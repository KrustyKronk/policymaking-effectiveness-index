"""Scoring (params.yaml) -> data/pei_country_year.csv and data/pei_cabinet.csv.

P1 throughput   : within-country percentile (0-100) of the rolling mean of substantive laws, averaged with the
                  within-country percentile of the government-bill pass rate where available; minus decree penalty.
P2 fiscal       : 100 if the budget was in force on day 1, 50 if late within late_grace_days, 0 otherwise
                  (25 if late with unknown date). Cross-country comparable.
P3 stability    : 100 * (1 - caretaker_share) - snap_penalty * early_elections - pm_change_penalty * min(pm_changes, 2).
P4 implementation: null in v0 unless use_sanity_in_p4 (then WGI government-effectiveness score).
PEI             : weighted mean of the non-null pillars (weights renormalised); P1 = 50 (neutral) when no law
                  data exists for the country-year, flagged p1_imputed_no_laws.
pei_per_governing_day: same, but P1 uses substantive laws per 365 full-power days."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from pipeline.common import COUNTRIES, DATA, INTER, era_of, load_params, log, scoring_from, write_csv


def pct_within(s: pd.Series) -> pd.Series:
    """Percentile rank 0-100 within the series (ignores NaN)."""
    return s.rank(pct=True, method="average") * 100


def main():
    p = load_params()
    y0, y1 = p["period"]["start"], p["period"]["end"]
    base = pd.DataFrame([(c, y) for c in COUNTRIES for y in range(y0, y1 + 1)], columns=["country", "year"])
    st = pd.read_csv(INTER / "stability_country_year.csv")
    tp = pd.read_csv(INTER / "throughput_country_year.csv")
    bu = pd.read_csv(DATA / "budgets.csv").rename(columns={"fiscal_year": "year"})
    cx = pd.read_csv(DATA / "context.csv")
    df = (base.merge(st, on=["country", "year"], how="left")
          .merge(tp, on=["country", "year"], how="left")
          .merge(bu[["country", "year", "in_force_day1", "delay_days", "regime"]].rename(columns={"regime": "budget_regime"}),
                 on=["country", "year"], how="left")
          .merge(cx[["country", "year", "wgi_gov_eff_score"]], on=["country", "year"], how="left"))

    w = p["throughput"]["rolling_window"]
    metric = "laws_substantive" if p["throughput"]["substantive_only"] else "laws_total"
    df["laws_per_governing_year"] = df[metric] / df.full_power_days.where(df.full_power_days > 30) * 365
    df["era"] = [era_of(c, int(y)) for c, y in zip(df.country, df.year)]
    out = []
    for (cc, _era), g in df.groupby(["country", "era"]):
        g = g.sort_values("year").copy()
        g["laws_rolling"] = g[metric].rolling(w, center=True, min_periods=1).mean()
        g["laws_pgd_rolling"] = g.laws_per_governing_year.rolling(w, center=True, min_periods=1).mean()
        g["s_laws"] = pct_within(g.laws_rolling.where(g[metric].notna()))
        g["s_laws_pgd"] = pct_within(g.laws_pgd_rolling.where(g[metric].notna()))
        if "gov_bill_pass_rate" in g and g.gov_bill_pass_rate.notna().sum() >= 5:
            g["s_pass_rate"] = pct_within(g.gov_bill_pass_rate.rolling(w, center=True, min_periods=1).mean().where(g.gov_bill_pass_rate.notna()))
        else:
            g["s_pass_rate"] = np.nan
        out.append(g)
    df = pd.concat(out)
    pen = p["throughput"]["decree_penalty"] * df.decree_share.fillna(0)
    df["p1_throughput"] = (df[["s_laws", "s_pass_rate"]].mean(axis=1, skipna=True) - pen).clip(0, 100)
    df["p1_throughput_per_governing_day"] = (df[["s_laws_pgd", "s_pass_rate"]].mean(axis=1, skipna=True) - pen).clip(0, 100)

    grace = p["fiscal"]["late_grace_days"]
    def p2(r):
        if pd.isna(r.in_force_day1):
            return np.nan
        if r.in_force_day1 in (True, "True", "true"):
            return 100.0
        if r.budget_regime == "late":
            if pd.isna(r.delay_days):
                return 25.0
            return 50.0 if r.delay_days <= grace else 0.0
        return 0.0
    df["p2_fiscal"] = df.apply(p2, axis=1)

    sp, pp = p["stability"]["snap_penalty"], p["stability"]["pm_change_penalty"]
    df["p3_stability"] = (100 * (1 - df.caretaker_share) - sp * df.early_elections.fillna(0)
                          - pp * df.pm_changes.fillna(0).clip(upper=2)).clip(0, 100)
    df["transposition_deficit"] = np.nan
    df["p4_implementation"] = df.wgi_gov_eff_score if p["implementation"]["use_sanity_in_p4"] else np.nan

    wts = p["weights"]
    def composite(row, p1col):
        p1 = row[p1col] if pd.notna(row[p1col]) else 50.0  # neutral when no law data (flagged p1_imputed)
        vals = {"p1_throughput": p1, "p2_fiscal": row.p2_fiscal, "p3_stability": row.p3_stability,
                "p4_implementation": row.p4_implementation}
        num = sum(wts[k] * v for k, v in vals.items() if pd.notna(v))
        den = sum(wts[k] for k, v in vals.items() if pd.notna(v))
        return num / den if den else np.nan
    df["pei"] = df.apply(lambda r: composite(r, "p1_throughput"), axis=1)
    df["pei_per_governing_day"] = df.apply(lambda r: composite(r, "p1_throughput_per_governing_day"), axis=1)
    # Only score democratic years, and only when at least one pillar has real data (P1 imputation alone is not a score).
    pre = df.apply(lambda r: r.year < scoring_from(r.country), axis=1)
    empty = df[["p1_throughput", "p2_fiscal", "p3_stability", "p4_implementation"]].isna().all(axis=1)
    df.loc[pre | empty, ["pei", "pei_per_governing_day"]] = np.nan
    df.loc[pre, ["p1_throughput", "p1_throughput_per_governing_day", "p2_fiscal", "p3_stability"]] = np.nan
    df["coverage_flags"] = df.apply(lambda r: ";".join(f for f, ok in (
        ("p1_imputed_no_laws", pd.isna(r.get(metric))), ("no_budget", pd.isna(r.p2_fiscal)), ("no_stability", pd.isna(r.p3_stability)),
        ("no_pass_rate", pd.isna(r.s_pass_rate)), ("budget_structural_na", r.budget_regime == "structural_na"),
        ("switzerland_consensus_system", r.country == "CH"), ("partial_year", r.year >= 2026)) if ok), axis=1)
    df["panel_b"] = df.country.map(lambda c: COUNTRIES[c]["panel_b"])
    df["panel_c"] = True

    keep = ["country", "year", "era", "laws_total", "laws_substantive", "laws_parliamentary", "n_decree_law", "decree_share",
            "n_budget", "n_ratification", "secondary_total", "laws_source", "gov_bill_pass_rate", "par_bill_pass_rate",
            "full_power_days", "caretaker_days", "caretaker_share", "early_elections", "cab_defeats", "pm_changes",
            "cabinets_started", "n_parties", "minority", "pref_range", "in_force_day1", "delay_days", "budget_regime",
            "transposition_deficit", "wgi_gov_eff_score", "laws_rolling", "laws_per_governing_year", "s_laws", "s_laws_pgd",
            "s_pass_rate", "p1_throughput", "p1_throughput_per_governing_day", "p2_fiscal", "p3_stability",
            "p4_implementation", "pei", "pei_per_governing_day", "panel_b", "panel_c", "coverage_flags"]
    df = df[[c for c in keep if c in df.columns]].sort_values(["country", "year"])
    for c in df.select_dtypes("float").columns:
        df[c] = df[c].round(3)
    write_csv(df, DATA / "pei_country_year.csv")

    cab = pd.read_csv(DATA / "cabinets.csv", parse_dates=["start", "end"])
    rows = []
    for _, c in cab.iterrows():
        end = c.end if pd.notna(c.end) else pd.Timestamp(dt.date(2026, 7, 1))
        if end.year < y0:
            continue
        years = [y for y in range(max(c.start.year, y0), min(end.year, y1) + 1)
                 if (min(end, pd.Timestamp(y + 1, 1, 1)) - max(c.start, pd.Timestamp(y, 1, 1))).days >= 90]
        sub = df[(df.country == c.country) & df.year.isin(years)]
        if sub.empty:
            continue
        rows.append({"country": c.country, "cabinet_id": c.cabinet_id, "cabinet_name": c.cabinet_name, "pm": c.pm,
                     "start": c.start.date(), "end": c.end.date() if pd.notna(c.end) else None, "cabinet_type": c.cabinet_type,
                     "n_parties": c.n_parties, "years": f"{min(years)}-{max(years)}", "n_years": len(years),
                     "laws_substantive_per_year": sub.laws_substantive.mean(),
                     **{k: sub[k].mean() for k in ("p1_throughput", "p2_fiscal", "p3_stability", "pei", "pei_per_governing_day")}})
    pc = pd.DataFrame(rows)
    for col in pc.select_dtypes("float").columns:
        pc[col] = pc[col].round(1)
    write_csv(pc, DATA / "pei_cabinet.csv")
    log.info("scored %d country-years, %d cabinets", len(df), len(pc))


if __name__ == "__main__":
    main()
