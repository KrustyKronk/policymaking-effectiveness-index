# PEI — Data source catalogue

Compiled 16 October 2026 from four parallel research passes. "Verified" means the page, API or file was actually fetched that day; "partial" means the page was fetched but a detail comes from a secondary source; "search only" means snippets.

Sections 1–2 cover legislative output (the throughput pillar). Sections 3–7 cover stability, budgets, implementation, veto points and composite indices. Section 8 lists datasets used in the academic literature. Section 9 is the recommended minimal download set for the execution session.

---

## 1. Legislative output — cross-national, ready-made

### Comparative Agendas Project (CAP) — the long-history backbone
- https://www.comparativeagendas.net/datasets_codebooks ; per-country pages `https://comparativeagendas.net/project/{country}/datasets`; files served openly from `https://minio.la.utexas.edu/compagendas/datasetfiles/…` (CSV, no login). Verified: yes (HEAD checks on files).
- Unit: one row per law (or per bill) with CAP major topic (21) + subtopic, year, description; most have month, legislature, type of law. PDF codebooks.
- Coverage for our countries (laws / bills, years, rows):
  - **Spain**: Laws 1980–2018 (2,256; has `type_of_law`: organic / ordinary / decree-law …); Parliamentary bills 1982–2017 (2,390); Executive bills 1977–2018 (1,945). Government vs MP bills are separate files.
  - **UK**: Acts of Parliament 1911–2015 (6,169); Statutory Instruments 1987–2022 (53,626); budgetary expenditure 1910–2007.
  - **France**: Laws 1979–2013 (3,069); government bills 1974–2013 (2,904); government decrees 1974–2013.
  - **Germany**: Laws 1976–2005 (3,137); bills 1976–2005 (5,787).
  - **Italy**: Primary laws 1983–2013 (4,554; page claims 1983–2021 but the file entry says Feb 2013, check); legislative decrees 1988–2013 (1,267).
  - **Netherlands**: Bills 1981–2009 (6,574; government + MP bills).
  - **Belgium**: Bills (lower house) 1988–2022 (15,682) with `bill_gov` / `bill_parl` dummies, introduction date and status ("AANGENOMEN KAMER" = became law) → pass rates by origin.
  - **Denmark**: Bills 1953–2016 (15,101).
  - **Ireland**: Bills 1922–2021 (5,526) with `billsource` (Government / Private Member), `enacted` 0/1, act year → pass rates by origin.
  - **Hungary**: Laws 1222–2024; Bills 1990–2022 (bonus country if wanted). **Switzerland** 1978–2008.
  - **Portugal**: "in development", codebook only, no data. **Poland**: in development, nothing. **No Austria, Sweden, Norway, Finland.**
- Fitness: best open, topic-coded, long-run source for 10 of our 13; but most laws series stop between 2005 and 2018. Needs splicing with §2 national sources or ParlLawSpeech for recent years.

### ParlLawSpeech (PLS) — recent years, text included
- https://parllawspeech.org/data/ ; archive at GESIS https://doi.org/10.7802/2824 (v1.0.0, 2025, CC BY 4.0, no registration). Format: `.RDS` per country (bills, laws, speeches). Verified: yes.
- Coverage (bills / laws): **Austria 1996–2019** (5,926 / 3,030); **Denmark 2007–2022** (3,615 / 3,220); **Germany 2009–2021** (2,445 / 1,638); **Spain 1996–2023** (4,188 / 1,563); **European Parliament 1999–2024** (14,105 / 10,554); plus Croatia, Czechia, Hungary.
- Variables: bills have title, text, `initiation_date`, `status` (final decision); laws have title, full text, `adoption_date`. No sponsor/origin field.
- Fitness: laws per year to 2019–2023 for AT, DK, DE, ES and the EP; full text enables the length-based significance proxy for free; bills with status give pass rates but not the government vs MP split.

### ParlText CEE (Harvard Dataverse) — covers Poland
- https://dataverse.harvard.edu/dataverse/parltext ; Laws DOI 10.7910/DVN/6NQXHF (v3, Feb 2026, CC0; CZ, HU, PL, SK). **Poland laws 1991–Aug 2023**, 4,807 rows with publication date, electoral cycle and CAP major topic. No bills yet. Verified: yes.

### Spanish Laws and Legislative Decrees 1982–2024 (Harvard Dataverse, Sept 2026) — best single file for Spain
- https://doi.org/10.7910/DVN/1VKJXZ , CC BY 4.0, XLSX. 2,367 measures with year/month, legislature, government type, PM, party, law type (ordinary / organic / decree-law / legislative decree), CAP topics. Verified: yes (Dataverse API).
- Fitness: replaces the CAP Spain laws file and extends it to 2024 with the decree flag built in.

### Bräuninger, Debus & Wüst (2017) replication — bill-level success by initiator
- https://doi.org/10.7910/DVN/27333 (CC0, Stata). 12,000+ bills, **Belgium, France, Germany, UK, 1986–2003**, bill success / event history by initiator (government vs parliamentary). Verified: yes.
- Fitness: the only ready-made government-bill pass-rate series for FR/DE/UK, but ends 2003.

### IPU Parline — the only official cross-national annual count
- https://data.ipu.org/ ; field `num_laws_adopt_parliament_per_year` ("annual number of laws adopted by parliament, lower chamber by default"), reference period 2013–2025. Per-country CSV export: `https://data.ipu.org/export-historical/num_laws_adopt_parliament_per_year/{ISO2}/csv`; data dictionary at `/data-dictionary/num_laws_adopt_parliament_per_year`. Licence CC BY-NC-SA 4.0. Live site blocks scripts (Cloudflare); verified via Wayback copies.
- Verified series: **ES 2013–2023** (2015 = 84, 2016 = 10, 2022 = 74, 2023 = 25; includes organic laws and legislative decrees); AT 2013–2024 (2021 = 223, 2024 = 140); FR 2013–2023 (2023 = 76); DE 2013–2023 (2021 = 197, 2023 = 107); IT 2013–2022 (2018 blank); NL 2013–2023 (2015, 2018 blank); BE, IE 2013–2023; NO 2020–2023; FI 2015–2023 (parliamentary year, not comparable). GB, PT, SE, DK, PL not in the archive copies, probably present live.
- Related fields: `total_laws_adopt_parliament_legislature`; `num_laws_initiat_executive` and `num_laws_init_parliament` (laws adopted in the previous legislature by initiator, per legislature not per year). No count of bills introduced.
- Fitness: cheap official cross-check for 2013 onward; blanks and definition differences mean it cannot be the primary series. The Spain 2016 value (10 laws in the year of the repeat election and ten-month caretaker spell) is exactly the kind of signal H2 predicts.

### Other academic sources (thinner)
- Döring & Hallerberg SPPL 1981–1991: 650 sampled bills, 18 countries, two policy fields only. Not a count dataset.
- BADELEY (Zenodo 10.5281/zenodo.7820758): ~10,000 Spanish national + regional laws 1977–2022 with vote counts; access restricted.
- Fukumoto "Legislative Production in Comparative Perspective": one observation per country, 1990s. Too thin.
- Search only: Regel/WZB (DE, FR, IT, UK proposals and votes from 2001); Calca Portugal legislative database 1982–2009 (MZES); QoG `ccl_nlp` climate-law counts. No dataset called "Lawmaking in Europe" or "European Legislative Output" exists.

### EU level (bonus "country")
- **EUR-Lex legal-acts statistics**: `https://eur-lex.europa.eu/statistics/legal-acts/{YYYY}/{MM}/legislative-acts-statistics-by-author.html`, years 1990–2026, monthly tables by author × act type × basic/amending, Export button (JS-rendered; curl gets HTTP 202). Verified.
- **Cellar SPARQL** https://publications.europa.eu/webapi/rdf/sparql — queried live; counts by `cdm:work_date_document` × resource type give e.g. 2018: 494 regulations / 133 directives / 902 decisions; 2024: 535 / 123 / 1,271. Implementing and delegated acts have separate types. R package `eurlex` wraps it. Verified.
- **European Parliament Open Data API v2** https://data.europarl.europa.eu/api/v2 (OpenAPI, CC BY 4.0, 500 req / 5 min): `/procedures`, `/procedures/{id}/events`, `/adopted-texts`; SPARQL at `/sparql`. Legislative Observatory https://oeil.europarl.europa.eu for procedure files. Verified.
- Fitness: EU output is fully computable from 1990; PLS EP laws 1999–2024 give a ready per-year count.

### Not useful
- OECD and World Bank publish no "laws enacted per year" indicator. Hugging Face has EU corpora (multi_eurlex, eurlex_resources) but nothing with national law counts. No GitHub repo with cross-national counts.

### Coverage map after §1 alone (before national APIs)
| Country | Long history | Recent years | Gov vs MP bills + pass rate |
|---|---|---|---|
| ES | CAP 1980–2018, Dataverse 1982–2024 | Dataverse to 2024, PLS to 2023, IPU 2013– | CAP bills to 2017/18 |
| UK | CAP Acts 1911–2015, SIs to 2022 | gap after 2015 (easy via legislation.gov.uk, see §2) | Bräuninger et al. to 2003 |
| FR | CAP 1979–2013 | gap after 2013, IPU 2013– | Bräuninger et al. to 2003 |
| DE | CAP 1976–2005 | PLS 2009–2021, IPU 2013– | Bräuninger et al. to 2003; CAP bills to 2005 |
| IT | CAP 1983–2013 | gap after 2013, IPU 2013–22 | — |
| NL | CAP bills 1981–2009 | gap after 2009, IPU 2013– (blanks) | CAP bills to 2009 |
| BE | CAP bills 1988–2022 | to 2022, IPU 2013– | CAP (gov/parl dummies, status) |
| DK | CAP bills 1953–2016 | PLS 2007–2022 | — |
| IE | CAP bills 1922–2021 | to 2021, IPU 2013– | CAP (`billsource`, `enacted`) |
| SE | nothing | nothing ready-made | — |
| PT | nothing | nothing ready-made | — |
| AT | PLS 1996–2019 | IPU 2013–2024 | IPU per-legislature only |
| PL | ParlText 1991–2023 | ParlText to 2023 | — |

---

## 2. Legislative output — national parliaments and gazettes

All verified by live fetch on 16 Oct 2026 unless marked. "Origin" = government vs parliament/member initiative; "Outcome" = passed / rejected / lapsed. Practical notes: send a browser User-Agent everywhere (Congreso, Portugal, Senato and the Belgian sites block curl); only the Bundestag DIP and Légifrance need a key; the Italian and Austrian endpoints are slow, cache locally.

### United Kingdom — easy to medium
- **legislation.gov.uk**: `https://www.legislation.gov.uk/ukpga/{year}/data.feed` (Atom) or `.../data.csv`; same for `uksi` (statutory instruments). No key. Facet totals give instant per-year counts (e.g. ukpga 2023 = 57, uksi 2023 = 1,139). Acts from 1267, SIs from 1948. Enacted stock only: no bills, outcomes or origin.
- **UK Parliament Bills API**: `https://bills-api.parliament.uk/api/v1/Bills` (OpenAPI at `/swagger/v1/swagger.json`), JSON, no key. Filters `Session`, `BillType` (Government, Private Members' variants, Private, Hybrid, Supply and Appropriation), `IsDefeated`, `IsWithdrawn`; each bill has `isAct`, sponsors (member + department → origin), `/Stages` with dates from first reading to Royal Assent. Usable from 2006–09, full from 2008–09.
- **Official stats**: Commons Library CBP-7438 *Acts and Statutory Instruments: the volume of UK legislation 1850 to 2019* and CBP-10489 *How much legislation does the UK Parliament consider?* (to July 2024). Search only (site blocks scripts).

### Spain — medium to hard for origin/outcome, easy for enacted-by-type
- **BOE API**: `https://www.boe.es/datosabiertos/api/legislacion-consolidada` with a JSON query on `rango` (Ley, Ley Orgánica, Real Decreto-ley, Real Decreto Legislativo) and `fecha_publicacion` range; JSON/XML, no key; fields `departamento`, `fecha_disposicion`, `fecha_publicacion`, `numero_oficial`. Back to 1978. Filter `departamento` = Jefatura del Estado to keep national laws and drop autonomous-community ones. Also `/api/boe/sumario/{yyyymmdd}` daily summaries.
- **Congreso datos abiertos**: `https://www.congreso.es/es/opendata/iniciativas` → timestamped CSV/JSON/XML files (ProyectosDeLey, ProposicionesDeLey, IniciativasLegislativasAprobadas, PropuestasDeReforma) with LEGISLATURA, AUTOR (→ origin), FECHAPRESENTACION, RESULTADOTRAMITACION (→ outcome), SITUACIONACTUAL; approved list has TIPO, NUMERO_LEY, FECHA_LEY. **Current legislature (XV) only.** Earlier legislatures need the iniciativas search or the Dataverse file in §1.
- **Official stats**: Congreso "Cuadro estadístico" per legislature on the iniciativas page. Search only.

### France — medium
- **Assemblée nationale open data**: bulk zips per legislature `https://data.assemblee-nationale.fr/static/openData/repository/{14|15|16|17}/loi/dossiers_legislatifs/Dossiers_Legislatifs….json.zip` (also XML), Licence Ouverte, no key. Dossiers carry projet vs proposition (→ origin), dépôt dates, each reading, promulgation (loi n°, date, JO). **2012 onward only** in structured form.
- **DILA "DOLE" dossiers législatifs**: `https://echanges.dila.gouv.fr/OPENDATA/DOLE/` (XML tar.gz bulk + daily deltas; also on data.gouv.fr). Laws and ordonnances **since June 2002** with nature (loi, loi organique, LFI/LFSS, ratification) and dates. Simplest route for 2002–2025 counts.
- **Sénat open data**: `https://data.senat.fr/` DOSLEG (PostgreSQL dumps, documents since 1977), AMELI, Monalisa. A dump, not an API.
- **Légifrance API (PISTE)**: free but registration + OAuth token, quotas. DOLE is simpler for counts.
- **Official stats**: AN *Statistiques de l'activité parlementaire* per legislature with annual bulletins; AN *Recueil des lois* 1967–2002; Sénat *Tableau de bord* PDFs per année parlementaire (textes définitivement adoptés split projets / propositions / conventions). Page/search.

### Germany — medium (needs a free key)
- **Bundestag DIP API**: `https://search.dip.bundestag.de/api/v1/vorgang?f.wahlperiode=20&f.vorgangstyp=Gesetzgebung` (OpenAPI at `/api/v1/openapi.yaml`), JSON/XML. Vorgang gives `initiative` (Bundesregierung / Bundesrat / Fraktion → origin), `beratungsstand` (verkündet / abgelehnt / für erledigt erklärt → outcome), dates, `verkuendung` (BGBl date), `zustimmungsbeduerftig`, GESTA code, `sachgebiet`. WP 8 (1976) onward; 2000–25 = WP 14–21. **A data call returned 401: an API key is mandatory** (free; request via the DIP help page or parlamentsdokumentation@bundestag.de; old demo keys have expired).
- **Official stats, no key needed**: *Statistik der Gesetzgebung* per Wahlperiode PDF (e.g. `gesetzgebung_wp20.pdf`, verified 200) with totals by initiator, verabschiedet, verkündet; **Datenhandbuch Kap. 10.1 "Statistik zur Gesetzgebung"** WP 12–20 (PDF verified 200). Together they give the whole 2000–25 series without the API.

### Italy — easy
- **Senato SPARQL**: `https://dati.senato.it/sparql`. `osr:Ddl` with `osr:tipoIniziativa` (Governativa / Parlamentare …), `osr:natura` (ordinaria / costituzionale / conversione DL / bilancio), `osr:statoDdl`, `osr:dataPresentazione`, `osr:numeroLegge`, `osr:dataLegge`. Legislatures 13–19 (1996–). A one-line query returns laws per year 1998–2026 (e.g. 2023 = 172 ddl with a law date). **Best single source for Italy.**
- **Camera SPARQL**: `https://dati.camera.it/sparql` (JSON, no key). `ocd:atto` with `ocd:iniziativa`, `ocd:rif_natura`, `ocd:rif_statoIter` ("Approvato definitivamente. Legge", "Ritirato", …), `dc:date`. All republican legislatures 1948– (leg. 18 = 7,514 atti). Camera-side states only; slow on heavy queries.
- **Normattiva / Gazzetta Ufficiale**: HTML + ELI URIs, no API. For decreti-legge counts if `natura` is not enough.
- **Official stats**: Senato *Statistiche sull'attività legislativa* per legislature (weekly, blocks scripts); Camera Osservatorio sulla legislazione dossiers. Search only.

### Netherlands — medium
- **Tweede Kamer OData**: `https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Zaak?$filter=Soort eq 'Wetgeving'` (and `'Initiatiefwetgeving'` → origin), `$count=true`, JSON, no key; SyncFeed for bulk. Fields Nummer, GestartOp, Vergaderjaar, Afgedaan, linked Besluit/Stemming (→ outcome). 2,551 Wetgeving zaken, reliable from 1 Sep 2008. Outcome needs a join on Besluit; docs partly outdated.
- **officielebekendmakingen.nl SRU**: `https://repository.overheid.nl/sru?operation=searchRetrieve&version=2.0&query=dt.type="wet" and dt.date>=2023-01-01` (XML; Staatsblad metadata: Wet / AMvB / Rijkswet, ministry, dates). From 1995 (240 wetten in 2000). Counts publications, not bills.
- **Official stats**: *Staat van de Kamer* annual PDF (bills by type with "aangenomen", 2019–24); Eerste Kamer *doorlooptijden wetsvoorstellen*. Search.

### Belgium — hard
- **data.dekamer.be**: the open-data portal says it is "in conceptual phase… test data, not up-to-date or complete"; the API index is WAF-blocked. Effectively **no usable API**. dekamer.be / lachambre.be dossier pages are HTML/PDF and reject non-browser requests; the Moniteur belge has no API.
- **Official stats**: Chamber *Statistiques* page for the current legislature (PDF tables of projets and propositions, monthly) and *Rapport annuel* PDFs with per-legislature tables since 1991 of projets/propositions déposés – adoptés – caducs. PDF transcription is the only route. The CAP Belgium bills file 1988–2022 (§1) is the real source here.

### Sweden — medium
- **Riksdagen open data**: `https://data.riksdagen.se/dokumentlista/?doktyp=prop&rm=2023/24&utformat=json` (also `bet`, `rskr`, `mot`, `sfs`); `dokumentstatus/{id}.json` gives dates and committee proposals; bulk zips from the dataset catalogue (CSV/JSON/XML/SQL). No key. Propositions back to 1971 (184 in 1999/2000); SFS from 1961 (175 in 2000, 112 in 2023, listing partial). No single "enacted law" entity: derive from `rskr` + `bet` outcome + SFS; origin = prop (government) vs mot (member), and nearly all laws are government props.
- **Official stats**: none standalone; partial tables in KU/RFR reports.

### Denmark — easy
- **Folketinget ODA**: `https://oda.ft.dk/api/Sag?$filter=typeid eq 3` (Lovforslag; OData v3 JSON, no key, `$inlinecount=allpages`). `kategoriid` 13 Regeringsforslag vs 12 Privat forslag (→ origin; 5,199 vs 139), `statusid` (Vedtaget / Stadfæstet / Forkastet / Bortfaldet → outcome), `periodeid` (samling), `lovnummer` / `lovnummerdato` (promulgation), `statsbudgetsag` flag. From samling 2004–05 (162) to 2023–24 (211). Map `periodeid` via `Periode`.
- **Official stats**: *Året, der gik i Folketinget* annual report with fremsatte/vedtagne lovforslag back to 1953–54 (fills 2000–04). Search.

### Ireland — easiest
- **Oireachtas API**: `https://api.oireachtas.ie/v1/legislation?bill_year=2023&bill_status=Enacted` (JSON, no key, Swagger at `/swagger.json`). `source` Government / Private Member (→ origin), `status` Enacted / Defeated / Lapsed / Withdrawn, `originHouse`, `events` with dates, `act.actNo` / `dateSigned`, stages. 1922 onward (70 bills in 2000, 36 enacted 2023). Statutory instruments not included (irishstatutebook.ie, HTML only).
- **Official stats**: Library & Research Service *The impact of Private Members' Bills* (2010–23); Commission annual reports. Search.

### Portugal — hard
- **Assembleia da República dados abertos**: `https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx` → *Iniciativas* per legislatura (I–XVII, 1976–), XML and JSON, monthly refresh. Download links are session-tokenised SharePoint handlers that returned HTML to curl; needs a browser session or the `app.parlamento.pt/webutils` path. Records include tipo (proposta de lei = government vs projeto de lei = members → origin), fases/votações, publication. Field schema unverified.
- **Official stats**: *Relatórios e Estatísticas da Atividade Parlamentar* per sessão/legislatura; DILP *Produção Legislativa Parlamentar: I à XIV Legislatura* PDF (by authorship, initiatives that became law). Search. Diário da República: HTML/ELI only.

### Austria — medium
- **Parlament filter JSON API**: `POST https://www.parlament.gv.at/Filter/api/filter/data/101?js=eval&showAll=true` with body `{"NRBR":["NR"],"GP_CODE":["XXVII"],"VHG":["RV"]}` (Regierungsvorlagen = government bills), `"VHG":["BNR"]` (Beschlüsse des Nationalrates = enactments, 1,351 in GP XXVII), `"ITYP":["A"]` (Initiativanträge, members). Rows have Datum, Art, Betreff, status/phase, Fraktionen, third-reading vote; any page `?json=TRUE` for detail. CC BY 4.0, no key. RV from GP XX (1996), Beschlüsse from GP XXII (2002). Codes undocumented (discover via the export dialog).
- **Official stats**: *Parlament in Zahlen* yearly; *Tagungsbilanz* press releases (Gesetzesbeschlüsse split RV / Initiativanträge / Ausschussanträge). Page/search.

### Poland — easy
- **Sejm API**: `https://api.sejm.gov.pl/sejm/term{7..10}/processes?limit=5000` (JSON, no key). `documentTypeEnum` BILL, `passed` true/false (→ outcome), `processStartDate`, `closureDate`, `urgencyStatus`, `stages` with dates, ELI link. Origin from the title prefix (Rządowy / Poselski / Senacki / Komisyjny / Obywatelski / Prezydencki); term 9: 538 government bills of which 513 passed; 308 member bills, 123 passed. Term 7 (2011) onward.
- **ELI / ISAP API**: `https://api.sejm.gov.pl/eli/acts/search?publisher=DU&year=2023&type=Ustawa&limit=500` (2000 = 159, 2010 = 233, 2023 = 148; types include Rozporządzenie). Dziennik Ustaw back to 1918. Counts acts including amendments.
- **Official stats**: *Podstawowe dane statystyczne dotyczące prac Sejmu* per kadencja (IV: 1,265 bills / 894 laws; VI: 1,511 / 952). Search (renders blank to curl).

### Ease ranking for "laws enacted per year by type and origin, 2000–2025"

| # | Country | Ease | Best single endpoint | Note |
|---|---|---|---|---|
| 1 | Ireland | Easy | Oireachtas `/v1/legislation` | Origin, status, dates, acts; 1922– |
| 2 | Italy | Easy | Senato SPARQL `osr:Ddl` | Origin, natura, law number/date; 1996– |
| 3 | Denmark | Easy | ODA `Sag?typeid eq 3` | Government vs private, status, law number; 2004– |
| 4 | Poland | Easy | Sejm `processes` + ELI `acts/search` | passed flag, origin in title; 2011– (ELI counts 1918–) |
| 5 | United Kingdom | Easy–medium | legislation.gov.uk feeds + Bills API | Instant yearly counts; origin/outcome from 2006 |
| 6 | Sweden | Medium | Riksdagen `dokumentlista` (prop + rskr + sfs) | Everything since 1971, "enacted" must be derived |
| 7 | Netherlands | Medium | Tweede Kamer OData `Zaak` | Wetgeving vs Initiatiefwetgeving; outcome via join; 2008– |
| 8 | France | Medium | AN dossiers zips + DILA DOLE | Rich; AN 2012–, DOLE 2002– |
| 9 | Austria | Medium | parlament.gv.at filter API | Works, undocumented codes; 1996–/2002– |
| 10 | Germany | Medium | DIP `vorgang` (key) or Datenhandbuch PDFs | Perfect data behind a free key |
| 11 | Spain | Medium–hard | BOE `legislacion-consolidada` + Dataverse 1982–2024 | Enacted-by-type easy; origin/outcome only for XV |
| 12 | Portugal | Hard | AR Iniciativas XML/JSON (SharePoint) | No API; DILP PDFs for history |
| 13 | Belgium | Hard | CAP bills file 1988–2022; Chamber PDFs after | Open-data portal still "conceptual" |

---

## 3. Government stability / cabinets (pillar P3)

### REPDEM (ex-ERDDA): REPDEM Basic + PAGED — **the pillar P3 backbone**
- https://repdem.org/index.php/current-dataset/ (erdda.org redirects here). Files: `repdem-basic-3.csv` and PDF codebook; PAGED Basic and PAGED WE+CEE (the Bergman/Bäck/Hellström *Coalition Governance in Western Europe* expert data).
- Coverage: REPDEM Basic v2026.07, 33 democracies, 1943 → 1 July 2026. PAGED Basic v2024.12 to end-2024; PAGED WE+CEE to 2019 (West) / 2021 (CEE).
- Variables: `date_in`, `date_out`, `cab_duration_days`, `cab_caretaker`, `cab_minority`, `cab_num_parties`, `cab_seatshare`, `cab_prefrange*` (ideological range), `form_duration` (days from previous `date_out` to new `date_in`), termination dummies `term_tech_regelec`, `term_disc_earlyelec`, `term_disc_cabdefeat` (lost confidence/no-confidence vote), `term_disc_voluntary`; WE+CEE adds `barg_total_duration`, `barg_fail_rounds`, investiture votes. Also "periodized" monthly/quarterly/yearly country-period files, which are index-ready.
- Format: CSV / XLSX / DTA, no registration. Verified: yes (codebooks downloaded).
- Fitness: gives caretaker days, formation delay, early elections and confidence defeats directly. Use this first.

### ParlGov 2024 release
- https://www.parlgov.org/ → data at https://doi.org/10.7910/DVN/2VZ5ZC (SQLite `parlgov-stable.db`, XLSX, `.tab` views, codebook).
- Coverage: 37 EU/OECD democracies, 1900–2023; ~1,600 cabinets, ~1,000 elections. `view_cabinet`: `election_date`, `start_date`, `caretaker`, `cabinet_party`, `prime_minister`, `seats`, `left_right`; `view_election`: `election_type`, seats, vote shares. No early-election flag; termination reasons only in the "experimental" DB.
- Last updated 12 Aug 2024; the maintainer announced retirement (Oct 2024), so treat as a frozen final release. Verified: yes.
- Fitness: clean seat-share / PM / party backbone and cross-check for REPDEM. Nothing after 2023.

### Comparative Political Data Set (CPDS) + Government Composition supplement
- https://cpds-data.org/data/ — 36 OECD/EU countries, 1960–2023, Stata/Excel + codebook; supplement has party composition, reshuffles, duration, reason for termination, type of government. Version June 2025. Verified: yes.
- Fitness: annual country-year format (government changes per year, cabinet type); second opinion on termination reasons.

### Golder (2010) bargaining delays; Ecker & Meyer (2020) bargaining rounds
- https://doi.org/10.7910/DVN/BUWZBA (16 W. European countries 1944–1998, `bargainingdays`); https://doi.org/10.7910/DVN/2XSNPC (303 bargaining attempts, 19 democracies). Verified: yes.
- Fitness: historical/replication only; REPDEM `form_duration` and `barg_*` supersede them for 2000–2025.

### Seki–Williams (Woldendorp/Keman/Budge update)
- https://doi.org/10.7910/DVN/0UNUAM — v3.0 (2016), through 2014. Verified: yes. Cross-check only.

### Bromo (2025, JoP) full-power vs caretaker event dataset
- "Full-Power Cabinets and Caretaker Administrations in Parliamentary Democracies, 1945–2024", 36 countries; data in the journal supplement (https://www.journals.uchicago.edu/doi/full/10.1086/738892). Search only.
- Fitness: the right denominator for "output per full-power governing day" if REPDEM's caretaker coding proves too coarse.

### Confidence motions / "days without government"
- No public cross-national motion-level dataset found. Use REPDEM `term_disc_cabdefeat`; compute caretaker days as the sum of `cab_caretaker` spells + `form_duration`.

---

## 4. Budget timeliness (pillar P2)

### IBP Open Budget Survey (OBS) — the only ready-made indicator, and it is sparse
- https://internationalbudget.org/open-budget-survey/download → `OBS_Full_Timeseries_2006_2025.xlsx` (8.7 MB; fetch with a browser user agent). Questionnaire PDF on the same site.
- The question: **Q109** (2017–2025 instrument; **q107** in 2015) "When does the legislature approve the Executive's Budget Proposal?" a = ≥1 month before the budget year; b = <1 month before but by the start; c = <1 month after; d = >1 month after or never; e = n/a. The 2006–2012 instrument has no equivalent.
- Coverage of our 13: ES, IT, PT (2010–2023), DE (2008–2023), UK, FR, PL, SE (2006–2023). **Not covered: NL, BE, DK, IE, AT.** None of the eight is in the 2025 round, so the series ends 2023, biennial.
- Sample letters pulled from the file (2017–2023): Spain b, e, b, b; Germany b, a, a, b; Portugal a, a, a, a; UK e/b/e/e (UK process scored "n/a"); Poland e, c, b, b. Verified: yes (file parsed).
- Fitness: use as the anchor and validation for a hand-built annual flag.

### OECD budgeting surveys (Budget Practices & Procedures 2007/2012/2018)
- https://www.oecd.org/en/data/datasets/public-finance-and-budgets-database.html — page blocked to fetchers; an SDMX sweep of all 1,550 OECD dataflows finds **no dataflow** for the 2018 BPP survey or approval timing. Verified: partial.
- Fitness: low; treat as unavailable unless microdata is requested from the OECD.

### Provisional / rolled-over budget episodes — no cross-national dataset exists; build it
- **Spain** (*presupuestos prorrogados*): roll-overs in force on 1 Jan 1979, 1983, 1996, 2012, 2017, 2018, 2019, 2020, 2024, 2025, 2026 (press lists: Forbes.es, Alicante Plaza, El Derecho). Hay Derecho *Informe Parlamento 2025* records that the last two governments are the only ones never to present a budget. Search snippets.
- **Italy** (*esercizio provvisorio*): 33 occurrences 1948–2018, none since 1988 (it.wikipedia citing Il Sole 24 Ore). Verified.
- **France** (*loi spéciale*): Dec 1979, Dec 2024 (2025 budget adopted Feb 2025), Dec 2025 (2026 budget, roughly six months without one) per Senate report a25-406. 2027 budget in the Assemblée since 13 Oct 2026 with no majority. Search.
- **Belgium** (*douzièmes provisoires*): episodes 1981–82, 1987–88, 1992, 2011, 2012, 2020, 2025; no consolidated list, compile from dekamer.be "crédits provisoires" bills. Partial.
- **Germany** (*vorläufige Haushaltsführung*, Art. 111 GG): applies "regularly" in post-election years; 2025 budget only promulgated 2 Oct 2025; compile from BMF/Bundestag promulgation dates. Partial.
- **UK / Ireland / Nordics**: concept differs (the UK Finance Bill routinely passes after 6 April; supply is secured by Votes on Account). Define the pillar as "appropriations legally in force on day 1 of the fiscal year" with per-country rules, and record the promulgation date of the main budget law each year.

---

## 5. Implementation (pillar P4)

### World Bank Worldwide Governance Indicators — Government Effectiveness
- https://www.worldbank.org/en/publication/worldwide-governance-indicators — 200+ economies, 1996–2025 (annual from 2002; 2026 update published), Excel/Stata with estimates, standard errors, percentile ranks. Verified: yes.
- Fitness: standard perception-based proxy; annual and complete for all 13. Sanity layer, not core.

### EU Single Market Scoreboard — transposition deficit and infringements
- https://single-market-scoreboard.ec.europa.eu/enforcement-tools/transposition_en and `.../infringements_en`. Per member state: transposition deficit %, long-overdue directives, average delay, conformity deficit, pending infringements, compliance with Court rulings. Current period to Nov 2025; EU-27 + EEA, **no UK after 2020**.
- Format: HTML dashboards and PDFs only, **no CSV**. Older editions at ec.europa.eu/internal_market/scoreboard/_docs/{year}/ and the Archive-It wayback copy. Verified: yes.
- Fitness: high conceptual fit, high effort (scrape PDFs/wayback for a 1997–2025 semi-annual series). Stretch goal.

### EUR-Lex national transposition measures / Cellar SPARQL
- https://eur-lex.europa.eu/collection/n-law/mne.html (renders empty to fetchers); SPARQL endpoint https://publications.europa.eu/webapi/rdf/sparql responds. Partial.
- Fitness: only for computing per-directive transposition lags yourself. Heavy; skip in v0.

### OECD iREG (Indicators of Regulatory Policy and Governance)
- SDMX CSV that works: `https://sdmx.oecd.org/public/rest/data/OECD.GOV.GIP,DSD_GOV_REG@DF_GOV_REG_2025,/all?format=csvfilewithlabels` (5,070 rows pulled). Editions 2014, 2017, 2021, 2024; all 13 countries incl. UK; stakeholder engagement / RIA / ex-post evaluation scores 0–4 for primary laws vs subordinate regulations. Verified: yes.
- Fitness: a "policy design quality" sub-score; only four time points.

### OECD Government at a Glance (same SDMX agency `OECD.GOV.GIP`)
- `DSD_GOV@DF_GOV_2025` main indicators, trust (`DF_GOV_TDG_2025`), governance of the policy cycle (`DF_GOV_GPC_2023`), 57 flows total. Verified via catalogue. Supplementary.

---

## 6. Veto points / institutional constraints (context pillar P5)

### Henisz POLCON 2025
- https://mgmt.wharton.upenn.edu/faculty/heniszpolcon/polcondataset/ → `POLCON_2025_FINALPOSTED.xlsx` (10 MB; posted March 2026). 1800–2025; `POLCONIII_2025`, `POLCONV_2025`, V-Dem-based components, legislative fractionalisation, executive/PM name and party. Verified: yes (downloaded).
- Fitness: direct annual veto-point measure for all 13 through 2025.

### Database of Political Institutions (DPI 2023, IDB)
- https://data.iadb.org/dataset/the-database-of-political-institutions-dpi-2023 — 180+ countries, 1975–2023; `CHECKS`, `CHECKS_LAX`, polarisation, government fractionalisation, stability of veto players, tenure. CSV/XLSX, CC BY 4.0, published March 2026. Verified: yes.
- Fitness: second veto-point measure; ends 2023.

### Tsebelis veto-player data
- No public download (umich pages 403). Substitute: REPDEM `cab_num_parties` + `cab_prefrange_*`; Angelova et al. data at https://madata.bib.uni-mannheim.de/240/ (not public). Search only.

### Comparative Constitutions Project
- https://comparativeconstitutionsproject.org/download-data/ — Characteristics of National Constitutions v5.0 (Feb 2025), Chronology of Constitutional Events v6.0. Verified: yes. Slow-moving controls (bicameralism, dissolution and no-confidence rules); also bundled in QoG.

---

## 7. Composite governance indices (sanity check, not scored)

### Bertelsmann Sustainable Governance Indicators (SGI)
- https://www.sgi-network.org/2024/Downloads (2024: 30 countries, all 13 included, Excel/SPSS/CSV + codebook); https://www.sgi-network.org/2022/Downloads (Scores 2014–2022 for 41 countries, "Time Series (Governance)" Excel, Executive Capacity reports). 2024 re-based the indicators, so 2009–2022 and 2024 are not comparable. Verified: yes.
- Fitness: best external "executive capacity" benchmark 2014–2022.

### EIU Democracy Index — "functioning of government"
- Sub-score exists 2006–2024 (confirmed via Our World in Data) but is **not downloadable** under licence; tables only in the annual report PDFs. Partial.
- Fitness: hand-transcribe 13 rows per year from the PDFs, or skip.

### V-Dem v16 (March 2026)
- https://www.v-dem.net/data/the-v-dem-dataset/ — Country-Year Core/Full CSV, free; R package `vdemdata`. Key index `v2xlg_legcon` (legislative constraints on the executive, 1789–2025) plus `v2x_jucon`, corruption indices. Verified: yes.
- Fitness: annual, complete, free.

### Quality of Government (QoG) Standard Dataset, January 2026 — one-stop aggregator
- https://www.gu.se/en/quality-government/qog-data/data-downloads/standard-dataset → `https://www.qogdata.pol.gu.se/data/qog_std_ts_jan26.csv` + 1,534-page codebook. 1946–2025 country-year, ~2,100 variables. **Bundles:** WGI, V-Dem (v13, older than live), POLCON, SGI, Open Budget Survey, CPDS, CCP, BTI, Freedom House, ICRG. **Not bundled:** DPI, ParlGov/REPDEM, EIU. Non-commercial use. Verified: yes.
- Fitness: one download covers most of §5–§7 at the cost of version lag.

### Hertie School Governance Report 2014
- https://www.hertie-school.org/en/governancereport/govreport-2014 — administrative-capacity dashboard with codebook + CSV. Search only. Prior art only; one-off.

---

## 8. Datasets from the literature (significance, pledges, decrees)

- **Civio decree-laws 1996–2024** (Spain): 499 decree-laws with dates, signatories, norms modified/repealed; CSV at https://datos.civio.es/dataset/decretos-ley-aprobados-desde-1996/ ; "Decretómetro" at https://civio.es/el-boe-nuestro-de-cada-dia/decretometro/ . Verified.
- **Hay Derecho, Informe Parlamento 2025** (Spain): decree-law share of norms by year, urgency procedures, budget non-presentation. https://www.hayderecho.com/informe-parlamento/ . Verified.
- **Spanish Legislative Amendments Dataset 1996–2023**: 117,575 amendments to government bills, CC BY (Data in Brief, 2026). https://diposit.ub.edu/items/f3ee101c-a60f-42ac-adb5-3063beef85bf/full . Verified.
- **Zubek, Dasgupta & Doyle (2021) replication**: 9,000+ UK statutory instruments 2009–16 with significance labels and PU-learning code. https://doi.org/10.7910/DVN/1XXDMW . Verified.
- **Thomson et al. (2017) Comparative Party Pledges Project**: 20,000+ pledges, 57 campaigns, 12 countries (AT, BG, CA, DE, IE, IT, NL, PT, ES, SE, UK, US). AJPS Dataverse https://dataverse.harvard.edu/dataverse/ajps . Verified (article); no central CPPP download page.
- **Sciences Po "EU Legislative Output 1999–2013"** (Dehousse & Rozenberg): texts × words index for EU, FR, UK. Seen via the LSE EUROPP blog only.
- **Angelova, Bäck, Müller & Strobl (2018) reform measures**, 13 countries 1985–2005: not public (https://madata.bib.uni-mannheim.de/240/).
- **Institute for Government, Parliamentary Monitor** (UK): government bills passed per session, SIs laid, bills rushed through in ≤5 sitting days, defeats. https://www.instituteforgovernment.org.uk/ (2021 PDF verified).
- **OCPI / Bank of Italy** (Italy): acts per year, words per act, instability index, 1950–2025 summary. https://osservatoriocpi.unicatt.it/ocpi-pubblicazioni-quantita-e-qualita-della-produzione-legislativa . Verified. **Openpolis Osservatorio legislativo** and **Osservatorio sulle fonti** for per-legislature counts. Search only.
- **Newtral** (Spain): laws per legislature since 1979 (I Legislatura 297; <30 ordinary + organic per legislature since 2015). Search only.

---

## 9. Recommended minimal download set for the execution session

Everything below is open, needs no registration, and is a plain file or a public endpoint. The one exception is the Bundestag DIP key (free, but someone has to email for it); the Datenhandbuch PDFs are the fallback.

**Phase A — ready-made files (covers P2, P3, P4, P5 and the historical half of P1)**
1. **REPDEM Basic v2026.07** governments CSV + periodized yearly file, and **PAGED WE+CEE** CSV (repdem.org) → caretaker days, formation delay, early elections, confidence defeats, coalition range. Add **ParlGov `parlgov-stable.db`** for seats/PM identity and as a cross-check.
2. **CAP laws/bills CSVs** for ES, UK, FR, DE, IT, NL, BE, DK, IE (comparativeagendas.net) + **Spanish Laws and Legislative Decrees 1982–2024** (Dataverse 1VKJXZ) + **ParlText CEE Poland laws** (Dataverse 6NQXHF) + **ParlLawSpeech** laws for AT, DK, DE, ES (GESIS 10.7802/2824) → the throughput backbone with topic codes and, via PLS, full text for length.
3. **IPU Parline** per-country CSV exports of `num_laws_adopt_parliament_per_year` for all 13 → official cross-check 2013 onward.
4. **OBS_Full_Timeseries_2006_2025.xlsx** (q107/q109) → budget-timeliness anchor for ES, UK, FR, DE, IT, PL, PT, SE; hand-build the annual flag for all 13 from the episode lists in §4.
5. **WGI 2026 Excel** (Government Effectiveness) + **iREG SDMX CSV** → implementation / sanity layer.
6. **POLCON_2025.xlsx** (+ **DPI 2023 CSV**) → veto points. **QoG `qog_std_ts_jan26.csv`** as the single fallback that bundles WGI, V-Dem, POLCON, SGI, OBS and CPDS.

**Phase B — national endpoints to extend P1 to 2025/26 (in order of payoff per hour)**
1. UK: legislation.gov.uk `ukpga` / `uksi` yearly feeds (minutes) + Bills API for origin and outcome 2006–.
2. Spain: BOE API by `rango` and year (minutes) + Congreso opendata for the XV legislature's outcomes.
3. Italy: Senato SPARQL laws per year with `natura` and `tipoIniziativa`.
4. Germany: Datenhandbuch 10.1 + per-WP Statistik PDFs (no key) or DIP API once a key arrives.
5. France: DILA DOLE bulk XML 2002– (nature, dates) + AN dossiers 2012– for origin and outcome.
6. Ireland, Denmark, Poland: one call each. Netherlands, Sweden, Austria: medium. Belgium, Portugal: stop at the ready-made files unless a fourth session is tolerated.

**Phase C — only if time remains**: Civio decree-law CSV (Spain) for pages and norms-modified; Zubek replication for the UK SI significance model; Single Market Scoreboard transposition deficit from PDFs/wayback; an LLM significance pass over titles + summaries.
