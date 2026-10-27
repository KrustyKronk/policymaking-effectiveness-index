# Findings — v2 (31 countries, 1950–2025, 18 October 2026, equal pillar weights)

The index now weights laws, budgets and stability equally (a third each). The same read with the original 40/20/30 weights is archived in `raw/FINDINGS_v2_weights_40-20-30_2026-10-18.md`; none of the conclusions changed. Earlier reads are archived in `raw/FINDINGS_v0_2026-10-16.md` (13 countries, 2000–25) and `raw/FINDINGS_v1_2026-10-18.md` (31 countries, 2000–25). Tables below are regenerated from `pei.duckdb` by `uv run python -m pipeline.write_findings_tables`. Read the README caveats before quoting a number, especially the note on law counts over long periods.

Deeper analysis of regions, standout countries, Italy's budgets and the coalition hypothesis (Germany, France, Spain 2021–25) is in [FINDINGS_regions_and_governments.md](FINDINGS_regions_and_governments.md).

## The short answer

**There was no golden age.** Measured on the same yardstick, European governments are more effective at the basics now than in the 1950s–80s. The long-history average rose from about 60 in the 1950s to about 75–78 from the 1990s on. The single biggest change is budgets: in the 1950s nearly three in four country-years started without a budget law in force; since 2000 it is about one in eight to one in six.

**But the last two years are the weakest in decades.** Across all 31 countries 2024 and 2025 sit at about 70–72, the lowest outside the post-communist transition years; for the ten long-standing democracies 2025 (64) is the lowest since the early 1960s. Prime-minister turnover per country is now the highest of any decade (about one change every three years, double the 1950s rate), and the share of days spent under caretaker governments has tripled since the 1960s.

**Spain is still last for 2016–2025, now measured against its own history back to 1979.** Its composite averaged 34 points less in 2016–25 than in 2000–15, the largest drop of any country. Poland, the UK, Portugal and Bulgaria complete the bottom five.

## What going back in time shows

- **Budgets used to be late almost everywhere.** Italy started 32 of the 39 fiscal years from 1950 to 1988 under a provisional budget (*esercizio provvisorio*), and has never needed one since 1989. Germany's budget law was promulgated after the start of its fiscal year in every year from 1950 to 1979. Luxembourg ran on provisional twelfths in every year from 1950 to 1967; Belgium did so routinely until the late 1980s and had no budget at all in 1988. Austria needed statutory provisional budgets in 1950, 1953, 1963 and 1966. France's Fifth Republic was the exception: on time every year from 1959 except 1963 (the spending half of the budget passed in February) and 1980, when the Constitutional Council annulled the finance law.
- **Italy's reputation belongs to its first republic.** Italy scored about 45–48 in the 1970s and 1980s (constant provisional budgets, governments lasting under a year) and about 82–83 in the 1990s and 2000s after the 1993 electoral reform.
- **The UK's decline is long and steady.** The UK peaked in the 1960s (89) and has fallen every decade since, to 59 in the 2020s. Two things drive it: Acts of Parliament per year halved (from about 65 to about 35; see the caveat below), and prime-minister churn rose.
- **Spain's problem is recent.** Spain scored 81 in the 1980s, 77–82 in the 1990s and 2000s, then 60 in the 2010s and 58 in the 2020s.
- **Germany dips in the 1960s–70s** (late budgets every year) and recovers from the 1990s, before falling again in the 2020s with the 2024–25 budget crises.
- **Most improved over 1980–1999 to 2000–2025 in Western Europe:** Cyprus, Ireland, Italy, Greece, Norway and Finland. **Biggest fallers:** the UK (77 to 62), Denmark, Spain, Portugal and France.

## The 2016–2025 ranking (full-history reference)

Small Western states lead: Malta, Cyprus, Finland and Luxembourg, followed by Lithuania, Switzerland and Norway. The bottom five are Spain, Poland, the UK, Portugal and Bulgaria. These positions moved compared with v1 because each country's law output is now compared with its whole democratic history, not only 2000–2025: countries that legislated more in earlier decades (the UK, France, Portugal) score lower on throughput today.

## The main caveat: fewer but longer laws

Within-country throughput scoring assumes a law means roughly the same thing across a country's history. Over 50–75 years that is not quite true: several parliaments (the UK, France, Italy) now pass fewer, much longer laws, and the literature documents texts growing several-fold. So part of the long-run throughput decline in those countries reflects drafting style, not less legislating. The budget and stability pillars are unaffected. A length-weighted count is the obvious next refinement.

## Tables

<!-- TABLES START -->

### Composite, 2016–2025 average, all 31 countries (higher = more effective)

| Country | Panel | PEI | PEI per governing day | P1 throughput (vs own past) | P2 budget | P3 stability | Note |
|---|---|---|---|---|---|---|---|
| MT | West | 94.8 | 94.8 | 85.4 | 100 | 99 |  |
| FI | West | 91.8 | 91.9 | 81.9 | 100 | 93.4 |  |
| CY | West | 91.8 | 91.8 | 81.4 | 95 | 99 |  |
| LU | West | 90.2 | 90.1 | 94.1 | 80 | 96.5 |  |
| LT | CEE | 89.2 | 89.4 | 84.8 | 100 | 82.8 |  |
| CH | West | 88.6 | 88.6 | 65.8 | 100 | 100 |  |
| NO | West | 86.5 | 87.3 | 65.1 | 100 | 94.5 |  |
| GR | West | 84.4 | 83 | 56 | 100 | 97.4 |  |
| SK | CEE | 83.9 | 82.7 | 60.3 | 100 | 91.5 |  |
| HU | CEE | 83.6 | 83.5 | 53.7 | 100 | 97.5 | P1 imputed in 1 of 10 years |
| IE | West | 80.7 | 82 | 75.2 |  | 86.3 |  |
| HR | CEE | 80.5 | 80.7 | 59.7 | 90 | 91.7 |  |
| EE | CEE | 80.4 | 80.4 | 47.9 | 100 | 93.2 |  |
| SI | CEE | 79.9 | 78.8 | 49.3 | 100 | 90.4 |  |
| SE | West | 79.8 | 80.6 | 46.6 | 100 | 92.8 |  |
| IT | West | 74.9 | 74.3 | 32.4 | 100 | 92.2 |  |
| BE | West | 74.9 | 74.9 | 82.4 | 70 | 82 | P1 imputed in 3 of 10 years |
| IS | West | 74.3 | 74.9 | 37.8 | 100 | 85.2 |  |
| DK | West | 74 | 74.1 | 36.3 | 90 | 95.7 |  |
| CZ | CEE | 73.4 | 73.7 | 43 | 90 | 87.1 |  |
| AT | West | 72.6 | 73.9 | 67.2 | 70 | 80.7 |  |
| NL | West | 68.8 | 75.3 | 47.4 | 90 | 69 |  |
| FR | West | 67.9 | 68.5 | 25.4 | 90 | 88.1 |  |
| LV | CEE | 67.2 | 67.2 | 31.5 | 80 | 90.1 |  |
| DE | West | 67.1 | 68.5 | 54 | 60 | 87.5 |  |
| RO | CEE | 62.1 | 62.7 | 50.7 | 50 | 85.5 |  |
| BG | CEE | 59.6 | 60.9 | 40.4 | 70 | 68.5 |  |
| PT | West | 57.1 | 57.2 | 12.4 | 70 | 89 |  |
| UK | West | 56.2 | 56.2 | 22 |  | 90.4 |  |
| PL | CEE | 52.4 | 52.5 | 49 | 15 | 93.3 |  |
| ES | West | 46.9 | 51.7 | 23.4 | 40 | 77.2 |  |

### Panel A: long-standing democracies by decade (composite)

| Country | 1950s | 1960s | 1970s | 1980s | 1990s | 2000s | 2010s | 2020s |
|---|---|---|---|---|---|---|---|---|
| AT | 60.1 | 69.1 | 85.1 | 76.3 | 77.6 | 61.3 | 74.9 | 75.6 |
| DE | 61.1 | 53.3 | 47.7 | 68.8 | 68.1 | 70.7 | 74.1 | 61.8 |
| DK | 54.9 | 57.4 | 81 | 82.5 | 90.7 | 74.8 | 79 | 69.2 |
| FI | 60.6 | 64.2 | 62.4 | 74.1 | 69.5 | 75.5 | 88 | 91 |
| FR | 89.3 | 88.1 | 94.4 | 81 | 78.1 | 70.6 | 74.7 | 66.9 |
| IE | 63.7 | 68.5 | 64.1 | 59 | 74.2 | 78.5 | 83 | 81.8 |
| IS | 62.6 | 79.7 | 79 | 73.5 | 82.4 | 89.5 | 75.9 | 75.3 |
| IT | 60 | 54.4 | 47.5 | 45 | 82.7 | 82.3 | 70.4 | 80 |
| LU | 33.4 | 42.3 | 82 | 80.8 | 80.6 | 91.4 | 85.3 | 92 |
| UK | 78.2 | 89.2 | 85.3 | 81.1 | 72.2 | 64.1 | 61.8 | 58.7 |

### Panel B: Western Europe, 1980–1999 vs 2000–2025

| Country | PEI 1980–99 | PEI 2000–25 | Change |
|---|---|---|---|
| UK | 76.7 | 62 | -14.7 |
| DK | 86.6 | 75.1 | -11.5 |
| ES | 79.2 | 67.8 | -11.4 |
| PT | 74.4 | 66.1 | -8.3 |
| FR | 79.5 | 71.3 | -8.2 |
| AT | 76.9 | 69.8 | -7.1 |
| SE | 82.1 | 82.7 | 0.6 |
| DE | 68.4 | 70 | 1.6 |
| NL | 68.3 | 70.9 | 2.6 |
| MT | 79.9 | 82.8 | 2.9 |
| IS | 77.9 | 81 | 3.1 |
| BE | 64.2 | 72.1 | 7.9 |
| LU | 80.7 | 89.2 | 8.5 |
| CH | 76 | 87.2 | 11.2 |
| FI | 71.8 | 83.9 | 12.1 |
| NO | 73.2 | 86.3 | 13.1 |
| GR | 66.2 | 79.5 | 13.3 |
| IT | 63.9 | 77.2 | 13.3 |
| IE | 66.6 | 81 | 14.4 |
| CY | 62.7 | 92.5 | 29.8 |

### Before and after 2015

| Country | PEI 2000–14 | PEI 2015–25 | Change | Budget 2000–14 | Budget 2015–25 | Stability 2000–14 | Stability 2015–25 |
|---|---|---|---|---|---|---|---|
| ES | 81 | 49.8 | -31.2 | 93.3 | 45.5 | 94.9 | 79 |
| BG | 86 | 61.5 | -24.5 | 100 | 72.7 | 89.8 | 71.4 |
| LV | 82.6 | 68 | -14.6 | 93.3 | 81.8 | 87.8 | 90.3 |
| PT | 72 | 58.2 | -13.8 | 86.7 | 72.7 | 89.7 | 88.4 |
| RO | 76 | 62.3 | -13.7 | 73.3 | 54.5 | 93.4 | 85.6 |
| IS | 85.9 | 74.3 | -11.6 | 100 | 100 | 94 | 86.6 |
| UK | 65.6 | 57 | -8.6 |  |  | 96.6 | 91.2 |
| CZ | 81.1 | 74.5 | -6.6 | 93.3 | 90.9 | 83.8 | 88.3 |
| PL | 60.2 | 54.5 | -5.7 | 20 | 18.2 | 90.7 | 92.4 |
| IT | 78.8 | 75.1 | -3.7 | 100 | 100 | 87.4 | 92.9 |
| FR | 72.8 | 69.2 | -3.6 | 100 | 90.9 | 95.6 | 89.2 |
| SE | 84.1 | 80.8 | -3.3 | 100 | 100 | 98 | 93.5 |
| SK | 85.7 | 83 | -2.7 | 100 | 100 | 92.5 | 92.3 |
| DK | 76.1 | 73.9 | -2.2 | 83.3 | 90.9 | 95.5 | 94.9 |
| DE | 70.7 | 69.1 | -1.6 | 60 | 63.6 | 94.5 | 88.6 |
| EE | 82.4 | 80.8 | -1.6 | 93.3 | 100 | 94.1 | 92.9 |
| NL | 71.4 | 70.1 | -1.3 | 86.7 | 90.9 | 77.7 | 71.8 |
| CY | 93 | 91.9 | -1.1 | 100 | 95.5 | 98 | 99.1 |
| HU | 85.3 | 84.6 | -0.7 | 100 | 100 | 93 | 97.7 |
| IE | 80.8 | 81.3 | 0.5 |  |  | 96.7 | 87.5 |
| NO | 86 | 86.7 | 0.7 | 100 | 100 | 95.2 | 95 |
| SI | 79 | 80.2 | 1.2 | 86.7 | 100 | 83.6 | 91.3 |
| CH | 86.6 | 88 | 1.4 | 100 | 100 | 100 | 100 |
| LU | 88.1 | 90.7 | 2.6 | 93.3 | 81.8 | 95.8 | 96.8 |
| HR | 75.7 | 80.3 | 4.6 | 73.3 | 90.9 | 94.6 | 91.1 |
| GR | 77.6 | 82.2 | 4.6 | 100 | 100 | 87.7 | 92.2 |
| AT | 66.7 | 74.1 | 7.4 | 66.7 | 72.7 | 88.2 | 82.4 |
| BE | 68.7 | 76.8 | 8.1 | 70 | 72.7 | 77.2 | 83.6 |
| LT | 77.5 | 89.5 | 12 | 100 | 100 | 90.9 | 84.3 |
| FI | 78 | 91.9 | 13.9 | 100 | 100 | 94.1 | 92.1 |
| MT | 73.8 | 95.1 | 21.3 | 93.3 | 100 | 98.7 | 99.1 |

### Budgets not in force on 1 January (2000–2026)

| Country | Years late | Years with no budget | Avg delay (days) when late | Late years |
|---|---|---|---|---|
| PL | 25 | 0 | 41 | 2000, 2001, 2002, 2004, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026 |
| RO | 12 | 0 | 45 | 2000, 2001, 2009, 2010, 2013, 2017, 2018, 2019, 2020, 2021, 2025, 2026 |
| DE | 10 | 0 | 143 | 2003, 2004, 2005, 2006, 2010, 2014, 2018, 2022, 2024, 2025 |
| BE | 9 | 2 | 97 | 2008, 2009, 2011, 2012, 2013, 2019, 2020, 2025, 2026 |
| ES | 8 | 5 | 181 | 2012, 2017, 2018, 2019, 2020, 2024, 2025, 2026 |
| AT | 8 | 0 | 163 | 2000, 2003, 2007, 2009, 2014, 2018, 2020, 2025 |
| HR | 5 | 0 | 71 | 2000, 2004, 2008, 2012, 2016 |
| PT | 5 | 0 | 113 | 2000, 2010, 2016, 2020, 2022 |
| DK | 4 | 0 | 85 | 2002, 2008, 2012, 2023 |
| BG | 4 | 0 | 141 | 2022, 2023, 2025, 2026 |
| NL | 4 | 0 | 180 | 2007, 2013, 2024, 2026 |
| LV | 3 | 0 | 83 | 2003, 2019, 2023 |
| LU | 3 | 0 | 116 | 2014, 2019, 2024 |
| CZ | 3 | 0 | 79 | 2000, 2022, 2026 |
| SI | 2 | 0 | 77 | 2000, 2001 |
| EE | 2 | 0 | 4 | 2001, 2002 |
| FR | 2 | 0 | 48 | 2025, 2026 |
| CY | 1 | 0 | 27 | 2021 |
| MT | 1 | 0 | 105 | 2013 |
| CH | 0 | 0 |  |  |
| SE | 0 | 0 |  |  |
| HU | 0 | 0 |  |  |
| LT | 0 | 0 |  |  |
| FI | 0 | 0 |  |  |
| IT | 0 | 0 |  |  |
| GR | 0 | 0 |  |  |
| NO | 0 | 0 |  |  |
| IS | 0 | 0 |  |  |
| UK | 0 | 0 |  |  |
| IE | 0 | 0 |  |  |
| SK | 0 | 0 |  |  |

### Time without a full-power government

| Country | % days 2000–25 | % days 2015–25 | Early elections | PM changes |
|---|---|---|---|---|
| NL | 14.6 | 27.3 | 7 | 13 |
| IT | 10.7 | 3.4 | 9 | 39 |
| BE | 10.7 | 13.7 | 10 | 25 |
| FI | 8.1 | 4.3 | 7 | 31 |
| AT | 6.1 | 8.5 | 14 | 18 |
| PT | 5.9 | 8.4 | 7 | 11 |
| ES | 4.1 | 17.4 | 8 | 6 |
| DE | 3.9 | 9.6 | 3 | 9 |
| CZ | 3.6 | 9 | 2 | 13 |
| BG | 3.6 | 13.2 | 10 | 22 |
| IS | 3.5 | 4.8 | 11 | 24 |
| SI | 3.3 | 4.6 | 2 | 12 |
| LT | 3.3 | 12 | 0 | 14 |
| LV | 3.2 | 6.9 | 1 | 15 |
| PL | 2.5 | 4.8 | 2 | 14 |
| LU | 2.4 | 2.3 | 3 | 9 |
| IE | 2.3 | 6.6 | 17 | 22 |
| GR | 2.1 | 1 | 16 | 11 |
| RO | 2 | 5.3 | 0 | 20 |
| EE | 1.9 | 4.4 | 0 | 11 |
| FR | 1.9 | 4 | 6 | 25 |
| NO | 1.8 | 4.1 | 0 | 21 |
| DK | 1.7 | 1.9 | 18 | 17 |
| SK | 1.5 | 1.8 | 2 | 11 |
| HR | 1.5 | 6.2 | 2 | 12 |
| HU | 1.5 | 2.3 | 0 | 7 |
| SE | 1.4 | 4.7 | 1 | 13 |
| CY | 0.7 | 0 |  | 6 |
| UK | 0.1 | 0.1 | 15 | 18 |
| CH | 0 | 0 |  |  |
| MT | 0 | 0 |  | 12 |

### Spain, year by year

| Year | Laws passed by parliament | Decree-laws | % days caretaker | Early elections | Budget | PEI |
|---|---|---|---|---|---|---|
| 2010 | 54 | 14 | 0 | 0 | on_time | 89.4 |
| 2011 | 53 | 20 | 9 | 1 | on_time | 79.2 |
| 2012 | 25 | 29 | 0 | 0 | late | 53.2 |
| 2013 | 37 | 17 | 0 | 0 | on_time | 84 |
| 2014 | 44 | 17 | 0 | 0 | on_time | 92.2 |
| 2015 | 72 | 12 | 3 | 0 | on_time | 79 |
| 2016 | 3 | 7 | 84 | 0 | on_time | 44.6 |
| 2017 | 13 | 21 | 0 | 0 | late | 35.5 |
| 2018 | 16 | 28 | 1 | 0 | late | 32.5 |
| 2019 | 8 | 18 | 68 | 2 | rolled_over | 5.6 |
| 2020 | 15 | 39 | 3 | 0 | rolled_over | 43.6 |
| 2021 | 33 | 32 | 0 | 0 | on_time | 90.4 |
| 2022 | 54 | 20 | 0 | 0 | on_time | 84 |
| 2023 | 17 | 8 | 32 | 0 | on_time | 63.5 |
| 2024 | 14 | 14 | 0 | 0 | rolled_over | 34 |
| 2025 | 13 | 16 | 0 | 0 | rolled_over | 34.8 |

<!-- TABLES END -->

## What this still cannot tell you

- **Whether the laws mattered.** "Substantive" strips budgets, ratifications, appropriations and similar by type and title only.
- **Why.** These are descriptive patterns, not causal tests.
- **Early budget years for some countries.** Denmark and Finland before 1980, Belgium 1980–87, Norway 1980–86 and Greece in the 1980s are unknown and unscored on the budget pillar.
