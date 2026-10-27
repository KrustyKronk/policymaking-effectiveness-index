"""Laws: national row-level files + CAP fallbacks -> data/laws.csv, data/laws_coverage.csv,
data/intermediate/throughput_country_year.csv.

Precedence per country-year: national endpoint rows > aggregate counts (e.g. Bundestag PDFs) > CAP rows.
CAP and the other alternates are kept in laws_coverage.csv for splice checks."""
from __future__ import annotations

import re

import pandas as pd
import yaml

from pipeline.common import COUNTRIES, DATA, INTER, LAWS_COLUMNS, RAW, log, write_csv

PERIOD = range(1945, 2027)


def read_cap(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / "cap" / name, encoding_errors="replace", sep=None, engine="python")


def cap_rows() -> dict[str, pd.DataFrame]:
    """Row-level laws from CAP for the countries/years where it can fill gaps or cross-check."""
    out = {}

    def frame(cc, df, year, title, itype="law", date=None, origin="unknown", topic=None, src=None):
        return pd.DataFrame({
            "country": cc, "year": year.astype(int), "date": date if date is not None else year.astype(int).astype(str) + "-01-01",
            "instrument_type": itype, "origin": origin, "title": title, "length_words": None,
            "cap_topic": topic, "is_budget": False, "is_ratification": False, "source": src or f"cap_{cc.lower()}",
            "source_id": df.iloc[:, 0].astype(str), "source_url": "https://www.comparativeagendas.net/datasets_codebooks",
        })[LAWS_COLUMNS]

    uk = read_cap("UK_acts__uk_actsofparliament_v1_2_1.csv")
    out["UK"] = frame("UK", uk, uk.year, uk.description, topic=uk.majortopic)
    fr = read_cap("FR_laws__lois_79_13_short_7.csv")
    t = fr.type.astype(str).str.lower()
    out["FR"] = frame("FR", fr, fr.year, fr.titre, topic=fr.majortopic,
                      itype=t.map(lambda x: "ratification" if "ratif" in x or "convention" in x or "approbation" in x
                                  else "budget_law" if "financ" in x else "organic_law" if "organique" in x else "law"))
    de = read_cap("DE_laws__laws_1976-2005_website-release_2.5.csv")
    dy = pd.to_datetime(de.adoption_date, errors="coerce", dayfirst=True)
    de = de[dy.notna()]
    dy = dy[dy.notna()]
    out["DE"] = frame("DE", de, dy.dt.year, de.law_id.astype(str), date=dy.dt.date.astype(str), topic=de.cap_topic)
    it = read_cap("IT_laws__laws_italy_web.csv")
    itype = pd.Series("law", index=it.index)
    itype[it.filter_dl == 1] = "decree_law"
    itype[it.filter_budget == 1] = "budget_law"
    itype[it.filter_ratification == 1] = "ratification"
    out["IT"] = frame("IT", it, it.year, it.description, itype=itype, topic=it.majortopic)
    be = read_cap("BE_bills__CAP_Belgium_Bills_1988-2022.csv")
    be = be[be.accepted == 1]
    out["BE"] = frame("BE", be, be.year, be.title_short.fillna(be.description),
                      origin=be.bill_gov.map({1: "government", 0: "parliament"}), topic=be.majortopic, src="cap_be_bills")
    ie = read_cap("IE_bills__bills_for_cap.csv")
    ie = ie[ie.enacted == 1]
    yr = pd.to_numeric(ie.actyear_ds, errors="coerce").fillna(ie.year)
    out["IE"] = frame("IE", ie, yr, ie.description, origin=ie.billsource.astype(str).str.lower().map(
        lambda s: "government" if s.startswith("gov") else "parliament"), topic=ie.majortopic)
    es = pd.read_csv(RAW / "cap" / "ES_laws__Spain_Laws19802018_19.1.csv", encoding_errors="replace", sep=None, engine="python")
    out["ES"] = frame("ES", es, es.year, es.description, topic=es.majortopic,
                      itype=es.type_of_law.astype(str).str.lower().map(
                          lambda x: "decree_law" if "decree" in x or "decreto" in x else "organic_law" if "organic" in x or "orgánica" in x else "law"))
    return out


def main():
    rules = yaml.safe_load(open(RAW.parent / "pipeline" / "mappings.yaml", encoding="utf-8"))
    national: dict[str, pd.DataFrame] = {}
    for cc in COUNTRIES:
        f = INTER / f"laws_{cc.lower()}.csv"
        if f.exists():
            d = pd.read_csv(f, low_memory=False)
            if len(d) and cc == "SE":
                # Sweden: real decision dates exist only from 2017/18; assign every law to the calendar year its
                # riksmöte ends (Sep-Jun session; most decisions fall in the spring) so the series is consistent.
                dt_ = pd.to_datetime(d.date, errors="coerce")
                d["year"] = ((dt_.dt.year - (dt_.dt.month < 9).astype(int)) + 1).astype("Int64")
                d = d[d.year.notna()].astype({"year": int})
            if len(d):
                national[cc] = d
    counts = {}
    for cc in COUNTRIES:
        f = INTER / f"counts_{cc.lower()}.csv"
        if f.exists():
            counts[cc] = pd.read_csv(f)
    cap = cap_rows()

    chosen, coverage = [], []
    for cc in COUNTRIES:
        nat = national.get(cc)
        nat_years = set(nat.year.unique()) if nat is not None else set()
        cnt = counts.get(cc)
        cnt_law = None
        if cnt is not None:
            cl = cnt[cnt.instrument_type != "secondary"]
            cl = cl[cl.origin == "all"] if (cl.origin == "all").any() else cl  # avoid summing origin splits
            cnt_law = cl.groupby("year").n.sum()
        cp = cap.get(cc)
        for y in PERIOD:
            alts = {
                "national_rows": int((nat.year == y).sum()) if nat is not None else None,
                "counts": float(cnt_law.get(y)) if cnt_law is not None and y in cnt_law.index else None,
                "cap": int((cp.year == y).sum()) if cp is not None and (cp.year == y).any() else None,
            }
            if y in nat_years:
                src = "national_rows"
                chosen.append(nat[nat.year == y])
            elif alts["counts"] is not None and not (cnt is not None and nat is not None and set(cnt.source) <= set(nat.source)):
                src = "counts"
            elif cp is not None and (cp.year == y).any():
                src = "cap"
                chosen.append(cp[cp.year == y])
            else:
                src = None
            primary = alts.get(src) if src else None
            diff = None
            if src == "national_rows" and alts["cap"]:
                diff = round(100 * (alts["national_rows"] - alts["cap"]) / alts["cap"], 1)
            coverage.append({"country": cc, "year": y, "chosen": src, "n_chosen": primary, **alts, "pct_diff_vs_cap": diff,
                             "national_source": nat.source.iloc[0] if nat is not None else None})
    laws = pd.concat(chosen, ignore_index=True)[LAWS_COLUMNS]
    laws["year"] = laws.year.astype(int)

    # substantive flag
    lang = {cc: v["lang"] for cc, v in COUNTRIES.items()}
    rx = {l: re.compile("|".join(p), re.I) for l, p in rules["exclude_title_regex"].items()}
    excl = set(rules["exclude_types"])
    laws["is_budget"] = laws.is_budget.fillna(False).astype(bool) | (laws.instrument_type == "budget_law")
    laws["is_ratification"] = laws.is_ratification.fillna(False).astype(bool) | (laws.instrument_type == "ratification")
    title_hit = [bool(rx[lang[c]].search(str(t))) if isinstance(t, str) and lang.get(c) in rx else False for c, t in zip(laws.country, laws.title)]
    laws["is_substantive_v0"] = ~laws.instrument_type.isin(excl) & ~pd.Series(title_hit, index=laws.index)
    write_csv(laws, DATA / "laws.csv")
    cov = pd.DataFrame(coverage)
    write_csv(cov, DATA / "laws_coverage.csv")

    # country-year throughput
    g = laws.groupby(["country", "year"])
    tp = pd.DataFrame({
        "laws_total": g.size(),
        "laws_substantive": g.is_substantive_v0.sum(),
        "n_decree_law": g.apply(lambda d: (d.instrument_type == "decree_law").sum(), include_groups=False),
        "n_budget": g.is_budget.sum(), "n_ratification": g.is_ratification.sum(),
        "laws_source": g.source.agg(lambda s: "+".join(sorted(set(s)))),
    }).reset_index()
    parl = tp.laws_total - tp.n_decree_law
    tp["decree_share"] = (tp.n_decree_law / tp.laws_total).where(tp.laws_total > 0)
    tp["laws_parliamentary"] = parl
    # aggregate-only countries (e.g. DE from Bundestag statistics): no title -> substantive = total minus nothing
    covered = {(c, y) for c, y in zip(tp.country, tp.year)}
    for cc, cnt in counts.items():
        c = cnt[cnt.instrument_type != "secondary"]
        if cc in national:  # only fill years the row-level source does not cover, and only from a different source
            c = c[~c.year.map(lambda y: (cc, y) in covered) & ~c.source.isin(set(national[cc].source))]
        if c.empty:
            continue
        c = c[c.origin.isin(["all"])] if (c.origin == "all").any() else c
        agg = c.groupby("year").n.sum()
        for y, n in agg.items():
            if y in PERIOD:
                tp = tp[~((tp.country == cc) & (tp.year == y))]
                tp = pd.concat([tp, pd.DataFrame([{"country": cc, "year": y, "laws_total": n, "laws_substantive": n,
                                                   "n_decree_law": 0, "n_budget": None, "n_ratification": None,
                                                   "laws_source": c.source.iloc[0], "decree_share": 0.0,
                                                   "laws_parliamentary": n}])], ignore_index=True)
    # secondary legislation (UK SIs etc.)
    sec = []
    for cc, cnt in counts.items():
        s = cnt[cnt.instrument_type == "secondary"]
        sec.append(s.groupby("year").n.sum().rename("secondary_total").reset_index().assign(country=cc))
    if sec:
        tp = tp.merge(pd.concat(sec), on=["country", "year"], how="left")

    # government bill pass rates by year of introduction
    pr = []
    for cc in COUNTRIES:
        f = INTER / f"bills_{cc.lower()}.csv"
        if not f.exists():
            continue
        b = pd.read_csv(f, low_memory=False)
        b = b[b.outcome.isin(["enacted", "defeated", "withdrawn", "lapsed"]) & b.year_introduced.notna()]
        for (y, o), d in b.groupby([b.year_introduced.astype(int), "origin"]):
            pr.append({"country": cc, "year": y, "origin": o, "bills": len(d), "enacted": (d.outcome == "enacted").sum()})
    if pr:
        pr = pd.DataFrame(pr)
        piv = pr.pivot_table(index=["country", "year"], columns="origin", values=["bills", "enacted"], aggfunc="sum")
        piv.columns = [f"{a}_{b}" for a, b in piv.columns]
        piv = piv.reset_index()
        for o in ("government", "parliament"):
            if f"bills_{o}" in piv:
                piv[f"{o[:3]}_bill_pass_rate"] = piv[f"enacted_{o}"] / piv[f"bills_{o}"]
        keep = [c for c in piv.columns if c in ("country", "year", "gov_bill_pass_rate", "par_bill_pass_rate", "bills_government", "bills_parliament")]
        tp = tp.merge(piv[keep], on=["country", "year"], how="left")
    tp = tp.sort_values(["country", "year"])
    write_csv(tp, INTER / "throughput_country_year.csv")
    log.info("laws: %d rows; coverage by chosen source:\n%s", len(laws), cov.chosen.value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
