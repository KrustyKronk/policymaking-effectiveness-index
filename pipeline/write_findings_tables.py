"""Regenerate the tables block in FINDINGS.md from pei.duckdb (between the TABLES markers)."""
from __future__ import annotations

import duckdb

from pipeline.common import ROOT

Q = {
    "Composite, 2016–2025 average, all 31 countries (higher = more effective)": """
        SELECT country AS Country, CASE WHEN panel_b THEN 'West' ELSE 'CEE' END AS Panel, pei_2016_25 AS PEI, pei_pgd_2016_25 AS "PEI per governing day",
               p1 AS "P1 throughput (vs own past)", p2 AS "P2 budget", p3 AS "P3 stability",
               CASE WHEN years_p1_imputed > 0 THEN 'P1 imputed in ' || years_p1_imputed || ' of 10 years' ELSE '' END AS Note
        FROM v_ranking_latest""",
    "Panel A: long-standing democracies by decade (composite)": """
        SELECT country AS Country,
               round(avg(pei) FILTER (WHERE decade = 1950), 1) AS "1950s", round(avg(pei) FILTER (WHERE decade = 1960), 1) AS "1960s",
               round(avg(pei) FILTER (WHERE decade = 1970), 1) AS "1970s", round(avg(pei) FILTER (WHERE decade = 1980), 1) AS "1980s",
               round(avg(pei) FILTER (WHERE decade = 1990), 1) AS "1990s", round(avg(pei) FILTER (WHERE decade = 2000), 1) AS "2000s",
               round(avg(pei) FILTER (WHERE decade = 2010), 1) AS "2010s", round(avg(pei) FILTER (WHERE decade = 2020), 1) AS "2020s"
        FROM v_panel_a_by_decade GROUP BY country ORDER BY country""",
    "Panel B: Western Europe, 1980–1999 vs 2000–2025": """
        SELECT country AS Country, pei_1980_99 AS "PEI 1980–99", pei_2000_25 AS "PEI 2000–25",
               round(pei_2000_25 - pei_1980_99, 1) AS Change FROM v_ranking_panel_b_1980_25 ORDER BY Change""",
    "Before and after 2015": """
        SELECT country AS Country, pei_2000_14 AS "PEI 2000–14", pei_2015_25 AS "PEI 2015–25",
               round(pei_2015_25 - pei_2000_14, 1) AS Change, p2_2000_14 AS "Budget 2000–14", p2_2015_25 AS "Budget 2015–25",
               p3_2000_14 AS "Stability 2000–14", p3_2015_25 AS "Stability 2015–25"
        FROM v_h4_trend ORDER BY Change""",
    "Budgets not in force on 1 January (2000–2026)": """
        SELECT country AS Country, years_late_or_none AS "Years late", years_no_budget_at_all AS "Years with no budget",
               avg_delay_days_when_late AS "Avg delay (days) when late", coalesce(late_years, '') AS "Late years"
        FROM v_h3_budgets""",
    "Time without a full-power government": """
        SELECT country AS Country, pct_days_not_full_power_2000_25 AS "% days 2000–25",
               pct_days_not_full_power_2015_25 AS "% days 2015–25", early_elections_2000_25 AS "Early elections",
               pm_changes_2000_25 AS "PM changes" FROM v_h2_time_lost""",
    "Spain, year by year": """
        SELECT year AS Year, laws_parliamentary AS "Laws passed by parliament", n_decree_law AS "Decree-laws",
               round(caretaker_share * 100) AS "% days caretaker", early_elections AS "Early elections",
               budget_regime AS Budget, round(pei, 1) AS PEI
        FROM pei_country_year WHERE country = 'ES' AND year >= 2010 ORDER BY year""",
}


def md(df) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join("" if (v is None or (isinstance(v, float) and v != v)) else (f"{v:g}" if isinstance(v, float) else str(v)) for v in r) + " |")
    return "\n".join(out)


def main():
    con = duckdb.connect(str(ROOT / "pei.duckdb"), read_only=True)
    blocks = [f"### {title}\n\n{md(con.sql(sql).df())}" for title, sql in Q.items()]
    f = ROOT / "FINDINGS.md"
    s = f.read_text(encoding="utf-8")
    a, b = s.index("<!-- TABLES START -->"), s.index("<!-- TABLES END -->")
    s = s[: a + len("<!-- TABLES START -->")] + "\n\n" + "\n\n".join(blocks) + "\n\n" + s[b:]
    f.write_text(s, encoding="utf-8")
    print("FINDINGS tables regenerated")


if __name__ == "__main__":
    main()
