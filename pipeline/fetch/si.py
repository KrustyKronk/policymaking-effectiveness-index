"""Slovenia: Državni zbor open data (fotogalerija.dz-rs.si/datoteke/opendata).
- SZ.XML: every adopted law since 1991, kept from FIRST_YEAR = 1992 (1991 is a partial post-independence year) (KARTICA_PREDLAGATELJ = proposer, KARTICA_POSTOPEK = procedure,
  Official Gazette citation, pisrs link) -> laws_si.csv + counts_si.csv.
- PZ2.XML .. PZ10.XML: every bill since Nov 1996 (mandates II-X) with its end-of-procedure phase
  (sprejet / umaknjen / konec postopka) and plenary votes -> bills_si.csv."""
from __future__ import annotations

import re

import pandas as pd
from lxml import etree

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

BASE = "https://fotogalerija.dz-rs.si/datoteke/opendata"
D = RAW / "si"
MANDATES = range(2, 11)
FIRST_YEAR = 1992
BUDGET_RE = re.compile(r"prora[čc]un", re.I)
# end-of-procedure phase (KARTICA_FAZA_POSTOPKA) -> outcome
PHASE_OUTCOME = {
    "sprejet predlog": "enacted",
    "umaknjen predlog": "withdrawn",
    "konec postopka": "defeated",      # procedure ended without adoption (rejected or dropped)
    "nepopoln predlog": "lapsed",      # incomplete proposal, never taken up
    "zavrnjen predlog": "defeated",
    "sprejet sklep": "defeated",       # a resolution (e.g. "bill not suitable for further reading") instead of the law
}


def _t(card, name: str) -> str:
    e = card.find(name)
    return (e.text or "").strip() if e is not None else ""


def origin_of(proposer: str) -> str:
    p = proposer.lower()
    if not p:
        return "unknown"
    if p.startswith("vlada"):
        return "government"
    if "državni svet" in p or "drzavni svet" in p:
        return "other"
    if "voliv" in p:                    # 5000 volivk in volivcev (popular initiative)
        return "other"
    if "poslan" in p:
        return "parliament"
    if "dz_as" in p or ".nsf" in p:     # Lotus Notes artefacts
        return "unknown"
    return "parliament"                 # bare MP names ("Rokavec Franci", "Potrč Miran;Veber Janko")


def classify(title: str, procedure: str) -> tuple[str, bool, bool]:
    t = title.lower()
    proc = procedure.lower()
    is_rat = proc == "ratifikacija" or t.startswith("zakon o ratifikaciji")
    is_budget = bool(BUDGET_RE.search(t)) and not is_rat
    if t.startswith("ustavni zakon"):
        itype = "constitutional_law"
    elif is_rat:
        itype = "ratification"
    elif is_budget:
        itype = "budget_law"
    else:
        itype = "law"
    return itype, is_budget, is_rat


def parse_laws() -> list[dict]:
    xml = get(f"{BASE}/SZ.XML", D / "SZ.XML", timeout=600)
    root = etree.fromstring(xml)
    rows, skipped = [], 0
    for p in root.findall("PREDPIS"):
        card = p.find("KARTICA_PREDPISA")
        if card is None:
            continue
        title = _t(card, "KARTICA_NAZIV")
        date = _t(card, "KARTICA_DATUM")[:10]
        objava = _t(card, "KARTICA_OBJAVA")
        if not re.match(r"\d{4}-\d{2}-\d{2}", date):
            m = re.search(r"/(\d{2})\b", objava)          # "Uradni list RS 11/91"
            if not m or not title:
                skipped += 1
                continue
            yy = int(m.group(1))
            date = f"{1900 + yy if yy > 50 else 2000 + yy}-01-01"
        proc = _t(card, "KARTICA_POSTOPEK")
        itype, is_budget, is_rat = classify(title, proc)
        sop = _t(card, "KARTICA_SOP")
        unid = _t(card, "UNID")
        url = (_t(card, "KARTICA_URL_REGISTER_PREDPISOV") or _t(card, "KARTICA_URL_URADNI_LIST")
               or _t(card, "KARTICA_URL_DZ"))
        rows.append({
            "country": "SI", "year": int(date[:4]), "date": date, "instrument_type": itype,
            "origin": origin_of(_t(card, "KARTICA_PREDLAGATELJ")), "title": title, "length_words": None,
            "cap_topic": None, "is_budget": is_budget, "is_ratification": is_rat, "source": "dz_rs_opendata",
            "source_id": " | ".join(x for x in (f"SOP {sop}" if sop else "", objava,
                                                 _t(card, "KARTICA_EPA") if _t(card, "KARTICA_EPA").strip("0") else "")
                                   if x) or unid,
            "source_url": url, "procedure": proc.lower(), "mandate": _t(card, "KARTICA_MANDAT"),
        })
    if skipped:
        log.warning("si: skipped %d SZ records without a usable date", skipped)
    return rows


def parse_bills(mandate: int) -> list[dict]:
    xml = get(f"{BASE}/PZ{mandate}.XML", D / f"PZ{mandate}.XML", timeout=600)
    root = etree.fromstring(xml)
    # last plenary vote per bill (by EPA number) -> date_final
    last_vote: dict[str, str] = {}
    for o in root.findall("OBRAVNAVA_PREDPISA"):
        card = o.find("KARTICA_OBRAVNAVE_PREDPISA")
        epa = _t(card, "KARTICA_EPA") if card is not None else ""
        for g in o.iter("GLASOVANJE_CAS"):
            d = (g.text or "")[:10]
            if epa and d and d > last_vote.get(epa, ""):
                last_vote[epa] = d
    rows, unmapped = [], {}
    for p in root.findall("PREDPIS"):
        card = p.find("KARTICA_PREDPISA")
        if card is None:
            continue
        title = _t(card, "KARTICA_NAZIV")
        date = _t(card, "KARTICA_DATUM")[:10]
        if not title or not re.match(r"\d{4}-\d{2}-\d{2}", date):
            continue
        phase = _t(card, "KARTICA_FAZA_POSTOPKA").lower()
        outcome = PHASE_OUTCOME.get(phase)
        if outcome is None:
            unmapped[phase] = unmapped.get(phase, 0) + 1
            outcome = "lapsed" if _t(card, "KARTICA_KONEC_POSTOPKA") == "1" else "pending"
        proc = _t(card, "KARTICA_POSTOPEK")
        itype, _, _ = classify(title, proc)
        epa = _t(card, "KARTICA_EPA")
        rows.append({
            "country": "SI", "bill_id": epa or _t(card, "UNID"), "title": title, "year_introduced": int(date[:4]),
            "origin": origin_of(_t(card, "KARTICA_PREDLAGATELJ")), "outcome": outcome, "date_introduced": date,
            "date_final": last_vote.get(epa), "instrument_type": itype, "source": "dz_rs_opendata",
            "mandate": mandate, "procedure": proc.lower(), "phase": phase,
        })
    if unmapped:
        log.warning("si PZ%d: unmapped end phases %s", mandate, unmapped)
    return rows


def main():
    laws = parse_laws()
    early = sum(r["year"] < FIRST_YEAR for r in laws)
    laws = [r for r in laws if r["year"] >= FIRST_YEAR]
    log.info("si: %d laws before %d dropped", early, FIRST_YEAR)
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["procedure", "mandate"]).sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_si.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="SI", source="dz_rs_opendata", source_url=f"{BASE}/SZ.XML"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_si.csv")
    log.info("si: %d laws, %s", len(laws_df), laws_df.groupby("year").size().loc[[2000, 2010, 2025]].to_dict())

    bills = []
    for m in MANDATES:
        try:
            b = parse_bills(m)
            bills.extend(b)
            log.info("si PZ%d: %d bills", m, len(b))
        except Exception as e:  # noqa: BLE001
            log.error("si PZ%d failed: %s", m, e)
    if bills:
        bills_df = pd.DataFrame(bills)
        bills_df = bills_df.drop_duplicates("bill_id", keep="last").sort_values(["date_introduced", "bill_id"])
        write_csv(bills_df[BILLS_COLUMNS + ["mandate", "procedure", "phase"]], INTER / "bills_si.csv")
        log.info("si bills: %s", bills_df.outcome.value_counts().to_dict())
    else:
        log.error("si: no bill files parsed, bills_si.csv not written")


if __name__ == "__main__":
    main()
