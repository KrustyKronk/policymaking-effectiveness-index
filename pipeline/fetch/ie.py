"""Ireland: Oireachtas API, all bills by bill_year 1920-2026 -> bills_ie.csv; enacted ones -> laws_ie.csv
(year = year the Act was signed, act.dateSigned), 1922-2026.

The API's bill_year filter selects on the bill's own year (billYear, the year in "Court Officers Bill, 1950" and
in the bill URI /bill/1950/41), i.e. the year the bill was introduced/numbered, NOT the act year: of the 42 bills
with bill_year=1950, 24 were signed in 1950 and 5 in 1951 (the rest lapsed/withdrawn/defeated). Laws are keyed on
act.dateSigned, so a complete act year Y needs bill years up to Y (fetched from 1920 so 1922 is complete).
Cross-check: enacted per act year vs CAP Ireland bills (enacted == 1, actyear_ds), 1980-1999 ->
raw/ie/cap_check.csv."""
from __future__ import annotations

import re
import time

import pandas as pd

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get_json, log, write_csv

D = RAW / "ie"
API = "https://api.oireachtas.ie/v1/legislation"
BILL_YEARS = range(1920, 2027)
LAW_YEARS = (1922, 2026)
PAUSE = 0.5


def polite_get_json(url, dest, **kw):
    """get_json with a pause after every live request and a long back-off on HTTP 429."""
    live = not dest.exists()
    for attempt in range(4):
        try:
            out = get_json(url, dest, **kw)
            if live:
                time.sleep(PAUSE)
            return out
        except RuntimeError as e:
            if "HTTP 429" in str(e) and attempt < 3:
                log.warning("ie: 429, sleeping %ds", 30 * 2 ** attempt)
                time.sleep(30 * 2 ** attempt)
                continue
            raise


def bills_for_year(year: int) -> list[dict]:
    out, skip = [], 0
    while True:
        j = polite_get_json(API, D / f"bills_{year}_skip{skip:04d}.json",
                     params={"bill_year": year, "limit": 500, "skip": skip})
        res = j.get("results", [])
        out.extend(r["bill"] for r in res)
        total = j["head"]["counts"]["billCount"]
        skip += 500
        if skip >= total or not res:
            break
    return out


def first_event_date(b: dict) -> str | None:
    dates = []
    for ev in b.get("events") or []:
        for d in (ev.get("event") or {}).get("dates") or []:
            if d.get("date"):
                dates.append(d["date"][:10])
    return min(dates) if dates else None


def main():
    bills, laws = [], []
    for year in BILL_YEARS:
        try:
            items = bills_for_year(year)
        except Exception as e:  # noqa: BLE001
            log.warning("ie bill_year %d failed (kept going): %s", year, e)
            continue
        for b in items:
            src = (b.get("source") or "").lower()
            origin = "government" if src.startswith("gov") else ("parliament" if src else "unknown")
            status = (b.get("status") or "").lower()
            outcome = {"enacted": "enacted", "defeated": "defeated", "withdrawn": "withdrawn",
                       "lapsed": "lapsed", "rejected": "defeated"}.get(status, "pending")
            act = b.get("act") or {}
            itype = "other" if (b.get("billType") or "").lower() == "private" else "law"
            bills.append({
                "country": "IE", "bill_id": b.get("uri"), "title": b.get("shortTitleEn"),
                "year_introduced": int(b.get("billYear") or year), "origin": origin, "outcome": outcome,
                "date_introduced": first_event_date(b), "date_final": act.get("dateSigned"),
                "instrument_type": itype, "source": "oireachtas_api",
            })
            if outcome == "enacted" and act.get("dateSigned"):
                title = act.get("shortTitleEn") or b.get("shortTitleEn") or ""
                is_budget = bool(re.match(r"^(Finance|Appropriation|Central Fund)", title))
                laws.append({
                    "country": "IE", "year": int(act["dateSigned"][:4]), "date": act["dateSigned"][:10],
                    "instrument_type": "budget_law" if is_budget else itype, "origin": origin, "title": title,
                    "length_words": None, "cap_topic": None, "is_budget": is_budget,
                    "is_ratification": bool(re.search(r"ratification", title, re.I)),
                    "source": "oireachtas_api", "source_id": act.get("uri"), "source_url": act.get("statutebookURI"),
                })
        if year % 10 == 0 or year >= 1997:
            log.info("ie %d: %d bills, %d enacted", year, len(items), sum(1 for b in items if (b.get('status') or '').lower() == 'enacted'))
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS)
    write_csv(bills_df, INTER / "bills_ie.csv")
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).drop_duplicates("source_id").sort_values("date")
    laws_df = laws_df[laws_df.year.between(*LAW_YEARS)]
    write_csv(laws_df, INTER / "laws_ie.csv")
    cap_check(laws_df)
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="IE", source="oireachtas_api", source_url=API))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_ie.csv")


def cap_check(laws_df: pd.DataFrame) -> None:
    """Enacted per act year, Oireachtas API vs CAP Ireland bills (enacted == 1, actyear_ds), 1980-1999."""
    try:
        cap = pd.read_csv(RAW / "cap" / "IE_bills__bills_for_cap.csv", encoding_errors="replace", sep=None, engine="python")
        cap = cap[cap.enacted == 1]
        cy = pd.to_numeric(cap.actyear_ds, errors="coerce").value_counts()
        api_all = laws_df.year.value_counts()
        api_pub = laws_df[laws_df.instrument_type != "other"].year.value_counts()
        rows = []
        for y in range(1980, 2000):
            c = int(cy.get(y, 0))
            a, p = int(api_all.get(y, 0)), int(api_pub.get(y, 0))
            rows.append({"year": y, "cap_enacted": c, "api_all": a, "api_public": p,
                         "pct_diff_all": round(100 * (a - c) / c, 1) if c else None,
                         "pct_diff_public": round(100 * (p - c) / c, 1) if c else None})
        df = pd.DataFrame(rows)
        df.to_csv(D / "cap_check.csv", index=False)
        log.info("ie CAP check 1980-1999 (max |%%diff| all %.1f, public %.1f):\n%s",
                 df.pct_diff_all.abs().max(), df.pct_diff_public.abs().max(), df.to_string(index=False))
    except Exception as e:  # noqa: BLE001
        log.warning("ie CAP check skipped: %s", e)


if __name__ == "__main__":
    main()
