"""Romania. cdep.ro promulgated-laws lists exist from 1996 but only from the 1996-2000 legislature (Nov 1996): the
1996 list holds 1 law and 1997 144 laws against law numbers up to 221 (1998: 253 of max no. 261; 1999: 208 of 210).
So laws_ro.csv / counts_ro.csv start in ROBUST_FROM = 1998; 1996-1997 are fetched and kept in raw/ro/cdep_laws.csv
only. OUG rows are kept for the same years (the SOAP enumeration is by number across all years, so 1990s OUGs come
for free: 1993: 1, 1996: 2, 1997: 76).
- Promulgated laws per year from the Chamber of Deputies database:
  https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.lista?cam=2&anl=YYYY (HTML table: bill id, title, Lege N/YYYY, date).
  Origin from the bill's nature: 'Proiect de Lege' / 'Proiectul Legii' = government bill, 'Propunere legislativă' =
  deputies/senators/citizens -> parliament. A small sample of bill pages per year is opened to confirm
  'Initiator: Guvern' (raw/ro/initiator_sample.csv): it agrees on only ~80%, because a deputies'/senators' proposal
  adopted by the Senate first arrives in the Chamber titled 'Proiect de lege'. So for ordinary laws titled 'Proiect de
  lege' the bill page's 'Initiator:' is read (Guvern -> government; deputies/senators/committees -> parliament;
  citizens -> other; time-boxed, fallback = title rule). Laws approving/rejecting ordinances, ratifications and budget
  laws are government bills by construction.
  Laws approving / rejecting emergency ordinances are kept as laws with note='oug_approval' / 'oug_rejection' and are
  reported separately in counts_ro.csv (instrument_type 'law' excludes them) so OUGs are not counted twice.
- Emergency ordinances (OUG) from the free legislatie.just.ro SOAP service (GetToken + Search). The year filter is
  ignored whenever a title/text filter is set and pages are capped at 10 rows, but SearchNumar + SearchTitlu works,
  so OUGs are enumerated by number: for N = 1, 2, ... search 'ORDONANŢĂ DE URGENŢĂ nr. N din' with SearchNumar=N and
  page through until an empty page (a 9-row page can precede a full one, so short pages do not end the paging); stop after STOP_AFTER consecutive numbers with no OUG. Year = date in the title ('nr. N din 16 martie
  2017'). Rows -> instrument_type decree_law, origin government. Cross-checked against the max OUG number cited in
  cdep.ro law titles per year (raw/ro/oug_check.csv)."""
from __future__ import annotations

import datetime as dt
import random
import re
import time
from xml.sax.saxutils import escape

import pandas as pd
from lxml import html as lhtml

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, manifest_add, write_csv

D = RAW / "ro"
CDEP = "https://www.cdep.ro"
LISTA = f"{CDEP}/ords/pls/proiecte/upl_pck2015.lista"
SOAP = "http://legislatie.just.ro/apiws/FreeWebService.svc/SOAP"
YEARS = range(1996, 2026)
ROBUST_FROM = 1998
SLEEP = 0.4
STOP_AFTER = 15          # consecutive OUG numbers with no hit (any year) before the enumeration stops
MAX_NUMAR = 400
SOAP_BUDGET_S = 50 * 60
MAX_PAGES = 8
SAMPLE_PER_YEAR = 6
INITIATOR_BUDGET_S = 75 * 60

MONTHS = {"ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
          "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12}


def get429(url, dest, **kw) -> bytes:
    """common.get with a long back-off on HTTP 429 (pauses after live requests are done by the callers)."""
    for attempt in range(4):
        try:
            return get(url, dest, **kw)
        except RuntimeError as e:
            if "HTTP 429" in str(e) and attempt < 3:
                log.warning("ro: 429 from %s, sleeping %ds", url, 30 * 2 ** attempt)
                time.sleep(30 * 2 ** attempt)
                continue
            raise
    raise RuntimeError(f"ro: gave up on {url}")


def ascii_ro(s: str) -> str:
    """Lower-case and fold Romanian diacritics (both comma and cedilla forms) for matching."""
    s = (s or "").lower()
    return re.sub(r"[şș]", "s", re.sub(r"[ţț]", "t", re.sub(r"[ăâ]", "a", re.sub(r"î", "i", s))))


# ----------------------------------------------------------------------------------------------- cdep.ro laws
def cdep_year(year: int) -> list[dict]:
    raw = get429(LISTA, D / "cdep" / f"lista_{year}.html", params={"cam": 2, "anl": year})
    doc = lhtml.fromstring(raw.decode("utf-8", "replace"))
    rows = []
    for tr in doc.xpath("//tr"):
        tds = tr.xpath("./td")
        if len(tds) < 4:
            continue
        law_a = tds[3].xpath(".//a[contains(@href,'legis_pck.htp_act')]")
        if not law_a:
            continue
        bill_a = tds[1].xpath(".//a")
        bill_id = bill_a[0].text_content().strip() if bill_a else tds[1].text_content().strip()
        bill_url = CDEP + bill_a[0].get("href") if bill_a else None
        title = re.sub(r"\s+", " ", tds[2].text_content()).strip()
        law_txt = law_a[0].text_content().strip()                 # 'Lege 2/2015'
        m = re.search(r"(\d+)/(\d{4})", law_txt)
        cell = tds[3].text_content()
        dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", cell)
        date = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else f"{year}-01-01"
        rows.append({"year": year, "bill_id": bill_id, "bill_url": bill_url, "title": title, "law": law_txt,
                     "law_no": int(m.group(1)) if m else None, "law_year": int(m.group(2)) if m else year,
                     "date": date, "law_url": CDEP + law_a[0].get("href")})
    m = re.search(r"Număr înregistrări găsite:\s*(\d+)", raw.decode("utf-8", "replace"))
    if m and int(m.group(1)) != len(rows):
        log.warning("ro %d: page says %s records, parsed %d", year, m.group(1), len(rows))
    return rows


def nature(title: str) -> str:
    t = ascii_ro(title)
    if t.startswith("proiect de lege") or t.startswith("proiectul legii") or t.startswith("proiect de lege"):
        return "government"
    if t.startswith("propunere legislativa"):
        return "parliament"
    return "unknown"


OUG_RX = re.compile(r"ordonant\w* de urgenta[^0-9]{0,40}nr\.?\s*(\d+)\s*/\s*(\d{4})")


def classify(title: str) -> tuple[str, str | None]:
    t = ascii_ro(title)
    note = None
    if re.search(r"aprobarea ordonant\w* de urgenta", t):
        note = "oug_approval"
    elif re.search(r"respingerea ordonant\w* de urgenta", t):
        note = "oug_rejection"
    elif re.search(r"aprobarea ordonant", t):
        note = "og_approval"
    elif re.search(r"respingerea ordonant", t):
        note = "og_rejection"
    if re.search(r"bugetul(ui)? de stat|bugetul(ui)? asigurarilor sociale de stat", t):
        return "budget_law", note
    if re.search(r"\bratificarea\b|\bratificare\b|\baderarea romaniei\b", t):
        return "ratification", note
    if re.search(r"revizuirea constitutiei", t):
        return "constitutional_law", note
    return "law", note


def initiator_sample(rows: list[dict]) -> pd.DataFrame:
    """Open a few bill pages per year and read 'Initiator:' to validate the nature->origin rule."""
    out = []
    rnd = random.Random(17)
    rnd_early = random.Random(1996)   # separate stream so the 2000+ samples (and their cached pages) stay the same
    by_year: dict[int, list[dict]] = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r)
    for y, rs in sorted(by_year.items()):
        for r in (rnd_early if y < 2000 else rnd).sample(rs, min(SAMPLE_PER_YEAR, len(rs))):
            if not r["bill_url"]:
                continue
            idp = re.search(r"idp=(\d+)", r["bill_url"])
            dest = D / "cdep" / "bills" / f"{idp.group(1) if idp else 'x'}.html"
            try:
                live = not dest.exists()
                h = get429(r["bill_url"], dest, retries=2).decode("utf-8", "replace")
                if live:
                    time.sleep(SLEEP)
            except Exception as e:  # noqa: BLE001
                log.warning("ro bill page %s: %s", r["bill_url"], e)
                continue
            m = re.search(r"Initiator:\s*</td>\s*<td[^>]*>(.*?)</td>", h, re.S)
            init = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else None
            out.append({"year": y, "bill_id": r["bill_id"], "nature_origin": nature(r["title"]), "initiator": init,
                        "initiator_is_gov": (init or "").lower().startswith("guvern") if init else None})
    df = pd.DataFrame(out)
    if len(df):
        ok = ((df.nature_origin == "government") == df.initiator_is_gov.fillna(False))
        log.info("ro initiator sample: %d bills, nature rule agrees with 'Initiator' on %.0f%%", len(df), 100 * ok.mean())
    return df


def bill_initiator(bill_url: str) -> str | None:
    """'Initiator:' cell of a cdep.ro bill page (cached under raw/ro/cdep/bills/)."""
    idp = re.search(r"idp=(\d+)", bill_url or "")
    if not idp:
        return None
    dest = D / "cdep" / "bills" / f"{idp.group(1)}.html"
    live = not dest.exists()
    h = get429(bill_url, dest, retries=2, timeout=60).decode("utf-8", "replace")
    if live:
        time.sleep(SLEEP)
    m = re.search(r"Initiator:\s*</td>\s*<td[^>]*>(.*?)</td>", h, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else None


def initiator_origin(init: str | None) -> str | None:
    i = ascii_ro(init or "")
    if not i:
        return None
    if i.startswith("guvern"):
        return "government"
    if re.search(r"cetateni", i):
        return "other"
    if re.search(r"deputat|senator|comisi|grup", i):
        return "parliament"
    return None


def initiator_lookup(rows: list[dict], deadline: float) -> dict[str, str]:
    """Bill-page initiator for ordinary laws titled 'Proiect de lege': a deputies'/senators' proposal adopted by the
    Senate first reaches the Chamber as a 'proiect de lege', so the title rule over-counts government bills
    (sample: 31 of 134). Returns {bill_url: origin}."""
    out, n, fails = {}, 0, 0
    for r in rows:
        if time.time() > deadline:
            log.warning("ro initiator lookup: time budget hit after %d bill pages", n)
            break
        try:
            o = initiator_origin(bill_initiator(r["bill_url"]))
        except Exception as e:  # noqa: BLE001
            fails += 1
            if fails > 50:
                log.warning("ro initiator lookup: too many failures, stopping (%s)", e)
                break
            continue
        n += 1
        if o:
            out[r["bill_url"]] = o
        if n % 500 == 0:
            log.info("ro initiator lookup: %d/%d bill pages", n, len(rows))
    return out


# ----------------------------------------------------------------------------------------------- SOAP OUG
_TOKEN: str | None = None


def soap_call(action: str, body: str) -> str:
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"http://tempuri.org/IFreeWebService/{action}"'}
    env = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>' + body + "</s:Body></s:Envelope>")
    raw = get(SOAP, None, method="POST", data=env.encode("utf-8"), headers=headers, retries=2, timeout=120,
              ok_statuses=(200, 500))
    return raw.decode("utf-8", "replace")


def soap_token() -> str:
    global _TOKEN
    x = soap_call("GetToken", '<GetToken xmlns="http://tempuri.org/"/>')
    m = re.search(r"<GetTokenResult>([^<]*)", x)
    if not m:
        raise RuntimeError("GetToken failed: " + x[:200])
    _TOKEN = m.group(1)
    return _TOKEN


def soap_search(numar: int, titlu: str, page: int, dest) -> list[dict]:
    """Search page (10 rows max); cached XML under raw/ro/oug/. Token is refreshed on 'TOKEN INVALID'."""
    if dest.exists():
        x = dest.read_text(encoding="utf-8")
    else:
        tok = _TOKEN or soap_token()
        for attempt in range(3):
            body = (f'<Search xmlns="http://tempuri.org/"><SearchModel xmlns:a="http://schemas.datacontract.org/2004/07/FreeWebService">'
                    f"<a:NumarPagina>{page}</a:NumarPagina><a:RezultatePagina>10</a:RezultatePagina><a:SearchAn></a:SearchAn>"
                    f"<a:SearchNumar>{numar}</a:SearchNumar><a:SearchText></a:SearchText><a:SearchTitlu>{escape(titlu)}</a:SearchTitlu>"
                    f"</SearchModel><tokenKey>{tok}</tokenKey></Search>")
            x = soap_call("Search", body)
            time.sleep(SLEEP)
            if "TOKEN INVALID" in x:
                tok = soap_token()
                continue
            if "<s:Fault>" in x:
                raise RuntimeError("SOAP fault: " + (re.search(r"<faultstring[^>]*>([^<]*)", x) or [None, x[:200]])[1])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(x, encoding="utf-8")
            manifest_add(dest, SOAP + f"#Search numar={numar} page={page}", x.encode("utf-8"))
            break
        else:
            raise RuntimeError("SOAP token could not be refreshed")
    out = []
    for l in re.findall(r"<a:Legi>(.*?)</a:Legi>", x, re.S):
        d = dict(re.findall(r"<a:(\w+)>(.*?)</a:\1>", l, re.S))
        d.pop("Text", None)
        out.append(d)
    return out


def oug_enumerate(deadline: float) -> tuple[list[dict], bool]:
    rows, seen, empty_run, complete = [], set(), 0, False
    for n in range(1, MAX_NUMAR + 1):
        if time.time() > deadline:
            log.warning("ro OUG: SOAP time budget hit at numar %d", n)
            break
        hits, page, page_seen = 0, 1, set()
        while True:
            try:
                res = soap_search(n, f"ORDONANŢĂ DE URGENŢĂ nr. {n} din", page, D / "oug" / f"n{n:03d}_p{page}.xml")
            except Exception as e:  # noqa: BLE001
                log.warning("ro OUG numar %d page %d: %s", n, page, e)
                break
            for d in res:
                if "URGEN" not in (d.get("TipAct") or "").upper():
                    continue
                titlu = re.sub(r"\s+", " ", d.get("Titlu", "")).strip()
                m = re.search(r"nr\.?\s*(\d+)\s+din\s+(\d{1,2})\s+(\w+)\s+(\d{4})", titlu)
                if not m or int(m.group(1)) != n:
                    continue
                mon = MONTHS.get(m.group(3).lower())
                y = int(m.group(4))
                date = f"{y}-{mon:02d}-{int(m.group(2)):02d}" if mon else f"{y}-01-01"
                key = (y, n)
                if key in seen:
                    continue
                seen.add(key)
                hits += 1
                rows.append({"year": y, "number": n, "date": date, "title": titlu, "emitent": d.get("Emitent"),
                             "url": d.get("LinkHtml"), "data_vigoare": d.get("DataVigoare")})
            # pages are unreliable: a short page (9 rows) can be followed by a full one, so page until an
            # empty page or a page that adds nothing new (cap MAX_PAGES)
            new_keys = {(r.get("Titlu"), r.get("DataVigoare")) for r in res} - page_seen
            page_seen |= new_keys
            if not res or not new_keys or page >= MAX_PAGES:
                break
            page += 1
        empty_run = empty_run + 1 if hits == 0 else 0
        if n % 25 == 0:
            log.info("ro OUG: numar %d, %d ordinances so far", n, len(rows))
        if empty_run >= STOP_AFTER:
            complete = True
            break
    return rows, complete


# ----------------------------------------------------------------------------------------------- main
def main():
    D.mkdir(parents=True, exist_ok=True)
    # 1. laws from cdep.ro
    cdep_rows = []
    for y in YEARS:
        live = not (D / "cdep" / f"lista_{y}.html").exists()
        try:
            rows = cdep_year(y)
            cdep_rows.extend(rows)
            log.info("ro %d: %d promulgated laws", y, len(rows))
        except Exception as e:  # noqa: BLE001
            log.warning("ro cdep %d failed: %s", y, e)
        if live:
            time.sleep(SLEEP)
    pd.DataFrame(cdep_rows).to_csv(D / "cdep_laws.csv", index=False)
    log.info("ro: %d laws listed for partial years < %d dropped from laws_ro.csv",
             sum(1 for r in cdep_rows if r["law_year"] < ROBUST_FROM), ROBUST_FROM)
    cdep_rows = [r for r in cdep_rows if r["law_year"] >= ROBUST_FROM]
    try:
        initiator_sample(cdep_rows).to_csv(D / "initiator_sample.csv", index=False)
    except Exception as e:  # noqa: BLE001
        log.warning("ro initiator sample failed: %s", e)

    # origin: OUG/OG approval laws, ratifications and budgets are government bills by construction; 'Propunere
    # legislativă' = parliament; ordinary 'Proiect de lege' laws -> bill-page Initiator (fallback: title rule)
    cand = [r for r in cdep_rows if r["bill_url"] and classify(r["title"]) == ("law", None)
            and nature(r["title"]) == "government"]
    init = initiator_lookup(cand, time.time() + INITIATOR_BUDGET_S)
    log.info("ro initiator lookup: %d/%d ordinary 'proiect de lege' laws resolved: %s", len(init), len(cand),
             pd.Series(list(init.values())).value_counts().to_dict() if init else {})

    def origin_of(r: dict, itype: str, note: str | None) -> str:
        if note or itype in ("ratification", "budget_law"):
            return "government" if nature(r["title"]) != "parliament" else "parliament"
        return init.get(r["bill_url"]) or nature(r["title"])

    laws = []
    for r in cdep_rows:
        itype, note = classify(r["title"])
        laws.append({"country": "RO", "year": r["law_year"], "date": r["date"], "instrument_type": itype,
                     "origin": origin_of(r, itype, note), "title": r["title"], "length_words": None, "cap_topic": None,
                     "is_budget": itype == "budget_law", "is_ratification": itype == "ratification",
                     "source": "cdep_ro", "source_id": r["law"], "source_url": r["law_url"], "note": note,
                     "bill_id": r["bill_id"], "bill_url": r["bill_url"]})
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["note", "bill_id", "bill_url"])
    laws_df = laws_df.drop_duplicates("source_id")

    # 2. OUG via SOAP (fallback: max OUG number cited in law titles per year)
    cited: dict[int, int] = {}
    for r in cdep_rows:
        for num, yr in OUG_RX.findall(ascii_ro(r["title"])):
            cited[int(yr)] = max(cited.get(int(yr), 0), int(num))
    oug_rows, complete, soap_ok = [], False, True
    try:
        oug_rows, complete = oug_enumerate(time.time() + SOAP_BUDGET_S)
    except Exception as e:  # noqa: BLE001
        log.warning("ro OUG SOAP failed: %s", e)
        soap_ok = False
    oug_df = pd.DataFrame(oug_rows)
    if len(oug_df):
        oug_df.to_csv(D / "oug_soap.csv", index=False)
        soap_by_year = oug_df.groupby("year").size().to_dict()
    else:
        soap_by_year = {}
    check = pd.DataFrame([{"year": y, "soap_n": soap_by_year.get(y), "soap_max_no": int(oug_df[oug_df.year == y].number.max()) if len(oug_df) and (oug_df.year == y).any() else None,
                           "cited_max_no_in_law_titles": cited.get(y)} for y in YEARS])
    check.to_csv(D / "oug_check.csv", index=False)
    log.info("ro OUG check (year: soap_n / soap_max / cited_max):\n%s", check.to_string(index=False))

    oug_laws = pd.DataFrame([{"country": "RO", "year": r["year"], "date": r["date"], "instrument_type": "decree_law",
                              "origin": "government", "title": r["title"], "length_words": None, "cap_topic": None,
                              "is_budget": False, "is_ratification": False, "source": "legislatie_just_ro_soap",
                              "source_id": f"OUG {r['number']}/{r['year']}", "source_url": r["url"], "note": None,
                              "bill_id": None, "bill_url": None} for r in oug_rows if r["year"] in YEARS and r["year"] >= ROBUST_FROM],
                            columns=laws_df.columns)
    out = pd.concat([laws_df, oug_laws], ignore_index=True).sort_values(["date", "source_id"]).reset_index(drop=True)
    write_csv(out, INTER / "laws_ro.csv")

    # 3. counts: laws by type excluding OUG/OG approval laws; those reported separately; OUG from SOAP or fallback
    base = laws_df[laws_df.note.isna()]
    counts = (base.groupby(["year", "instrument_type"]).size().reset_index(name="n")
              .assign(origin="all", source="cdep_ro", source_url=LISTA))
    appr = (laws_df[laws_df.note.notna()].groupby(["year", "note"]).size().reset_index(name="n")
            .rename(columns={"note": "instrument_type"}).assign(origin="all", source="cdep_ro", source_url=LISTA))
    gov = (laws_df.groupby(["year", "origin"]).size().reset_index(name="n").assign(instrument_type="law_all", source="cdep_ro", source_url=LISTA))
    if soap_ok and len(oug_df):
        oug_counts = pd.DataFrame([{"year": y, "instrument_type": "decree_law", "origin": "government",
                                    "n": soap_by_year.get(y, 0), "source": "legislatie_just_ro_soap" + ("" if complete else "_partial"),
                                    "source_url": SOAP} for y in YEARS if y >= ROBUST_FROM])
    else:
        log.warning("ro OUG: using max OUG number cited in cdep.ro law titles as the yearly count (SOAP unavailable)")
        oug_counts = pd.DataFrame([{"year": y, "instrument_type": "decree_law", "origin": "government", "n": cited.get(y),
                                    "source": "cdep_ro_cited_max_oug_number", "source_url": LISTA} for y in YEARS if y >= ROBUST_FROM])
    counts = pd.concat([counts, appr, gov, oug_counts], ignore_index=True).assign(country="RO")
    write_csv(counts[COUNTS_COLUMNS].sort_values(["year", "instrument_type", "origin"]), INTER / "counts_ro.csv")
    log.info("ro: %d laws (%d OUG-approval/rejection), %d OUG (%s)", len(laws_df), laws_df.note.notna().sum(),
             len(oug_laws), "complete" if complete else "partial")


if __name__ == "__main__":
    main()
