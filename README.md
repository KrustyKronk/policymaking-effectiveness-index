# Policymaking Effectiveness Index (PEI)

A side project testing a hunch: that Spain and the UK (and other European democracies) spend so much time on gridlock, snap elections and campaigning that they pass little substantive legislation. The background thinking is in [BRAINSTORM.md](BRAINSTORM.md); the source catalogue is in [data-sources.md](data-sources.md); the first read of the results is in [FINDINGS.md](FINDINGS.md).

**Coverage (v2, 18 October 2026):** 31 European democracies, scored from each country's democratic start (or 1950) to 2025, 2026 partial.
- **Panel A, long history (10):** UK, IE, IT, DE, AT, DK, FR (from 1959), LU, FI, IS — 1950–2025.
- **Panel B, Western Europe (20):** Panel A plus ES, PT, GR, NL, BE, SE, NO, CH, CY, MT — 1980–2025.
- **Panel C, all Europe (31):** Panel B plus PL, CZ, SK, HU, SI, HR, RO, BG, EE, LV, LT — from their transitions (1990–93).
v0 (16 Oct) covered 13 countries 2000–25; v1 (17–18 Oct) 31 countries 2000–25.

**Interactive explorer:** https://claude.ai/artifact/PLd7Pp4BfAJ2nzEYDrrFKs (a Claude artifact; anyone with the link can view it). It has two pages: Explore, and How the index works. It re-scores the index live from weight and penalty sliders. Rebuild it after any data change with `uv run python run.py --artifact`, which writes `artifact/pei-explorer.html`, then republish that file. The event notes live in `artifact/annotations.yaml`. `node artifact/check_score.js` checks that the page's scoring matches `pipeline/score.py`.

## What is in this repository

- `pipeline/` and `run.py`: the fetchers, normalisers, scoring and database build.
- `pipeline/budget_inputs/`: the hand-compiled budget tables, one source per row.
- `params.yaml`: weights and penalties. Edit it and re-score.
- `data/`: the scored index and the inputs the scoring step needs. See `data/LICENSE.md`.
- `artifact/`: the interactive explorer (`pei-explorer.html` opens in any browser) and the code that builds it.
- `FINDINGS.md` and `FINDINGS_regions_and_governments.md`: what the data shows.

Not included: raw downloads (about 6.5 GB) and row-level law records. Several sources do not allow redistribution, and the fetchers rebuild everything from the original publishers.

## Run it

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env                    # add a Bundestag DIP key (only the German fetcher needs one)
uv run python run.py --score --build --artifact   # re-score from the included data, e.g. after editing params.yaml
uv run python run.py --all              # full rebuild: fetch every source, normalise, score, build
```

A full rebuild downloads several gigabytes and takes hours. Some parliament sites throttle requests, so expect retries. Without the fetched law records the database skips a few law-level views.

Every downloaded file is cached under `raw/` and listed with URL, timestamp and SHA-256 in `raw/MANIFEST.json`. Re-running without deleting `raw/` makes no network calls except for sources that are explicitly refreshed.

## What is in `data/`

| File | One row per | What it holds |
|---|---|---|
| `laws.csv` | enacted primary-law instrument | country, year, date, instrument_type (law, organic_law, decree_law, legislative_decree, budget_law, ratification, constitutional_law, other), origin (government / parliament / unknown), original-language title, CAP topic where known, `is_substantive_v0`, source and URL |
| `laws_coverage.csv` | country × year | which source was used, its count, and the alternate counts (national rows, aggregate counts, Comparative Agendas Project) with % difference |
| `cabinets.csv` | cabinet | REPDEM cabinet data: PM, start/end, parties, type (single majority / coalition / minority / caretaker), formation days, termination reason, early-election flag |
| `budgets.csv` | country × fiscal year | was the budget law in force on day 1, adoption and promulgation dates, delay days, regime (on_time / late / rolled_over), confidence, **one source URL per row**, note, Open Budget Survey cross-check letter |
| `context.csv` | country × year | World Bank government effectiveness, POLCON III/V, DPI checks, SGI executive capacity (2014, 2022), OECD iREG regulatory-impact score. **Not scored** (`scored = false`) |
| `pei_country_year.csv` | country × year | all raw metrics, per-metric scores, the four pillars, `pei` and `pei_per_governing_day`, coverage flags |
| `pei_cabinet.csv` | cabinet | the same scores averaged over the years each cabinet held office (≥ 90 days in the year) |

`data/intermediate/` holds the per-country fetch outputs (`laws_xx`, `bills_xx`, `counts_xx`) and the stability and throughput country-year tables.

## How the index is built

| Pillar | Weight (equal thirds since 18 Oct 2026; was 40/20/30) | Metric | Comparable across countries? |
|---|---|---|---|
| P1 Throughput | 33 | Percentile of the 3-year rolling mean of *substantive* laws within the country's own 2000–2025 history, averaged with the within-country percentile of the government-bill pass rate where ≥ 5 years exist; optional decree penalty | **No.** Scored against each country's own past |
| P2 Fiscal | 33 | 100 if the budget law (or, in FI, NO, SE, CH, parliament's full-year budget decision) was in force on day 1, 50 if late by ≤ 30 days, 0 if later or never (25 if late with unknown date). **UK and Ireland are "not applicable"** (their systems cannot start a year without spending authority), so P2 is null and weights renormalise | Yes |
| P3 Stability | 33 | 100 × share of days with a full-power (non-caretaker) government, minus 15 per early election, minus 10 per PM change (max 2) | Yes |
| P4 Implementation | 10 | Not populated in v0 (transposition data needs PDF scraping). Turn on `use_sanity_in_p4` to use World Bank government effectiveness | — |

`pei` is the weighted mean of the non-null pillars with weights renormalised. When a country-year has no law data at all, P1 is set to a neutral 50 and flagged `p1_imputed_no_laws`. `pei_per_governing_day` swaps P1 for laws per 365 full-power days, which separates "slow when governing" from "rarely governing". Everything is a parameter in `params.yaml`.

**Substantive laws (v0)** exclude budget/appropriation laws, treaty ratifications, consolidations and private bills, by instrument type plus per-language title patterns in `pipeline/mappings.yaml`. Decree-laws count as output and are reported separately as `n_decree_law` and `decree_share`.

## Time coverage and rules (v2)

| Country | Laws from | Budgets from | Notes |
|---|---|---|---|
| UK | 1950 | structural N/A | Acts per calendar year (pre-1963 regnal numbering) |
| IE | 1922 (scored 1950) | structural N/A | |
| IT | 1948 | 1950 | Camera SPARQL 1948–97 holds ~45% of 1950s law numbers (consistent within era); eras 1948–92, 1993– |
| DE | 1949 (per term to 1972), rows 1973– | 1950 | Fiscal year April–March until 1960; eras 1949–89, 1990– |
| AT | 1945 (BGBl counts), rows 1996– | 1950 | |
| DK | 1953 (CAP), ODA 2004– | 1980 (1950–79 unknown) | Fiscal year April–March until 1977/78 |
| FR | 1959 (Senate counts), CAP rows 1979–2001, DOLE 2002– | 1959 | **Three-source splice** |
| LU | 1950 | 1950 | |
| FI | 1990 | 1980 (1950–79 unknown) | Finlex throttled; stopped at 1990 |
| IS | 1992 | 1950 | |
| ES | 1979 | 1980 | |
| PT | 1976 (Diário da República) | 1980 | Decree-laws ~80% of norms; within ~5% of DILP per legislatura except VII |
| GR | 1975 | 1990 (1980s unknown) | Law numbering complete except 7 numbers |
| NL | 1981 (CAP), Staatsblad 1995– | 1980 | Budget rule: Tweede Kamer vote |
| BE | 1988 (CAP) | 1988 (1980–87 unknown) | |
| SE | 2003 | 1980 | Fiscal year July–June until 1996 (1995/96 was 18 months) |
| NO | 1987 | 1987 (1980–86 unknown) | |
| CH | 1978 (CAP), Fedlex 2000– | 1980 | |
| CY | 1960 | 1980 | Pre-1992 single numbering: appropriation and guarantee laws excluded by title |
| MT | 1990 | 1981 | |
| PL, CZ, SK, HU, SI, HR, RO, BG, EE, LV, LT | 1990–93 (BG 2003, LV 2000) | from transition | Romania laws from 1998 |

- **Scoring eras.** Throughput is a percentile within each country's own history, split at regime breaks (`ERAS` in `pipeline/common.py`): Italy 1948–92 / 1993–, Germany 1949–89 / 1990–, and democratic starts for Spain, Portugal, Greece and the post-communist states. Years before a country's democratic start are not scored.
- **Fiscal-year starts by era** (`FY_START`): Italy 1 July until 1964, Germany 1 April until 1960, Denmark 1 April until 1977/78, Sweden 1 July until 1995/96, UK 1 April always.
- **Fewer but longer laws.** Over 50–75 years some parliaments (UK, France, Italy) pass fewer, longer laws. Long-run throughput declines there partly reflect drafting style; budgets and stability are unaffected.

## Sources actually used

| Country | Laws (row level unless noted) | Bills / pass rates | Budget table |
|---|---|---|---|
| ES | Spanish Laws & Legislative Decrees dataset 1982–2024 (Dataverse 10.7910/DVN/1VKJXZ); BOE daily summaries 2025–26 | Congreso open data, XV legislature only | BOE + senado.es votes |
| UK | legislation.gov.uk Public General Acts; SI counts | UK Parliament Bills API, 2006– | legislation.gov.uk Finance Acts |
| FR | DILA DOLE dossiers 2002–; CAP laws 2000–01 | — | senat.fr dossiers |
| DE | Bundestag *Datenhandbuch* 10.1 + WP21 statistics, **per-Wahlperiode totals spread pro rata to years** | — | Haushaltsgesetz dates (buzer.de, gesetze-im-internet.de) |
| IT | Senato SPARQL (`osr:Ddl`), 1998– | not in v0 (endpoint returned 403 mid-run; rerun `--fetch it`) | normattiva.it |
| NL | Staatsblad via repository.overheid.nl SRU | Tweede Kamer OData, 2008– | eerstekamer.nl; **rule: Tweede Kamer final vote before 1 Jan** (the Senate routinely finishes chapters in spring) |
| BE | CAP Belgian bills adopted by the Chamber, 1988–2022 (year = introduction year) | CAP (origin dummies) | lachambre.be dossiers + Moniteur belge |
| SE | Riksdagen SFS listing (**standalone statutes only, a floor**) | Riksdagen propositions | Riksdagen FiU1 decisions |
| DK | Folketing ODA (lovforslag with law number), 2004– | Folketing ODA | folketingstidende.dk / ODA |
| IE | Oireachtas API | Oireachtas API | Oireachtas API (Appropriation Acts) |
| PT | none scriptable in v0 | — | parlamento.pt / DR (from memory, low confidence) |
| AT | parlament.gv.at filter API, 2003– (matches *Parlament in Zahlen* once treaties are excluded) | parlament.gv.at | ris.bka.gv.at BGBl |
| PL | Sejm ELI API (Dziennik Ustaw, type Ustawa) | Sejm processes API, 2011– | sejm.gov.pl / ELI |

| FI | Finlex open-data API (acts; origin from HE/LA bill references) | Eduskunta | Eduskunta plenary votes |
| NO | Storting open data (lovsak cases with origin and status) | Storting | Storting budget decisions |
| IS | Althingi XML (bills with outcome and origin) | Althingi | Althingi final votes |
| LU | Legilux SPARQL (LOI) | — | Legilux budget laws |
| CH | Fedlex SPARQL, deduplicated to one row per act (matches CAP on 363 of 378 acts 2000–08) | parlament.ch OData | parlament.ch budget decrees. **Flagged:** consensus system with no PM, confidence votes or snap elections |
| GR | Government Gazette legislation search; law numbering complete with zero gaps 2000–2025 | — | Budget ratification laws (FEK) |
| CY | CyLaw numbered indexes (general / budget / ratification by numbering) | — | CyLaw budget laws |
| MT | legislation.mt ELI JSON-LD, no gaps in act numbering | — | Appropriation Acts |
| CZ | psp.cz open data (Collection of Laws + bills) | psp.cz | Sbírka zákonů |
| SK | ParlText SK + nrsr.sk | nrsr.sk | Slov-Lex |
| HU | ParlText HU | — | njt.hu / Magyar Közlöny |
| SI | National Assembly open-data XML (proposer, procedure) | National Assembly | Uradni list |
| HR | Narodne novine ELI metadata (ZAKON) | — | Narodne novine |
| RO | cdep.ro promulgated laws + emergency ordinances (legislatie.just.ro) | cdep.ro | Monitorul Oficial / cdep.ro |
| BG | parliament.bg JSON (2009–) | parliament.bg | parliament.bg / State Gazette |
| EE | Riigikogu API | Riigikogu | Riigikogu / Riigi Teataja |
| LV | Saeima open data (2017–) + annual reports (2010–16) | — | likumi.lv |
| LT | Seimas open data: sittings and final votes rebuilt into adopted laws (levels unverified against an official total) | — | Seimas sitting records |

Changed in v1 for v0 countries: **Germany** now uses row-level laws from the Bundestag DIP API (public key in `.env`; matches the Datenhandbuch within 0.6% per term). **Sweden** now classifies every adopted government bill from its Riksdag status record (exact; 2003– by the calendar year the session ends), replacing the in-force-biased SFS list.

Stability: REPDEM Basic v2026.07 (cabinets to 1 July 2026). Context: WGI (World Bank API, `GOV_WGI_GE.*`), POLCON 2025, DPI 2023, SGI 2014/2022, OECD iREG 2025.

## Caveats you should know before quoting anything

- **Law counts are not comparable across countries.** Belgium, Denmark, the Netherlands and Poland count every small amending act; the UK and Ireland pass few long Acts; Germany's Länder and Spain's regions legislate on things Westminster does centrally. That is why P1 is within-country only. Raw counts are in the data for curiosity, not ranking.
- **Splices.** France's DOLE source misses many treaty-ratification laws (≈ 35% below CAP on overlapping years, mostly ratifications, which the substantive count excludes anyway). Spain's 2025–26 BOE-summary series found 24 laws for 2024 against 28 in the dataset (−14%). The UK and Ireland match CAP exactly. The two big single-year gaps (Italy 2013 +275%, Spain 2018 +76%) are the partial final years of the CAP files, not errors in the national series. See `laws_coverage.csv`.
- **Germany** law counts are Wahlperiode totals spread evenly across years, which hides pre-election bunching. 2025 is provisional (WP 21 still running).
- **Sweden** law counts start in 2003 (earlier sessions lack decision data in the Riksdag API).
- **Lithuania** counts are rebuilt from sitting records and include many amending laws; levels are not cross-checked with an official total.
- **Bulgaria** has no law data before mid-2009; **Latvia** before 2010; **Portugal** none (session 2).
- **Origin** (government vs parliament) is unknown for Greece, Cyprus, Croatia, Lithuania, Latvia and Luxembourg, and partial for Switzerland.
- **Belgium** throughput comes from bills adopted by the Chamber, dated by introduction year, and ends in 2022.
- **Portugal** has no law data in v0 (no scriptable source); its P1 is imputed at 50.
- **Budgets** were hand-compiled by research agents on 16 Oct 2026 with one source per row and a confidence column. All 13 countries are high or medium confidence after verification against parliament and gazette records; the lowest-confidence cells are a few German Bundestag vote dates. Ireland and the UK never start a fiscal year without spending authority by design (votes on account; the Central Fund Act 1965), so they score 100 every year by construction.
- **Poland** shows the budget "late" in 25 of 27 years. That is real (the President usually signs in late January) but the delay is usually 3–6 weeks and the government spends on the draft budget meanwhile, so read P2 for Poland as "chronically a few weeks late", not "no budget".
- **Caretaker time** is caretaker cabinets plus gaps between cabinets (REPDEM coding). Campaign periods before an election are not counted.
- **Direction-neutral.** The index measures capacity to act, not whether the action was good. A deregulating repeal counts as an act.

## Example queries

```sql
-- the composite, last ten years
SELECT * FROM v_ranking_latest;
-- H2: how much time does each country spend without a full-power government?
SELECT * FROM v_h2_time_lost;
-- H3: budgets
SELECT * FROM v_h3_budgets;
-- H4: before vs after 2015
SELECT * FROM v_h4_trend;
-- Spain, year by year
SELECT year, laws_parliamentary, n_decree_law, round(decree_share,2) AS decree_share, caretaker_share,
       early_elections, budget_regime, round(pei,1) AS pei
FROM pei_country_year WHERE country = 'ES' ORDER BY year;
-- every Spanish decree-law since 2016
SELECT date, title FROM laws WHERE country = 'ES' AND instrument_type = 'decree_law' AND year >= 2016 ORDER BY date;
-- which cabinets were the most and least effective?
SELECT country, cabinet_name, years, cabinet_type, pei FROM pei_cabinet WHERE n_years >= 2 ORDER BY pei;
```

## Not done in v0 (next, if ever)

LLM significance classifier over law titles; length-based significance (needs full texts); EU transposition deficit from Single Market Scoreboard PDFs; Portugal law counts; Belgium after 2022; Germany row-level laws (Bundestag DIP API needs a key); Italian bill pass rates; Austria 2000–02; IPU Parline cross-check (Cloudflare-blocked); bill durations; government defeats on votes; any HTML visualisation.

## Licence

Code: MIT (`LICENSE`). Data, findings and the explorer's data: CC BY-NC-SA 4.0, because part of the law series comes from the Comparative Agendas Project. See `data/LICENSE.md` for the sources to cite.
