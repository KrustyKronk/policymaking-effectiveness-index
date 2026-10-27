"""Poland: Sejm ELI API (acts published in Dziennik Ustaw, type Ustawa) 1991-2025 -> laws_pl.csv (1989-90 are
excluded as pre-democratic: the first fully free Sejm sat from Nov 1991, ERAS PL = 1991);
Sejm legislative processes API, terms 7-10 (2011-) -> bills_pl.csv with origin from the title prefix."""
from __future__ import annotations

import re
import time

import pandas as pd

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get_json, log, write_csv

D = RAW / "pl"
FIRST_YEAR, LAST_YEAR = 1991, 2025
SLEEP = 1.5                     # between uncached ELI calls
ELI = "https://api.sejm.gov.pl/eli/acts/search"
PROC = "https://api.sejm.gov.pl/sejm/term{term}/processes"
ORIGIN_PREFIX = [("rządowy", "government"), ("poselski", "parliament"), ("senacki", "parliament"),
                 ("komisyjny", "parliament"), ("prezydencki", "other"), ("obywatelski", "other")]


def acts_for_year(year: int) -> list[dict]:
    out, offset = [], 0
    while True:
        dest = D / f"eli_{year}_off{offset:05d}.json"
        if not dest.exists():
            time.sleep(SLEEP)
        j = get_json(ELI, dest,
                     params={"publisher": "DU", "year": year, "type": "Ustawa", "limit": 500, "offset": offset})
        items = j.get("items", [])
        out.extend(items)
        offset += 500
        if offset >= j.get("totalCount", 0) or not items:
            break
    return out


def main():
    laws = []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        try:
            acts = acts_for_year(year)
        except Exception as e:  # noqa: BLE001
            log.error("pl %d: ELI search failed (%s); year left empty", year, e)
            continue
        for a in acts:
            title = a.get("title") or ""
            tl = title.lower()
            if "budżetowa na rok" in tl:
                itype = "budget_law"
            elif "ratyfikacji" in tl:
                itype = "ratification"
            elif "o zmianie konstytucji" in tl:
                itype = "constitutional_law"
            else:
                itype = "law"
            date = a.get("promulgation") or a.get("announcementDate") or f"{year}-01-01"
            laws.append({
                "country": "PL", "year": int(date[:4]), "date": date[:10], "instrument_type": itype,
                "origin": "unknown", "title": title, "length_words": None, "cap_topic": None,
                "is_budget": itype == "budget_law", "is_ratification": itype == "ratification",
                "source": "sejm_eli", "source_id": a.get("ELI"), "source_url": f"https://eli.gov.pl/eli/{a.get('ELI')}/ogl",
            })
        log.info("pl %d: %d acts so far", year, len(laws))
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).drop_duplicates("source_id").sort_values("date")
    write_csv(laws_df, INTER / "laws_pl.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="PL", source="sejm_eli", source_url=ELI))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_pl.csv")

    bills = []
    for term in (7, 8, 9, 10):
        offset = 0
        while True:
            try:
                j = get_json(PROC.format(term=term), D / f"processes_term{term}_off{offset:05d}.json",
                             params={"limit": 5000, "offset": offset})
            except Exception as e:  # noqa: BLE001
                log.warning("pl processes term %d failed: %s", term, e)
                break
            items = j if isinstance(j, list) else j.get("items", [])
            for p in items:
                if p.get("documentTypeEnum") != "BILL":
                    continue
                title = p.get("title") or ""
                origin = next((o for pre, o in ORIGIN_PREFIX if title.lower().startswith(pre)), "unknown")
                if p.get("passed"):
                    outcome = "enacted"
                elif p.get("closureDate"):
                    outcome = "lapsed"
                else:
                    outcome = "pending"
                start = p.get("processStartDate") or p.get("documentDate")
                bills.append({
                    "country": "PL", "bill_id": f"term{term}/{p.get('number')}", "title": title,
                    "year_introduced": int(start[:4]) if start else None, "origin": origin, "outcome": outcome,
                    "date_introduced": start, "date_final": p.get("closureDate"), "instrument_type": "law",
                    "source": "sejm_processes", "term": term, "urgency": p.get("urgencyStatus"),
                })
            if len(items) < 5000:
                break
            offset += 5000
    bills_df = pd.DataFrame(bills)
    if len(bills_df):
        write_csv(bills_df[BILLS_COLUMNS + ["term", "urgency"]], INTER / "bills_pl.csv")


if __name__ == "__main__":
    main()
