"""Netherlands.
- Staatsblad via the officielebekendmakingen SRU endpoint (repository.overheid.nl): enacted Wet / Rijkswet
  publications, row level, one query per publication year 1995-2025 (the electronic Staatsblad starts in 1995).
- 1981-1994: CAP Netherlands laws file (raw/cap/NL_bills__2LAW10062020.csv = "PA_LAW_COMPLETE_1981-2009", the
  Dutch Policy Agendas laws dataset). It has only id, year, majortopic, subtopic: every row is one law (there is no
  enacted flag because the file holds laws only; its yearly totals track the Staatsblad within ~10% in 1995-2009,
  see raw/nl/cap_overlap.csv). Written as laws_nl.csv rows with source cap_nl, origin unknown, no title, date =
  1 January (the file has no date), cap_topic = majortopic.
- Tweede Kamer OData v4 (gegevensmagazijn): Zaak Soort 'Wetgeving' (government) and 'Initiatiefwetgeving'
  (members' bills), with Besluit expanded -> outcome, Kamerstukdossier expanded -> join to Staatsblad
  (behandeldDossier) for law origin."""
from __future__ import annotations

import re
import time

import pandas as pd
from lxml import etree

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, get_json, log, write_csv

SRU = "https://repository.overheid.nl/sru"
ODATA = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Zaak"
YEARS = range(1995, 2026)
CAP_YEARS = range(1981, 1995)
D = RAW / "nl"
PAUSE = 0.3
NS = {"dcterms": "http://purl.org/dc/terms/", "ow": "http://standaarden.overheid.nl/wetgeving/",
      "sru": "http://docs.oasis-open.org/ns/search-ws/sruResponse", "gzd": "http://standaarden.overheid.nl/sru"}


def _get(url, dest, **kw):
    """common.get with a pause after every live request and a long back-off on HTTP 429."""
    if dest.exists():
        return dest.read_bytes()
    for attempt in range(4):
        try:
            out = get(url, dest, **kw)
            time.sleep(PAUSE)
            return out
        except RuntimeError as e:
            if "HTTP 429" in str(e) and attempt < 3:
                log.warning("nl: 429, sleeping %ds", 30 * 2 ** attempt)
                time.sleep(30 * 2 ** attempt)
                continue
            raise
    raise RuntimeError(f"nl: gave up on {url}")


def _x(rec, path):
    e = rec.find(path, NS)
    return e.text.strip() if e is not None and e.text else None


# ---------------------------------------------------------------- Staatsblad
def staatsblad_year(year: int, dtype: str) -> list[dict]:
    rows, start, total = [], 1, None
    while total is None or start <= total:
        q = f'dt.type="{dtype}" and dt.date>={year}-01-01 and dt.date<={year}-12-31'
        xml = _get(SRU, D / "staatsblad" / f"{dtype}_{year}_s{start:04d}.xml",
                   params={"operation": "searchRetrieve", "version": "2.0", "query": q,
                           "maximumRecords": 1000, "startRecord": start})
        root = etree.fromstring(xml)
        total = int(root.findtext("sru:numberOfRecords", default="0", namespaces=NS))
        recs = root.findall(".//sru:record", NS)
        for r in recs:
            rows.append({
                "pub_year": year, "dtype": dtype,
                "identifier": _x(r, ".//dcterms:identifier"), "title": _x(r, ".//dcterms:title") or "",
                "date": _x(r, ".//dcterms:date"), "signed": _x(r, ".//ow:datumOndertekening"),
                "creator": _x(r, ".//dcterms:creator"), "dossier": _x(r, ".//ow:behandeldDossier"),
                "url": _x(r, ".//gzd:preferredUrl"),
            })
        if not recs:
            break
        start += len(recs)
    if total is not None and sum(1 for r in rows if r["pub_year"] == year) < total:
        log.warning("nl staatsblad %s %d: %d records announced, %d parsed", dtype, year, total, len(rows))
    return rows


def classify_law(title: str) -> tuple[str, bool, bool]:
    t = title.lower()
    if re.search(r"tot vaststelling van de begrotingsstat", t):
        return "budget_law", True, False
    if re.search(r"verandering in de grondwet|wijziging van de grondwet", t):
        return "constitutional_law", False, False
    if re.search(r"goedkeuring van (het|de)\b.*\b(verdrag|protocol|overeenkomst|akkoord)", t):
        return "ratification", False, True
    return "law", False, False


# ---------------------------------------------------------------- Tweede Kamer bills
def fetch_zaken(soort: str) -> list[dict]:
    items, skip, total, top = [], 0, None, 100
    while total is None or skip < total:
        try:
            j = get_json(ODATA, D / "zaak" / f"{soort}_skip{skip:05d}.json", params={
                "$filter": f"Soort eq '{soort}' and Verwijderd eq false", "$count": "true", "$top": top,
                "$skip": skip, "$orderby": "GestartOp,Id",
                "$select": "Id,Nummer,Titel,GestartOp,Afgedaan,Status,Vergaderjaar,Soort",
                "$expand": "Kamerstukdossier($select=Nummer,Toevoeging),"
                           "Besluit($select=BesluitSoort,BesluitTekst,Status,GewijzigdOp,Verwijderd;"
                           "$expand=Agendapunt($select=Id;$expand=Activiteit($select=Datum)))"})
            time.sleep(PAUSE)
        except Exception as e:  # noqa: BLE001
            log.warning("nl zaak %s skip %d failed: %s; keeping %d rows", soort, skip, e, len(items))
            break
        total = j.get("@odata.count", total or 0)
        items.extend(j["value"])
        if not j["value"]:
            break
        skip += top
    log.info("nl zaak %s: %d of %s", soort, len(items), total)
    return items


def bill_outcome(z: dict) -> tuple[str, str | None]:
    best = None  # (rank, outcome, date)
    for b in z.get("Besluit") or []:
        if b.get("Verwijderd") or b.get("Status") != "Besluit":
            continue
        s = (b.get("BesluitSoort") or "").lower()
        txt = (b.get("BesluitTekst") or "").lower()
        act = ((b.get("Agendapunt") or {}).get("Activiteit") or {})
        date = (act.get("Datum") or b.get("GewijzigdOp") or "")[:10] or None
        if s.startswith("stemmen - aangenomen") or s.startswith("stemmen - zonder stemming aannemen"):
            cand = (3, "enacted", date)
        elif s.startswith("stemmen - verworpen") or (s.startswith("stemmen") and "verworpen" in txt):
            cand = (2, "defeated", date)
        elif "ingetrokken" in s or "intrekken" in s or "ingetrokken" in txt:
            cand = (1, "withdrawn", date)
        else:
            continue
        if best is None or cand[0] > best[0] or (cand[0] == best[0] and (cand[2] or "") > (best[2] or "")):
            best = cand
    if best:
        return best[1], best[2]
    return ("lapsed" if z.get("Afgedaan") else "pending"), None


def main():
    D.mkdir(parents=True, exist_ok=True)
    # 1. bills (first, so laws can borrow origin through the dossier number)
    bills, dossier_origin = [], {}
    for soort, origin in (("Wetgeving", "government"), ("Initiatiefwetgeving", "parliament")):
        for z in fetch_zaken(soort):
            outcome, dfinal = bill_outcome(z)
            started = (z.get("GestartOp") or "")[:10] or None
            dossiers = [str(k["Nummer"]) for k in z.get("Kamerstukdossier") or [] if k.get("Nummer")]
            for k in dossiers:
                dossier_origin.setdefault(k, origin)
            bills.append({
                "country": "NL", "bill_id": dossiers[0] if dossiers else z["Nummer"], "title": z.get("Titel"),
                "year_introduced": int(started[:4]) if started else None, "origin": origin, "outcome": outcome,
                "date_introduced": started, "date_final": dfinal, "instrument_type": "law", "source": "tk_odata",
                "zaak_nummer": z["Nummer"], "vergaderjaar": z.get("Vergaderjaar"),
            })
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS + ["zaak_nummer", "vergaderjaar"])
    write_csv(bills_df, INTER / "bills_nl.csv")

    # 2. Staatsblad laws
    raw = []
    for y in YEARS:
        for dtype in ("wet", "rijkswet"):
            try:
                raw.extend(staatsblad_year(y, dtype))
            except Exception as e:  # noqa: BLE001
                log.warning("nl staatsblad %s %d failed: %s", dtype, y, e)
    seen, laws = set(), []
    for r in raw:
        if not r["identifier"] or r["identifier"] in seen:
            continue
        seen.add(r["identifier"])
        itype, is_budget, is_rat = classify_law(r["title"])
        laws.append({
            "country": "NL", "year": r["pub_year"], "date": (r["signed"] or r["date"] or "")[:10] or None,
            "instrument_type": itype, "origin": dossier_origin.get(r["dossier"] or "", "unknown"),
            "title": r["title"], "length_words": None, "cap_topic": None, "is_budget": is_budget,
            "is_ratification": is_rat, "source": f"staatsblad_sru_{r['dtype']}", "source_id": r["identifier"],
            "source_url": r["url"] or f"https://zoek.officielebekendmakingen.nl/{r['identifier']}.html",
        })
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS)
    try:
        cap = pd.read_csv(RAW / "cap" / "NL_bills__2LAW10062020.csv", sep=None, engine="python")
        cap.columns = [c.strip() for c in cap.columns]
        ov = pd.DataFrame({"cap": cap.year.value_counts(), "staatsblad": laws_df.year.value_counts()}).loc[1995:2009]
        ov["pct_diff_cap_vs_staatsblad"] = (100 * (ov.cap - ov.staatsblad) / ov.staatsblad).round(1)
        ov.rename_axis("year").to_csv(D / "cap_overlap.csv")
        log.info("nl CAP vs Staatsblad 1995-2009:\n%s", ov.to_string())
        c = cap[cap.year.isin(CAP_YEARS)]
        cap_rows = pd.DataFrame({
            "country": "NL", "year": c.year.astype(int), "date": c.year.astype(int).astype(str) + "-01-01",
            "instrument_type": "law", "origin": "unknown", "title": None, "length_words": None,
            "cap_topic": c.majortopic, "is_budget": False, "is_ratification": False, "source": "cap_nl",
            "source_id": "cap_nl_" + c["id"].astype(str),
            "source_url": "https://minio.la.utexas.edu/compagendas/datasetfiles/2LAW10062020.csv"})[LAWS_COLUMNS]
        laws_df = pd.concat([cap_rows, laws_df], ignore_index=True)
    except Exception as e:  # noqa: BLE001
        log.warning("nl CAP 1981-1994 rows skipped: %s", e)
    write_csv(laws_df, INTER / "laws_nl.csv")

    # 3. counts aggregated from rows
    if len(laws_df):
        grp = laws_df.source.where(laws_df.source == "cap_nl", "staatsblad_sru")
        c = laws_df.groupby([grp.rename("source"), "year", "instrument_type", "origin"]).size().reset_index(name="n")
        c["country"] = "NL"
        c["source_url"] = c.source.map({"cap_nl": "https://minio.la.utexas.edu/compagendas/datasetfiles/2LAW10062020.csv"}).fillna(
            "https://repository.overheid.nl/sru")
    else:
        c = pd.DataFrame(columns=COUNTS_COLUMNS)
    write_csv(c[COUNTS_COLUMNS], INTER / "counts_nl.csv")
    log.info("nl: %d laws (origin known %d), %d bills", len(laws_df), (laws_df.origin != "unknown").sum(),
             len(bills_df))


if __name__ == "__main__":
    main()
