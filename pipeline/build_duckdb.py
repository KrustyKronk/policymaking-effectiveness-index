"""Load the tidy CSVs into pei.duckdb and create one view per hypothesis (H1-H5 in BRAINSTORM.md)."""
from __future__ import annotations

import duckdb

from pipeline.common import DATA, ROOT, log

TABLES = ["laws", "laws_coverage", "cabinets", "budgets", "context", "pei_country_year", "pei_cabinet"]

VIEWS = {
    # H1: throughput levels and composition, last 10 full years (counts are NOT cross-country comparable)
    "v_h1_throughput": """
        SELECT country,
               round(avg(laws_substantive), 1)              AS substantive_laws_per_year_2016_25,
               round(avg(laws_parliamentary), 1)            AS parliamentary_laws_per_year_2016_25,
               round(avg(n_decree_law), 1)                  AS decree_laws_per_year_2016_25,
               round(avg(decree_share), 3)                  AS decree_share_2016_25,
               round(avg(gov_bill_pass_rate), 3)            AS gov_bill_pass_rate_2016_25,
               round(avg(p1_throughput), 1)                 AS p1_vs_own_history_2016_25
        FROM pei_country_year WHERE year BETWEEN 2016 AND 2025 GROUP BY country ORDER BY country""",
    # H2: time lost to caretaker / formation / repeat elections
    "v_h2_time_lost": """
        SELECT country,
               round(avg(caretaker_share) * 100, 1)                         AS pct_days_not_full_power_2000_25,
               round(avg(CASE WHEN year >= 2015 THEN caretaker_share END) * 100, 1) AS pct_days_not_full_power_2015_25,
               sum(early_elections)                                          AS early_elections_2000_25,
               sum(pm_changes)                                               AS pm_changes_2000_25,
               sum(cab_defeats)                                              AS cabinets_ended_by_defeat_2000_25
        FROM pei_country_year GROUP BY country ORDER BY pct_days_not_full_power_2000_25 DESC""",
    # H3: budgets
    "v_h3_budgets": """
        SELECT country,
               count(*) FILTER (WHERE in_force_day1 IS NOT NULL)            AS years_known,
               count(*) FILTER (WHERE in_force_day1 = false)                AS years_late_or_none,
               count(*) FILTER (WHERE regime = 'rolled_over')               AS years_no_budget_at_all,
               round(avg(delay_days) FILTER (WHERE regime = 'late'), 0)     AS avg_delay_days_when_late,
               string_agg(CAST(fiscal_year AS VARCHAR), ', ' ORDER BY fiscal_year) FILTER (WHERE in_force_day1 = false) AS late_years
        FROM budgets WHERE fiscal_year BETWEEN 2000 AND 2026 GROUP BY country ORDER BY years_late_or_none DESC""",
    # H4: has it got worse since 2015? (within-country)
    "v_h4_trend": """
        SELECT country,
               round(avg(pei) FILTER (WHERE year BETWEEN 2000 AND 2014), 1)            AS pei_2000_14,
               round(avg(pei) FILTER (WHERE year BETWEEN 2015 AND 2025), 1)            AS pei_2015_25,
               round(avg(laws_substantive) FILTER (WHERE year BETWEEN 2000 AND 2014), 1) AS laws_2000_14,
               round(avg(laws_substantive) FILTER (WHERE year BETWEEN 2015 AND 2025), 1) AS laws_2015_25,
               round(avg(p2_fiscal) FILTER (WHERE year BETWEEN 2000 AND 2014), 1)      AS p2_2000_14,
               round(avg(p2_fiscal) FILTER (WHERE year BETWEEN 2015 AND 2025), 1)      AS p2_2015_25,
               round(avg(p3_stability) FILTER (WHERE year BETWEEN 2000 AND 2014), 1)   AS p3_2000_14,
               round(avg(p3_stability) FILTER (WHERE year BETWEEN 2015 AND 2025), 1)   AS p3_2015_25
        FROM pei_country_year GROUP BY country ORDER BY country""",
    # H5: mechanism - throughput vs government type, within country
    "v_h5_mechanism": """
        SELECT country,
               round(avg(s_laws) FILTER (WHERE minority = 1), 1)  AS laws_pctile_minority_govt,
               round(avg(s_laws) FILTER (WHERE minority = 0), 1)  AS laws_pctile_majority_govt,
               round(avg(s_laws) FILTER (WHERE n_parties = 1), 1) AS laws_pctile_single_party,
               round(avg(s_laws) FILTER (WHERE n_parties > 1), 1) AS laws_pctile_coalition,
               round(corr(s_laws, caretaker_share), 2)            AS corr_laws_caretaker
        FROM pei_country_year GROUP BY country ORDER BY country""",
    "v_ranking_latest": """
        SELECT country, any_value(panel_b) AS panel_b,
               round(avg(pei), 1) AS pei_2016_25, round(avg(pei_per_governing_day), 1) AS pei_pgd_2016_25,
               round(avg(p1_throughput), 1) AS p1, round(avg(p2_fiscal), 1) AS p2, round(avg(p3_stability), 1) AS p3,
               count(*) FILTER (WHERE coverage_flags LIKE '%p1_imputed%') AS years_p1_imputed
        FROM pei_country_year WHERE year BETWEEN 2016 AND 2025 GROUP BY country ORDER BY pei_2016_25 DESC""",
    "v_ranking_panel_b": "SELECT * FROM v_ranking_latest WHERE panel_b ORDER BY pei_2016_25 DESC",
    "v_ranking_panel_b_1980_99": """
        SELECT country, round(avg(pei), 1) AS pei_1980_99, round(avg(p1_throughput), 1) AS p1, round(avg(p2_fiscal), 1) AS p2,
               round(avg(p3_stability), 1) AS p3, count(*) FILTER (WHERE laws_total IS NOT NULL) AS years_with_laws
        FROM pei_country_year WHERE panel_b AND year BETWEEN 1980 AND 1999 GROUP BY country ORDER BY pei_1980_99 DESC""",
    "v_ranking_panel_b_1980_25": """
        SELECT country, round(avg(pei), 1) AS pei_1980_25, round(avg(pei) FILTER (WHERE year < 2000), 1) AS pei_1980_99,
               round(avg(pei) FILTER (WHERE year >= 2000), 1) AS pei_2000_25
        FROM pei_country_year WHERE panel_b AND year BETWEEN 1980 AND 2025 GROUP BY country ORDER BY pei_1980_25 DESC""",
    "v_panel_a_by_decade": """
        SELECT country, (year // 10) * 10 AS decade, round(avg(pei), 1) AS pei, round(avg(laws_substantive), 1) AS laws,
               round(avg(p2_fiscal), 1) AS p2, round(avg(p3_stability), 1) AS p3, count(*) FILTER (WHERE pei IS NOT NULL) AS years
        FROM pei_country_year WHERE country IN ('UK','IE','IT','DE','AT','DK','FR','LU','FI','IS') AND year BETWEEN 1950 AND 2025
        GROUP BY country, decade ORDER BY country, decade""",
    "v_long_trend": """
        SELECT year, round(avg(pei) FILTER (WHERE country IN ('UK','IE','IT','DE','AT','DK','FR','LU','FI','IS')), 1) AS pei_panel_a,
               round(avg(pei) FILTER (WHERE panel_b), 1) AS pei_panel_b, round(avg(pei), 1) AS pei_all,
               count(*) FILTER (WHERE pei IS NOT NULL) AS countries_scored,
               count(*) FILTER (WHERE in_force_day1 = false) AS late_budgets, sum(early_elections) AS early_elections
        FROM pei_country_year WHERE year BETWEEN 1950 AND 2025 GROUP BY year ORDER BY year""",
    "v_eras": "SELECT country, era, min(year) AS from_year, max(year) AS to_year, count(*) FILTER (WHERE laws_total IS NOT NULL) AS years_with_laws FROM pei_country_year GROUP BY country, era ORDER BY country, era",
    "v_ranking_panel_c": "SELECT * FROM v_ranking_latest ORDER BY pei_2016_25 DESC",
    "v_coverage": """
        WITH p AS (
            SELECT country,
                   count(*) FILTER (WHERE laws_total IS NOT NULL)              AS years_with_laws,
                   min(year) FILTER (WHERE laws_total IS NOT NULL)             AS laws_from,
                   max(year) FILTER (WHERE laws_total IS NOT NULL)             AS laws_to,
                   count(*) FILTER (WHERE in_force_day1 IS NOT NULL)           AS years_with_budget_test,
                   count(*) FILTER (WHERE budget_regime = 'structural_na')     AS years_budget_structural_na,
                   count(*) FILTER (WHERE p3_stability IS NOT NULL)            AS years_with_stability,
                   count(*) FILTER (WHERE gov_bill_pass_rate IS NOT NULL)      AS years_with_pass_rate
            FROM pei_country_year WHERE year BETWEEN 1950 AND 2025 GROUP BY country),
        o AS (
            SELECT country, round(avg(CASE WHEN origin IN ('government','parliament') THEN 1 ELSE 0 END), 2) AS origin_known_share,
                   string_agg(DISTINCT source, ', ') AS law_sources
            FROM laws WHERE year BETWEEN 1950 AND 2025 GROUP BY country)
        SELECT p.*, o.origin_known_share, o.law_sources FROM p LEFT JOIN o USING (country) ORDER BY country""",
}


def main():
    path = ROOT / "pei.duckdb"
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    for t in TABLES:
        f = DATA / f"{t}.csv"
        if f.exists():
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{f}', header=true, sample_size=-1)")
    skipped = []
    for name, sql in VIEWS.items():
        try:
            con.execute(f"CREATE VIEW {name} AS {sql}")
        except duckdb.Error:  # a table it needs is absent (e.g. laws.csv not rebuilt yet in a fresh clone)
            skipped.append(name)
    if skipped:
        log.warning("skipped views (missing tables; run --fetch and --normalise to build them): %s", skipped)
    log.info("pei.duckdb: tables %s; views %s", con.execute("SHOW TABLES").fetchall(), list(VIEWS))
    con.close()


if __name__ == "__main__":
    main()
