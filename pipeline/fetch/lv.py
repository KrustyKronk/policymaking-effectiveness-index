"""Latvia: laws adopted by the Saeima, rebuilt from data.gov.lv dataset "saeimas-sedes" (Saeima sitting agendas
with results, one "-dkp" XML per sitting; coverage starts with the 12th Saeima autumn 2016 session).

- CKAN package_show?id=saeimas-sedes lists ~2,700 resources ("<N>.Saeimas <YYYY>.gada <session>-<k>-dkp|deb|vote");
  only the -dkp (agenda + result) files are downloaded, cached raw/lv/dkp/<resource id>.xml.
- Each <DKP> item: DKP_TYPE 1 = bill (likumprojekts), READING (1, 2, 3; 4 = repeated consideration after the
  President returned the law), RESULT ("Pieņemts", "Likums", "Nod. kom.", "Noraidīts"...), URGENCY,
  LIVSDOCUMENTID (bill number "709/Lp14"), TITLE, DKDATE (sitting date).
- A bill counts as an adopted law (final reading) when it has a positive result ("Pieņemts" or "Likums") in
  reading 3 or 4, or in reading 2 when the bill is urgent (two readings) or is a treaty/budget bill (international
  agreements and the budget are passed in two readings: title contains līgum/konvencij/protokol/nolīgum/
  memorand/budžet) and never appears in a third reading. One row per LIVSDOCUMENTID, dated at the first final
  vote (a law returned by the President and re-adopted counts once).
- Origin is not in the agenda file -> unknown. "budžet" + "likums par valsts budžetu"/"Par valsts budžetu" ->
  budget_law; treaty keywords + "Par ... " -> ratification.
Outputs: laws_lv.csv = open-data rebuild 2017-2025 (2016 dropped: autumn session only). counts_lv.csv = annual-report
totals 2010-2018 (REPORT_TOTALS) + open-data counts 2019-2025. NOTE: normalise_laws uses counts only for countries
without a laws file, so while laws_lv.csv exists the 2010-2016 report totals are a cross-check, not used.
Back-extension 2000-2009 (counts_lv.csv, source "saeima_likumprojektu_registrs", origin "all"): laws adopted per
calendar year (date of the final reading, i.e. the reading whose result is "Likums"), rebuilt from the Saeima bill
registers of the 7th Saeima (1998-2002, static archive https://www.saeima.lv/L_Saeima7/...), the 8th Saeima
(2002-2006, https://www.saeima.lv/Lapas/8Sae_Lprj/...) - one HTML page each with every bill, its stages, dates and
"Izsludināts" (promulgated) - and the 9th Saeima (2006-2010) LIVS Domino database (webAll view lists every bill
with status; each promulgated bill's document gives the stage dates; the final reading is the stage before
"Izsludināts"). Only promulgated laws are counted; a bill re-adopted after a presidential return counts once.
Cached under raw/lv/registers/. No cross-check year overlaps the annual-report series (the 9th Saeima ends in
Nov 2010), so 2010 stays on the report total. Origin (Iesniedzējs: Ministru kabinets = government) is logged only,
because counts for LV are origin "all".
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, manifest_add, session, write_csv

CKAN = "https://data.gov.lv/dati/api/3/action/package_show?id=saeimas-sedes"
D = RAW / "lv"
TREATY_RE = re.compile(r"līgum|konvencij|protokol|nolīgum|memorand|hartā|hartu|statūt", re.I)
BUDGET_RE = re.compile(r"budžet", re.I)
POSITIVE = {"Pieņemts", "Likums"}
# Laws adopted per calendar year, from the Saeima annual reports ("Saeimas gada pārskats"), read by hand from
# https://www.saeima.lv/files/PP/Saeimasgadaparskats{YEAR}.pdf (2010-2018; each report also repeats the
# previous years). From the 2019 report on, the headline counts laws adopted *from bills submitted that year*,
# which is not comparable, so 2019+ come from the open-data rebuild only. 2000-2009 reports are not online.
REPORT_TOTALS = {2010: 415, 2011: 255, 2012: 215, 2013: 396, 2014: 282, 2015: 225, 2016: 252, 2017: 278, 2018: 212}
REPORT_URL = "https://www.saeima.lv/files/PP/Saeimasgadaparskats{y}.pdf"
FIRST_FULL_YEAR = 2017   # the open data starts in the autumn 2016 session


REG7 = "https://www.saeima.lv/L_Saeima7/reg.jaut1-cbutton=Likumprojektu%20registrs.htm"
REG8 = "https://www.saeima.lv/Lapas/8Sae_Lprj/reg.jaut1-cbutton=Likumprojektu_registrs.htm"
LIVS9 = "https://titania.saeima.lv/LIVS/SaeimaLIVS.nsf"
BACK_YEARS = range(2000, 2010)


def _text(raw: bytes, enc: str) -> str:
    import html as h
    t = raw.decode(enc, errors="replace")
    t = re.sub(r"<(script|style).*?</\1>", "", t, flags=re.S)
    return re.sub(r"\s+", " ", h.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " "))


def register_laws(url: str, dest) -> list[dict]:
    """7th/8th Saeima static registers: one entry per bill 'Nr:N ... Iesniedzējs : ...;'."""
    txt = _text(get(url, dest, timeout=180), "cp1257")
    out = []
    for e in re.split(r"(?= Nr:\d+ )", txt):
        if "Izsludin" not in e:
            continue
        m = re.findall(r"(\d)\. ?lasījums (\d\d\.\d\d\.\d{4}) Likums", e)
        p = re.search(r"Izsludināts\.? ?(\d\d\.\d\d\.\d{4})", e)
        date = ddmmyyyy(m[-1][1]) if m else (ddmmyyyy(p.group(1)) if p else None)
        if not date:
            continue
        who = re.search(r"Iesniedzējs ?: ?([^;]+)", e)
        out.append({"date": date, "gov": bool(who and "Ministru kabinets" in who.group(1)),
                    "title": e[:120].strip()})
    return out


def livs9_laws() -> list[dict]:
    view = get(f"{LIVS9}/webAll?OpenView&Count=3000", D / "registers" / "livs9_webAll.html", timeout=180)
    rows = re.findall(r'dvRow_LPView\("([^"]*)","([^"]*)","([^"]*)","([0-9A-F]{32})"', view.decode("utf-8", "replace"))
    # Documents are kept in one JSON cache (raw/lv/registers/livs9_docs.json, unid -> page text): writing ~1,450
    # separate files through get() rewrites the raw manifest each time, which is far slower than the fetch itself.
    cache_f = D / "registers" / "livs9_docs.json"
    docs = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    for f in (D / "registers" / "livs9").glob("*.html") if (D / "registers" / "livs9").exists() else []:
        docs.setdefault(f.stem, _text(f.read_bytes(), "utf-8"))     # files from an earlier per-file run
    s = session()
    new = 0

    def flush():
        b = json.dumps(docs, ensure_ascii=False).encode("utf-8")
        cache_f.write_bytes(b)
        manifest_add(cache_f, f"{LIVS9}/0/<unid>?OpenDocument", b)

    out = []
    for status, title, nr, unid in rows:
        if "Izsludin" not in status and "izsludin" not in status:
            continue
        if unid not in docs:
            for attempt in range(4):
                try:
                    r = s.get(f"{LIVS9}/0/{unid}?OpenDocument", timeout=60)
                    if r.status_code == 200:
                        docs[unid] = _text(r.content, "utf-8")
                        break
                    if r.status_code in (403, 404):
                        break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(2 ** attempt)
            if unid not in docs:
                log.warning("lv: 9th Saeima bill %s failed", nr)
                continue
            new += 1
            time.sleep(0.3)
            if new % 200 == 0:
                flush()
                log.info("lv: 9th Saeima documents: %d fetched", len(docs))
        txt = docs[unid]
        hdr = re.search(r"Iesniegts (.*?) Datums ((?:\d\d\.\d\d\.\d{4} ?)+)", txt)
        if not hdr:
            continue
        dates = hdr.group(2).split()
        # final reading = the last date before the promulgation date
        if len(dates) < 2:
            continue
        date = ddmmyyyy(dates[-2]) if "Izsludināts" in hdr.group(1) else ddmmyyyy(dates[-1])
        who = re.search(r"Iesniedzēji?: (.+?) Dokumenti", txt)
        out.append({"date": date, "gov": bool(who and "Ministru kabinets" in who.group(1)), "title": title})
    if new:
        flush()
    return out


def back_counts() -> pd.DataFrame:
    laws = []
    for name, fn in (("7", lambda: register_laws(REG7, D / "registers" / "reg7.html")),
                     ("8", lambda: register_laws(REG8, D / "registers" / "reg8.html")),
                     ("9", livs9_laws)):
        try:
            got = fn()
            log.info("lv: %s. Saeima register: %d promulgated laws", name, len(got))
            laws += [dict(x, saeima=name) for x in got]
        except Exception as e:  # noqa: BLE001
            log.warning("lv: %s. Saeima register failed: %s", name, e)
    if not laws:
        return pd.DataFrame(columns=COUNTS_COLUMNS)
    df = pd.DataFrame(laws)
    df["year"] = df.date.str[:4].astype(int)
    df = df[df.year.isin(BACK_YEARS)]
    log.info("lv back-extension laws per year: %s", df.groupby("year").size().to_dict())
    log.info("lv back-extension government share per year: %s",
             df.groupby("year").gov.mean().round(2).to_dict())
    src = {"7": REG7, "8": REG8, "9": f"{LIVS9}/webAll?OpenView"}
    return (df.groupby("year").agg(n=("date", "size"), saeima=("saeima", lambda s: "+".join(sorted(set(s)))))
            .reset_index()
            .assign(country="LV", instrument_type="law", origin="all", source="saeima_likumprojektu_registrs",
                    source_url=lambda x: x.saeima.map(lambda k: " ; ".join(src[i] for i in k.split("+"))))[COUNTS_COLUMNS])


def ddmmyyyy(s: str) -> str | None:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def main():
    D.mkdir(parents=True, exist_ok=True)
    pkg = json.loads(get(CKAN, D / "package_show.json", force=True).decode("utf-8"))["result"]
    res = [r for r in pkg["resources"] if r["name"].strip().endswith("-dkp")]
    log.info("lv: %d dkp resources", len(res))
    items = []
    for i, r in enumerate(res):
        dest = D / "dkp" / f"{r['id']}.xml"
        cached = dest.exists()
        try:
            raw = get(r["url"], dest, timeout=120)
        except RuntimeError as e:
            log.warning("lv: %s failed: %s", r["name"], e)
            continue
        if not cached:
            time.sleep(0.3)
        try:
            x = ET.fromstring(raw.decode("utf-8-sig").encode("utf-8"))
        except ET.ParseError as e:
            log.warning("lv: %s unparsable: %s", r["name"], e)
            continue
        date = ddmmyyyy(x.findtext("DK/DKDATE") or "")
        for p in x.iter("DKP"):
            if p.findtext("DKP_TYPE") != "1":
                continue
            items.append({"doc": (p.findtext("LIVSDOCUMENTID") or "").strip(), "title": (p.findtext("TITLE") or "").strip(),
                          "reading": (p.findtext("READING") or "").strip(), "result": (p.findtext("RESULT") or "").strip(),
                          "urgent": (p.findtext("URGENCY") or "") == "True", "date": date, "res": r["name"]})
        if i and i % 200 == 0:
            log.info("lv: %d/%d files", i, len(res))
    it = pd.DataFrame(items)
    it = it[it.doc.ne("") & it.date.notna()]
    rows = []
    for doc, g in it.groupby("doc"):
        g = g.sort_values("date")
        title = g.title.iloc[0]
        has3 = g.reading.isin(["3"]).any()
        two_reading = g.urgent.any() or bool(TREATY_RE.search(title)) or bool(BUDGET_RE.search(title))
        pos = g[g.result.isin(POSITIVE)]
        final = pos[pos.reading.isin(["3", "4"]) | (pos.reading.eq("2") & two_reading & (not has3))]
        if final.empty:
            continue
        f = final.iloc[0]
        is_r = bool(TREATY_RE.search(title)) and title.lower().startswith("par ")
        is_b = bool(re.search(r"valsts budžetu|vidēja termiņa budžeta ietvar", title, re.I)) and not is_r
        rows.append({
            "country": "LV", "year": int(f.date[:4]), "date": f.date,
            "instrument_type": "ratification" if is_r else "budget_law" if is_b else "law", "origin": "unknown",
            "title": title, "length_words": None, "cap_topic": None, "is_budget": is_b, "is_ratification": is_r,
            "source": "data_gov_lv_saeimas_sedes", "source_id": doc,
            "source_url": "https://data.gov.lv/dati/lv/dataset/saeimas-sedes",
        })
    df = pd.DataFrame(rows, columns=LAWS_COLUMNS).sort_values(["date", "source_id"])
    part2016 = int((df.year == 2016).sum())
    df = df[(df.year >= FIRST_FULL_YEAR) & (df.year <= 2025)]
    write_csv(df, INTER / "laws_lv.csv")
    for y in (2017, 2018):
        log.info("lv %d: open-data rebuild %d vs annual report %d", y, int((df.year == y).sum()), REPORT_TOTALS[y])
    log.info("lv 2016 (autumn session only, dropped from laws_lv): %d vs report total %d", part2016, REPORT_TOTALS[2016])
    rep = pd.DataFrame([{"country": "LV", "year": y, "instrument_type": "law", "origin": "all", "n": n,
                         "source": "saeima_gada_parskats", "source_url": REPORT_URL.format(y=y)}
                        for y, n in REPORT_TOTALS.items()])
    od = (df[df.year > max(REPORT_TOTALS)].groupby(["year", "instrument_type"]).size().reset_index(name="n")
          .assign(country="LV", origin="all", source="data_gov_lv_saeimas_sedes", source_url=CKAN))
    try:
        back = back_counts()
    except Exception as e:  # noqa: BLE001
        log.warning("lv: 2000-2009 back-extension failed: %s", e)
        back = pd.DataFrame(columns=COUNTS_COLUMNS)
    write_csv(pd.concat([back, rep, od[COUNTS_COLUMNS]], ignore_index=True), INTER / "counts_lv.csv")
    log.info("lv laws per year: %s", df.groupby("year").size().to_dict())
    log.info("lv types: %s", df.instrument_type.value_counts().to_dict())


if __name__ == "__main__":
    main()
