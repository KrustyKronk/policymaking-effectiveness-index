"""Lithuania: laws adopted by the Seimas, rebuilt from the Seimas open-data XML (apps.lrs.lt/sip/p2b.*, CC BY 4.0).

The open data has no adopted-laws list, so:
1. p2b.ad_seimo_sesijos?ar_visos=T -> every session; keep those overlapping 2000-2025.
2. p2b.ad_seimo_posedziai?sesijos_id=N -> sittings of each session (cached raw/lt/posedziai_N.xml).
3. p2b.ad_seimo_posedzio_eiga_full?posedzio_id=N -> full proceedings of each sitting, with every agenda item
   (<pavadinimas>, <stadija>) and its votes (<balsavimas><aprasas>). Cached raw/lt/eiga/N.xml.
An item counts as an adopted law when its title contains "ĮSTATYM" (laws, codes, constitutional laws and
"ĮSTATYMO „Dėl ... ratifikavimo“"), not "NUTARIM"/"STATUT" (resolutions, Statute of the Seimas), and it has a
vote whose description starts "Pritarta"/"Priimta" and mentions "priėmim" (e.g. "Pritarta – dėl įstatymo
priėmimo"). The adoption vote happens at the "Priėmimas" stage (or on re-adoption after a presidential veto,
"Grąžinto įstatymo pakartotinis svarstymas"; those re-adoptions are de-duplicated by project number so a vetoed
law counts once, in the year of its first adoption). Year/date = sitting date. Items with a failed final vote
are not counted. Origin is not in this feed -> unknown. "biudžeto" + "patvirtinimo" -> budget_law;
"ratifikavimo" -> ratification.
1993-1999: the sitting proceedings feed is empty before 1999 (sittings carry no start time, eiga_full returns only
the sitting header, no agenda items or votes), so these years come from the Register of Legal Acts open data
(TAR, data.gov.lt UAPI https://get.data.gov.lt/datasets/gov/lrsk/teises_aktai/Dokumentas, rusis = "Įstatymas",
adopted by the Seimas, by adoption date `priimtas`), cached as raw/lt/tar/istatymai_YYYY.json, source tar_open_data.
In the overlap the register lists 0-14% (median ~6%) more laws per year than the sitting rebuild (2000: 528 vs 503; 2004: 465
vs 414; 2010: 441 vs 422): it also holds laws adopted inside grouped agenda items, so the 1999/2000 splice
over-states the earlier years by roughly that margin. TAR vs rebuild per year 2000-2010 -> raw/lt/tar_overlap.csv.
Known limitations: a law adopted as part of a grouped item whose title lacks "ĮSTATYM" is missed; vote
descriptions in some early-2000s sittings may be missing (then the item is not counted).
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

P2B = "https://apps.lrs.lt/sip/p2b"
D = RAW / "lt"
Y0, Y1 = 2000, 2025          # sitting rebuild
TAR_YEARS = range(1993, 2000)
TAR_CHECK = range(2000, 2011)
TAR = "https://get.data.gov.lt/datasets/gov/lrsk/teises_aktai/Dokumentas"
ADOPT_RE = re.compile(r"^\s*(Pritarta|Priimta)\b.*priėmim", re.I)
PROJ_RE = re.compile(r"\(Nr\.\s*([0-9A-ZĄČĘĖĮŠŲŪŽ]*P-\d+)", re.I)


def fetch(url: str, dest, sleep: float = 0.25, **kw) -> bytes:
    """common.get with a pause after every live request and a long back-off on HTTP 429."""
    if dest.exists():
        return dest.read_bytes()
    for attempt in range(4):
        try:
            b = get(url, dest, timeout=120, **kw)
            time.sleep(sleep)
            return b
        except RuntimeError as e:
            if "HTTP 429" in str(e) and attempt < 3:
                log.warning("lt: 429, sleeping %ds", 30 * 2 ** attempt)
                time.sleep(30 * 2 ** attempt)
                continue
            raise
    raise RuntimeError(f"lt: gave up on {url}")


def classify(title: str) -> tuple[str, bool, bool]:
    low = title.lower()
    is_rat = "ratifikavimo" in low
    is_bud = ("biudžeto" in low and "patvirtinimo" in low and not is_rat)
    return ("ratification" if is_rat else "budget_law" if is_bud else "law"), is_bud, is_rat


def tar_year(year: int) -> list[dict]:
    """Laws (rusis 'Įstatymas') adopted by the Seimas in `year`, from the Register of Legal Acts open data."""
    q = (f'rusis="Įstatymas"&priimtas>="{year}-01-01"&priimtas<="{year}-12-31"'
         "&select(_id,pavadinimas,priimtas,priemusi_inst,atv_dok_nr,dok_busena,tar_kodas,nuoroda)&limit(5000)")
    import json
    j = json.loads(fetch(f"{TAR}?{q}", D / "tar" / f"istatymai_{year}.json", sleep=1.0).decode("utf-8"))
    rows = [r for r in j.get("_data", []) if "seimas" in (r.get("priemusi_inst") or "").lower()]
    if len(rows) >= 5000:
        log.warning("lt TAR %d: hit the 5000-row limit, year may be truncated", year)
    return rows


def tar_laws(rebuilt: pd.DataFrame) -> pd.DataFrame:
    out, check = [], []
    for y in list(TAR_YEARS) + list(TAR_CHECK):
        try:
            rows = tar_year(y)
        except Exception as e:  # noqa: BLE001
            log.warning("lt TAR %d failed (kept going): %s", y, e)
            continue
        if y in TAR_CHECK:
            n = int((rebuilt.year == y).sum())
            check.append({"year": y, "tar": len(rows), "sitting_rebuild": n,
                          "pct_diff_tar_vs_rebuild": round(100 * (len(rows) - n) / n, 1) if n else None})
            continue
        for r in rows:
            title = " ".join((r.get("pavadinimas") or "").split())
            itype, is_bud, is_rat = classify(title)
            out.append({"country": "LT", "year": int(r["priimtas"][:4]), "date": r["priimtas"][:10],
                        "instrument_type": itype, "origin": "unknown", "title": title, "length_words": None,
                        "cap_topic": None, "is_budget": is_bud, "is_ratification": is_rat, "source": "tar_open_data",
                        "source_id": r.get("atv_dok_nr") or r.get("tar_kodas"),
                        "source_url": r.get("nuoroda") or f"{TAR}/{r['_id']}"})
    if check:
        ck = pd.DataFrame(check)
        ck.to_csv(D / "tar_overlap.csv", index=False)
        log.info("lt TAR vs sitting rebuild:\n%s", ck.to_string(index=False))
    return pd.DataFrame(out, columns=LAWS_COLUMNS).drop_duplicates("source_id")


def main():
    D.mkdir(parents=True, exist_ok=True)
    ses = ET.fromstring(fetch(f"{P2B}.ad_seimo_sesijos?ar_visos=T", D / "sesijos.xml"))
    sessions = [s.attrib for s in ses.iter("SeimoSesija")
                if s.attrib["data_iki"][:4] >= str(Y0) and s.attrib["data_nuo"][:4] <= str(Y1)]
    sittings = []
    for s in sessions:
        sid = s["sesijos_id"]
        x = ET.fromstring(fetch(f"{P2B}.ad_seimo_posedziai?sesijos_id={sid}", D / f"posedziai_{sid}.xml"))
        for p in x.iter("SeimoPosėdis"):
            sittings.append((p.attrib["posėdžio_id"], p.attrib.get("pradžia", "")[:10]))
    sittings = [s for s in dict(sittings).items() if s[1] and Y0 <= int(s[1][:4]) <= Y1]
    log.info("lt: %d sessions, %d sittings %d-%d", len(sessions), len(sittings), Y0, Y1)

    rows, seen, failed = [], set(), 0
    for i, (pid, date) in enumerate(sorted(sittings, key=lambda s: s[1])):
        if i and i % 250 == 0:
            log.info("lt: %d/%d sittings parsed, %d laws so far", i, len(sittings), len(rows))
        try:
            raw = fetch(f"{P2B}.ad_seimo_posedzio_eiga_full?posedzio_id={pid}", D / "eiga" / f"{pid}.xml")
            x = ET.fromstring(raw)
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.warning("lt: sitting %s failed: %s", pid, e)
            continue
        for item in x.iter():
            title_el = item.find("pavadinimas")
            if title_el is None or item.find("balsavimai") is None:
                continue
            title = " ".join((title_el.text or "").split())
            up = title.upper()
            if "ĮSTATYM" not in up or "NUTARIM" in up or "STATUT" in up:
                continue
            votes = [(v.findtext("aprasas") or "") for v in item.iter("balsavimas")]
            if not any(ADOPT_RE.search(v) for v in votes):
                continue
            m = PROJ_RE.search(title)
            key = m.group(1).upper() if m else re.sub(r"\W+", " ", up)
            if key in seen:
                continue
            seen.add(key)
            itype, is_bud, is_rat = classify(title)
            rows.append({
                "country": "LT", "year": int(date[:4]), "date": date, "instrument_type": itype, "origin": "unknown",
                "title": title, "length_words": None, "cap_topic": None, "is_budget": is_bud,
                "is_ratification": is_rat, "source": "lrs_open_data_eiga", "source_id": key,
                "source_url": f"{P2B}.ad_seimo_posedzio_eiga_full?posedzio_id={pid}",
            })
    df = pd.DataFrame(rows, columns=LAWS_COLUMNS)
    df = pd.concat([tar_laws(df), df], ignore_index=True).sort_values(["date", "source_id"])
    write_csv(df, INTER / "laws_lt.csv")
    counts = (df.groupby(["source", "year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="LT", source_url=lambda d: d.source.map({"tar_open_data": TAR}).fillna(
                  f"{P2B}.ad_seimo_posedzio_eiga_full")))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_lt.csv")
    log.info("lt: laws per year %s (%d sittings failed)", df.groupby("year").size().to_dict(), failed)


if __name__ == "__main__":
    main()
