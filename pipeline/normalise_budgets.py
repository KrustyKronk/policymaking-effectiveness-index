"""Hand-compiled budget-timeliness tables (pipeline/budget_inputs/*.csv, researched 16 Oct 2026, one source per row)
-> data/budgets.csv. Adds delay_days and the Open Budget Survey approval-timing letter (q107 in 2015, q109 from
2017) as a cross-check. Note: an OBS round assesses the budget current at survey time, so the letter is joined to
the fiscal year before the round (round 2017 -> FY 2016; approximate)."""
from __future__ import annotations

import pandas as pd

from pipeline.common import COUNTRIES, DATA, ISO3_TO_CC, RAW, fy_start_for, log, write_csv

INPUTS = RAW.parent / "pipeline" / "budget_inputs"


def main():
    frames = [pd.read_csv(f, dtype=str) for f in sorted(INPUTS.glob("*.csv"))]
    b = pd.concat(frames, ignore_index=True)
    names = {v["name"].upper(): k for k, v in COUNTRIES.items()}
    b["country"] = b.country.str.strip().map(lambda c: c if c in COUNTRIES else names.get(c.upper(), c))
    b = b[b.country.isin(COUNTRIES)].drop_duplicates(["country", "fiscal_year"], keep="last")
    b["fiscal_year"] = b.fiscal_year.astype(int)
    b["in_force_day1"] = b.in_force_day1.str.lower().map({"true": True, "false": False}).astype(object)
    blank = b.fy_start.isna() | ~b.fy_start.astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")
    b.loc[blank, "fy_start"] = [fy_start_for(c, y) for c, y in zip(b.country[blank], b.fiscal_year[blank])]
    for c in ("adoption_date", "promulgation_date", "fy_start"):
        b[c] = pd.to_datetime(b[c].where(b[c].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)), errors="coerce")
    b["regime"] = b.regime.where(b.regime.isin(["on_time", "late", "rolled_over", "provisional", "none", "structural_na"]))
    effective = b.promulgation_date.fillna(b.adoption_date)
    delay = (effective - b.fy_start).dt.days
    b["delay_days"] = delay.where(b.regime == "late")
    b.loc[b.regime.isin(["rolled_over", "none", "provisional"]), "delay_days"] = 365
    b.loc[b.regime == "on_time", "delay_days"] = 0
    b.loc[b.regime == "structural_na", ["in_force_day1", "delay_days"]] = [None, None]

    obs = []
    for sheet, q in (("Scores+Letters_2006-2015", "q107_letter"), ("Scores+Letters_2017-2025", "q109_letter")):
        d = pd.read_excel(RAW / "obs" / "OBS_Full_Timeseries_2006_2025.xlsx", sheet_name=sheet, header=3)
        if q not in d:
            continue
        d = d[d.ISO.isin(ISO3_TO_CC)]
        if sheet.startswith("Scores+Letters_2006"):
            d = d[d.Year == 2015]
        obs.append(pd.DataFrame({"country": d.ISO.map(ISO3_TO_CC), "fiscal_year": d.Year.astype(int) - 1, "obs_approval_letter": d[q]}))
    if obs:
        b = b.merge(pd.concat(obs), on=["country", "fiscal_year"], how="left")
    cols = ["country", "fiscal_year", "fy_start", "in_force_day1", "adoption_date", "promulgation_date", "delay_days",
            "regime", "confidence", "obs_approval_letter", "source_url", "note"]
    for c in cols:
        if c not in b:
            b[c] = None
    b = b[cols].sort_values(["country", "fiscal_year"])
    for c in ("fy_start", "adoption_date", "promulgation_date"):
        b[c] = b[c].dt.date
    write_csv(b, DATA / "budgets.csv")
    log.info("budgets: %d rows, %d with in_force_day1 known; countries: %s", len(b), b.in_force_day1.notna().sum(),
             sorted(b.country.unique()))


if __name__ == "__main__":
    main()
