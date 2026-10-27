"""United Kingdom.
- legislation.gov.uk Atom feeds: enacted Public General Acts (row level, 1950-2025; one feed per calendar year,
  /ukpga/{year}/data.feed, 20 entries per page) and SI yearly totals (2000-2025).
  Pre-1963 numbering: until the Acts of Parliament Numbering and Citation Act 1962, chapters were numbered
  within the regnal-year session, not the calendar year (e.g. 14 Geo. 6 c. 39 = Public Utilities Street Works
  Act 1950; the feed id is /ukpga/Geo6/14/39). Rows are still assigned to the calendar year of the feed (the
  year of Royal Assent), but (year, number) is not unique before 1963: a calendar year can hold two regnal
  sessions with overlapping chapter numbers. source_id (the feed id URI) is unique throughout.
- UK Parliament Bills API: bills with type (government / private members / ...), isAct, defeated, withdrawn,
  introduced session -> origin and pass rates (2006 onward). Acts before 2006 therefore have origin unknown."""
from __future__ import annotations

import datetime as dt
import json
import re
import time

import pandas as pd
from lxml import etree

from pipeline.common import (BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, get_json, log,
                             norm_title, write_csv)

BASE = "https://www.legislation.gov.uk"
BILLS = "https://bills-api.parliament.uk/api/v1"
YEARS = range(1950, 2026)        # Public General Acts (row level + yearly counts)
SI_YEARS = range(2000, 2026)     # SI totals: legislation.gov.uk is not complete for older SIs
D = RAW / "uk"
PAUSE = 1.0                      # seconds between live requests


def polite_get(url, dest, **kw) -> bytes:
    """common.get with a pause after every live request and a long back-off on HTTP 429."""
    if dest is not None and dest.exists():
        return dest.read_bytes()
    for attempt in range(4):
        try:
            out = get(url, dest, **kw)
            time.sleep(PAUSE)
            return out
        except RuntimeError as e:
            if "HTTP 429" in str(e) and attempt < 3:
                wait = 30 * 2 ** attempt
                log.warning("uk: 429 from %s, sleeping %ds", url, wait)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"uk: gave up on {url}")


def facet_year_totals(kind: str) -> dict[int, int]:
    xml = get(f"{BASE}/{kind}/data.feed", D / f"{kind}_facets.feed")
    root = etree.fromstring(xml)
    out = {}
    for e in root.iter("{http://www.legislation.gov.uk/namespaces/legislation}facetYear"):
        out[int(e.get("year"))] = int(e.get("total"))
    return out


def _text(e, name):
    x = e.find(f"{{http://www.w3.org/2005/Atom}}{name}")
    return x.text if x is not None else None


def acts_for_year(year: int) -> list[dict]:
    rows, page, more = [], 1, 1
    while page <= more:
        xml = polite_get(f"{BASE}/ukpga/{year}/data.feed", D / "ukpga" / f"{year}_p{page}.feed", params={"page": page})
        root = etree.fromstring(xml)
        mp = root.find("{http://www.legislation.gov.uk/namespaces/legislation}morePages")
        more = int(mp.text) if mp is not None and mp.text else 1
        for en in root.iter("{http://www.w3.org/2005/Atom}entry"):
            dates = {}
            for el in en.iter():
                for k, v in el.attrib.items():
                    if k.lower().endswith("date") or k == "Date":
                        dates[etree.QName(el).localname] = v
            number = None
            for el in en.iter("{http://www.legislation.gov.uk/namespaces/metadata}Number"):
                number = el.get("Value")
            rows.append({
                "id": _text(en, "id"), "title": _text(en, "title"), "published": _text(en, "published"),
                "updated": _text(en, "updated"), "number": number, "dates": json.dumps(dates), "year": year,
            })
        page += 1
    return rows


def fetch_bills() -> tuple[list[dict], dict]:
    types = get_json(f"{BILLS}/BillTypes", D / "bills" / "bill_types.json")
    items, skip, total = [], 0, None
    while total is None or skip < total:
        j = get_json(f"{BILLS}/Bills", D / "bills" / f"bills_skip{skip:05d}.json", params={"Take": 100, "Skip": skip})
        total = j["totalResults"]
        items.extend(j["items"])
        skip += 100
    return items, types


def session_years(items: list[dict]) -> dict[int, int]:
    """Map sessionId -> calendar year the session started, from the earliest sitting date seen for it."""
    first: dict[int, dt.date] = {}
    for b in items:
        cs = b.get("currentStage") or {}
        sid = cs.get("sessionId")
        for s in cs.get("stageSittings") or []:
            d = dt.date.fromisoformat(s["date"][:10])
            if sid is not None and (sid not in first or d < first[sid]):
                first[sid] = d
    years = {sid: d.year for sid, d in first.items()}
    # anchors from the parliament website for sessions with few sittings on record
    years.setdefault(36, 2021)
    years.setdefault(40, 2025)
    return years


def main():
    # 1. yearly totals (Acts and SIs) straight from the facets
    totals_pga = facet_year_totals("ukpga")
    totals_si = facet_year_totals("uksi")
    counts = []
    for y in YEARS:
        counts.append({"country": "UK", "year": y, "instrument_type": "law", "origin": "all",
                       "n": totals_pga.get(y), "source": "legislation_gov_uk", "source_url": f"{BASE}/ukpga/{y}"})
    for y in SI_YEARS:
        counts.append({"country": "UK", "year": y, "instrument_type": "secondary", "origin": "all",
                       "n": totals_si.get(y), "source": "legislation_gov_uk", "source_url": f"{BASE}/uksi/{y}"})
    write_csv(pd.DataFrame(counts, columns=COUNTS_COLUMNS), INTER / "counts_uk.csv")

    # 2. row-level Acts
    acts = []
    for y in YEARS:
        try:
            acts.extend(acts_for_year(y))
        except Exception as e:  # noqa: BLE001
            log.warning("uk acts %d failed (kept going): %s", y, e)
            continue
        if len(acts) and len(acts) % 200 < 60:
            log.info("uk acts: %d rows so far (year %d)", len(acts), y)
    acts_df = pd.DataFrame(acts)
    acts_df.to_csv(D / "ukpga_entries.csv", index=False)
    for y, n in totals_pga.items():
        if y in YEARS and (acts_df["year"] == y).sum() != n:
            log.warning("uk %d: feed says %d acts, parsed %d", y, n, (acts_df["year"] == y).sum())

    # 3. bills -> origin / outcome
    try:
        items, types = fetch_bills()
    except Exception as e:  # noqa: BLE001
        log.warning("uk bills API failed (laws written with origin unknown): %s", e)
        items, types = [], []
    types = types.get("items", types) if isinstance(types, dict) else types
    tmap = {t["id"]: t for t in types}
    syears = session_years(items)
    bills = []
    for b in items:
        t = tmap.get(b["billTypeId"], {})
        cat = (t.get("category") or "").lower()          # 'public' / 'private'
        tname = (t.get("name") or "").lower()
        origin = ("government" if tname.startswith("government") or tname.startswith("supply")
                  else "parliament" if tname.startswith("private members") else "other")
        if b["isAct"]:
            outcome = "enacted"
        elif b["introducedSessionId"] == 40 or 40 in (b.get("includedSessionIds") or []):
            outcome = "pending"
        elif b.get("isDefeated"):
            outcome = "defeated"
        elif b.get("billWithdrawn"):
            outcome = "withdrawn"
        else:
            outcome = "lapsed"
        bills.append({
            "country": "UK", "bill_id": b["billId"], "title": b["shortTitle"],
            "year_introduced": syears.get(b["introducedSessionId"]), "origin": origin, "outcome": outcome,
            "date_introduced": None, "date_final": None,
            "instrument_type": "other" if cat == "private" or "hybrid" in tname else "law",
            "source": "uk_bills_api", "bill_type": t.get("name"), "session_id": b["introducedSessionId"],
        })
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS + ["bill_type", "session_id"])
    if len(bills_df):
        write_csv(bills_df, INTER / "bills_uk.csv")

    # 4. laws.csv rows: Acts with origin matched from enacted bills by normalised title
    origin_by_title = {norm_title(r["title"]): r["origin"] for r in bills if r["outcome"] == "enacted"}
    laws = []
    for r in acts:
        dates = json.loads(r["dates"])
        date = dates.get("EnactmentDate") or dates.get("Date") or (r["published"] or "")[:10] or f"{r['year']}-01-01"
        title = r["title"] or ""
        is_budget = bool(re.match(r"^(Finance|Supply and Appropriation|Appropriation|Consolidated Fund)", title))
        laws.append({
            "country": "UK", "year": r["year"], "date": date[:10],
            "instrument_type": "budget_law" if is_budget else "law",
            "origin": origin_by_title.get(norm_title(title), "unknown" if r["year"] >= 2006 else "unknown"),
            "title": title, "length_words": None, "cap_topic": None, "is_budget": is_budget,
            "is_ratification": bool(re.search(r"ratification", title, re.I)),
            "source": "legislation_gov_uk", "source_id": r["id"], "source_url": r["id"],
        })
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS)
    write_csv(laws_df, INTER / "laws_uk.csv")
    log.info("uk: %d acts, origin known for %d; %d bills", len(laws_df), (laws_df.origin != "unknown").sum(), len(bills_df))


if __name__ == "__main__":
    main()
