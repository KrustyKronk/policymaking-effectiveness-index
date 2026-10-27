"""Sanity / context indices -> data/context.csv (scored = false).
WGI Government Effectiveness, POLCON III/V, DPI checks, SGI Executive Capacity (2014, 2022 levels), iREG RIA on
primary laws (2014/17/21/24 editions)."""
from __future__ import annotations

import json

import pandas as pd

from pipeline.common import COUNTRIES, DATA, ISO3_TO_CC, NAME_TO_CC, RAW, write_csv


def yr(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    return df.dropna(subset=["year"]).astype({"year": int})


def main():
    years = pd.MultiIndex.from_product([list(COUNTRIES), range(1950, 2026)], names=["country", "year"])
    ctx = pd.DataFrame(index=years).reset_index()

    for ind, col in (("GOV_WGI_GE.EST", "wgi_gov_eff"), ("GOV_WGI_GE.SC", "wgi_gov_eff_score")):
        j = json.loads((RAW / "wgi" / f"{ind}.json").read_text())
        w = pd.DataFrame([{"country": ISO3_TO_CC.get(x["countryiso3code"]), "year": int(x["date"]), col: x["value"]}
                          for x in j[1] if x["countryiso3code"] in ISO3_TO_CC])
        ctx = ctx.merge(yr(w), on=["country", "year"], how="left")

    pc = pd.read_excel(RAW / "polcon" / "POLCON_2025_FINALPOSTED.xlsx", sheet_name="Data",
                       usecols=["ctrynm", "year", "POLCONIII_2025", "POLCONV_2025"])
    alias = {"United Kingdom": "UK", "UK": "UK", "Great Britain": "UK", "Czech Republic": "CZ", "Czechia": "CZ",
             "Slovak Republic": "SK", "Slovakia": "SK", "Republic of Cyprus": "CY"}
    pc["country"] = pc.ctrynm.map(lambda n: NAME_TO_CC.get(str(n).strip(), alias.get(str(n).strip())))
    pc = pc.dropna(subset=["country"]).rename(columns={"POLCONIII_2025": "polcon3", "POLCONV_2025": "polcon5"})
    ctx = ctx.merge(yr(pc[["country", "year", "polcon3", "polcon5"]]).drop_duplicates(["country", "year"]), on=["country", "year"], how="left")

    dpi = pd.read_csv(RAW / "dpi" / "DPI 2023 (CSV Version).csv", encoding="latin-1", low_memory=False)
    dpi["country"] = dpi.ifs.map(ISO3_TO_CC)
    dpi["dpi_checks"] = pd.to_numeric(dpi.checks, errors="coerce").where(lambda s: s >= 0)
    ctx = ctx.merge(yr(dpi.dropna(subset=["country"])[["country", "year", "dpi_checks"]]), on=["country", "year"], how="left")

    sg = []
    for sheet, sgi_year in (("SGI2014", 2014), ("SGI2022", 2022)):
        s = pd.read_excel(RAW / "sgi" / "SGI2022_TimeSeries_Governance.xlsx", sheet_name=sheet, header=None)
        for _, row in s.iloc[1:].iterrows():
            cc = NAME_TO_CC.get(str(row[0]).strip(), alias.get(str(row[0]).strip()))
            if cc:
                sg.append({"country": cc, "year": sgi_year, "sgi_exec_capacity": row[4]})
    ctx = ctx.merge(yr(pd.DataFrame(sg)), on=["country", "year"], how="left")

    ir = pd.read_csv(RAW / "ireg" / "ireg_2025.csv")
    ir = ir[(ir.Measure == "Regulatory Impact Assessment") & (ir["Regulatory category"] == "Primary laws")]
    ir = ir.assign(country=ir.REF_AREA.map(ISO3_TO_CC)).dropna(subset=["country"])
    ir = ir.groupby(["country", "TIME_PERIOD"]).OBS_VALUE.sum().reset_index().rename(columns={"TIME_PERIOD": "year", "OBS_VALUE": "ireg_ria_primary"})
    ctx = ctx.merge(yr(ir), on=["country", "year"], how="left")
    ctx["scored"] = False
    write_csv(ctx, DATA / "context.csv")


if __name__ == "__main__":
    main()
