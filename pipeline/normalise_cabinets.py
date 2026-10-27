"""REPDEM Basic -> data/cabinets.csv and data/intermediate/stability_country_year.csv.

Non-full-power days in a year = days covered by a caretaker cabinet (cab_caretaker == 1) plus days in the gap
between one cabinet's date_out and the next cabinet's date_in (the outgoing government acting 'en funciones').
Campaign periods before an election are NOT counted (v0)."""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from pipeline.common import COUNTRIES, DATA, INTER, NO_REPDEM, RAW, load_params, log, write_csv

LAST_OBS = dt.date(2026, 7, 1)  # REPDEM Basic v2026.07 cut-off


def pm_of(cab_name: str) -> str:
    return re.sub(r"\s+[IVXL]+$", "", str(cab_name)).strip()


# Cabinets after ParlGov's 2024 freeze, for the three countries REPDEM does not cover (hand-entered, sourced).
MANUAL_CABINETS = [
    {"country": "CY", "cabinet_name": "Christodoulides I", "start": "2023-03-01",
     "note": "President Christodoulides sworn in 28 Feb 2023 (presidential system: cabinet = president's council of ministers)"},
    {"country": "CH", "cabinet_name": "Bundesrat 2023", "start": "2023-12-13",
     "note": "Federal Council elected by the Federal Assembly on 13 Dec 2023 after the Oct 2023 election"},
]


def parlgov_fallback() -> pd.DataFrame:
    """CH, CY, MT from ParlGov view_cabinet (one row per cabinet), end = next cabinet's start.
    Early elections and confidence defeats are not coded in ParlGov stable: left null."""
    pg = pd.read_csv(RAW / "parlgov" / "view_cabinet.tab", sep="\t", low_memory=False)
    rows = []
    for cc in sorted(NO_REPDEM):
        g = pg[pg.country_name == COUNTRIES[cc]["parlgov"]].copy()
        parties = g.groupby("cabinet_id").party_name_short.agg(lambda s: "; ".join(sorted(set(map(str, s)))))
        g = g.drop_duplicates("cabinet_id").sort_values("start_date")
        recs = [{"country": cc, "cabinet_id": f"pg{r.cabinet_id}", "cabinet_name": r.cabinet_name,
                 "start": pd.Timestamp(r.start_date).date(), "caretaker": int(r.caretaker or 0),
                 "parties": parties.get(r.cabinet_id, "")} for r in g.itertuples()]
        recs += [{"country": m["country"], "cabinet_id": f"manual_{m['country']}_{m['start']}", "cabinet_name": m["cabinet_name"],
                  "start": pd.Timestamp(m["start"]).date(), "caretaker": 0, "parties": ""} for m in MANUAL_CABINETS if m["country"] == cc]
        recs.sort(key=lambda r: r["start"])
        for i, r in enumerate(recs):
            r["end"] = recs[i + 1]["start"] if i + 1 < len(recs) else None
            r["pm"] = None if cc == "CH" else pm_of(r["cabinet_name"])
            rows.append(r)
    out = pd.DataFrame(rows)
    out = out.assign(n_parties=out.parties.str.count(";") + 1, seat_share=None,
                     cabinet_type=out.caretaker.map({1: "caretaker"}).fillna("coalition_majority" if False else "unknown"),
                     formation_days=None, term_reason="unknown", early_election=pd.NA, cab_defeat=pd.NA,
                     pref_range=None, source="parlgov_2024+manual")
    out.loc[out.country == "CH", "cabinet_type"] = "collegial_all_party"
    return out


def main():
    r = pd.read_csv(RAW / "repdem" / "repdem-basic-3.csv", low_memory=False)
    name_to_cc = {v["repdem"]: k for k, v in COUNTRIES.items()}
    r = r[r.country_name.isin(name_to_cc)].copy()
    r["country"] = r.country_name.map(name_to_cc)
    r["start"] = pd.to_datetime(r.date_in).dt.date
    r["end"] = pd.to_datetime(r.date_out).dt.date
    r = r.sort_values(["country", "start"])

    def reason(x):
        if x.get("term_disc_earlyelec") == 1:
            return "early_election"
        if x.get("term_disc_cabdefeat") == 1:
            return "cabinet_defeat"
        if x.get("term_tech_regelec") == 1:
            return "regular_election"
        if x.get("term_disc_voluntary") == 1:
            return "voluntary"
        return "other" if pd.notna(x.get("date_out")) else "in_office"

    cab = pd.DataFrame({
        "country": r.country, "cabinet_id": r.cab_id, "cabinet_name": r.cab_name, "pm": r.cab_name.map(pm_of),
        "start": r.start, "end": r.end,
        "parties": r[[f"cab_party{i}" for i in range(1, 9)]].apply(lambda s: "; ".join(str(v) for v in s if pd.notna(v)), axis=1),
        "n_parties": r.cab_num_parties, "seat_share": r.get("cab_strength_lower"),
        "cabinet_type": [("caretaker" if c == 1 else "minority" if m == 1 else "coalition_majority" if n > 1 else "single_majority")
                         for c, m, n in zip(r.cab_caretaker, r.cab_minority, r.cab_num_parties)],
        "caretaker": r.cab_caretaker.fillna(0).astype(int), "formation_days": r.form_duration,
        "term_reason": r.apply(reason, axis=1), "early_election": r.term_disc_earlyelec.fillna(0).astype(int),
        "cab_defeat": r.term_disc_cabdefeat.fillna(0).astype(int), "pref_range": r.cab_prefrange,
        "source": "repdem_basic_2026_07",
    })
    cab = pd.concat([cab, parlgov_fallback()], ignore_index=True).sort_values(["country", "start"])
    write_csv(cab, DATA / "cabinets.csv")

    p = load_params()["period"]
    rows = []
    for cc, g in cab.groupby("country"):
        g = g.sort_values("start").reset_index(drop=True)
        # day -> status: 'full' | 'caretaker' | 'gap'
        status: dict[dt.date, str] = {}
        for i, c in g.iterrows():
            end = c.end if pd.notna(c.end) else LAST_OBS
            d = c.start
            while d < end:
                status[d] = "caretaker" if c.caretaker == 1 else "full"
                d += dt.timedelta(days=1)
            if i + 1 < len(g):
                d, nxt = end, g.loc[i + 1, "start"]
                while d < nxt:
                    status.setdefault(d, "gap")
                    d += dt.timedelta(days=1)
        for y in range(1945, 2027):
            days = [dt.date(y, 1, 1) + dt.timedelta(days=k) for k in range((dt.date(y + 1, 1, 1) - dt.date(y, 1, 1)).days)]
            observed = [d for d in days if d < LAST_OBS]
            if not observed:
                continue
            care = sum(1 for d in observed if status.get(d) in ("caretaker", "gap"))
            ended = g[g.end.notna() & g.end.map(lambda e: pd.notna(e) and e.year == y)]
            started = g[g.start.map(lambda s: s.year == y)]
            pms_started = 0
            for _, c in started.iterrows():
                prev = g[g.start < c.start].tail(1)
                if len(prev) and prev.iloc[0].pm != c.pm and c.caretaker == 0:
                    pms_started += 1
            rows.append({
                "country": cc, "year": y, "days_observed": len(observed),
                "full_power_days": len(observed) - care, "caretaker_days": care,
                "caretaker_share": care / len(observed),
                "early_elections": (None if cc in NO_REPDEM else int(ended.early_election.sum())),
                "cab_defeats": (None if cc in NO_REPDEM else int(ended.cab_defeat.sum())),
                "cabinets_started": len(started), "pm_changes": (None if cc == "CH" else pms_started),
                "stability_source": "parlgov_2024+manual" if cc in NO_REPDEM else "repdem_basic_2026_07",
                "minority_days_share": sum(1 for d in observed for _ in [0]
                                           if any((c.start <= d) and (pd.isna(c.end) or d < c.end) and c.cabinet_type == "minority"
                                                  for _, c in g.iterrows())) / len(observed) if False else None,
                "n_parties": g[g.start <= dt.date(y, 7, 1)].tail(1).n_parties.squeeze() if len(g[g.start <= dt.date(y, 7, 1)]) else None,
                "minority": int(g[g.start <= dt.date(y, 7, 1)].tail(1).cabinet_type.squeeze() == "minority") if len(g[g.start <= dt.date(y, 7, 1)]) else None,
                "pref_range": g[g.start <= dt.date(y, 7, 1)].tail(1).pref_range.squeeze() if len(g[g.start <= dt.date(y, 7, 1)]) else None,
            })
    st = pd.DataFrame(rows).drop(columns=["minority_days_share"])
    write_csv(st, INTER / "stability_country_year.csv")
    log.info("cabinets: %d rows; stability: %d country-years", len(cab), len(st))


if __name__ == "__main__":
    main()
