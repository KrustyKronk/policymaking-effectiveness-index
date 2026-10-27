# PEI v1 — Expansion source details

Compiled 17 October 2026 from three research passes. [F] = fetched or queried that day; [S] = search results only; [B] = background knowledge, verify before coding. Companion to [EXPANSION_BRAINSTORM.md](EXPANSION_BRAINSTORM.md).

## A. New countries — Western, Northern, Southern Europe

### Finland — easy
- **Laws:** Finlex Open Data API (Akoma Ntoso), no key. Use the query-parameter form: `https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/list?startYear=2020&endYear=2020&limit=…&langAndVersion=fin@` (the path form `/statute/2020/list` returns empty) [F]. Back to 1734 [F]. Each act has `finlex:typeStatute` (act vs decree), `finlex:categoryStatute` (e.g. amending) and bill references: HE = government bill, LA = member's bill [F].
- **Bills:** Eduskunta open data `https://avoindata.eduskunta.fi/api/v1/tables/` (JSON, no key) [F]; structured feed from ~2015 [S].
- **Budget:** a December parliamentary decision, not a law; never late [S].

### Norway — easy
- **Bills/cases:** `https://data.stortinget.no/eksport/saker?sesjonid=2002-2003` (XML/JSON, no key), sessions from 1986–87 [F]. Fields: `type` (lovsak / budsjett), `dokumentgruppe` (proposisjon = government, representantforslag = member), `status` [F]. Pass/reject needs the vedtak/votes endpoints [S].
- **Enacted laws:** Lovdata public bulk `https://api.lovdata.no/v1/publicData/list` → `lovtidend-avd1-2001-2025.tar.bz2` (69 MB, NLOD 2.0) [F]. Other Lovdata endpoints need a key from api@lovdata.no; not needed.
- **Budget:** December, never late [S]; source = `budsjett` cases.

### Iceland — easy
- **All:** Althingi XML, no key. Sessions `https://www.althingi.is/altext/xml/loggjafarthing/` (from 1875); items `thingmalalisti/?lthing=N` (`málstegund='l'` = bill); outcome `thingmal/?lthing=N&malnr=M` → `staðamáls` ("Samþykkt sem lög frá Alþingi"); origin `thingskjol/thingskjal/?…` → `skjalategund=stjórnarfrumvarp` [F].
- **Budget:** a law, item 1 of each autumn session; 2018 budget passed 29–30 Dec 2017 after a dissolution [F]; none found late [S].

### Luxembourg — easy (counts) / medium (origin)
- **Laws:** Legilux SPARQL `https://data.legilux.public.lu/sparqlendpoint`, filter `jolux:typeDocument` = `resource-type/LOI` [F]. Counts: 1980 = 91, 2000 = 82, 2020 = 159, 2025 = 131 [F].
- **Origin:** Chamber open data `chd.lu/en/open-data`, dataset "112" (projets vs propositions de loi), XLSX/CSV/XML [S] (page timed out).
- **Budget:** late 2014, 2019, 2024, each with a provisional-spending law for Jan–Apr and the budget law in late April [F]. Some years' titles missed by regex; re-check.

### Switzerland — medium
- **Parliament:** `https://ws.parlament.ch/odata.svc/` (Business, BusinessType, BusinessStatus, Vote), no key, from 1985 [F]. BusinessType 1 = Federal Council bill, 4 = parliamentary initiative, 3 = cantonal initiative [F].
- **Enacted acts:** Fedlex SPARQL `https://fedlex.data.admin.ch/sparqlendpoint`; type 21 = federal act, 22 = urgent federal act, 8 = simple federal decree [F]. **Counts need deduplication** (2000 = 445 vs 2024 = 68 because texts appear in both the official compilation and the federal gazette) [F].
- **CAP:** `https://minio.la.utexas.edu/compagendas/datasetfiles/switzerland_legislation.csv`, 1,420 rows 1978–2008 [F].
- **Budget:** a federal decree in December; 2017 first rejected in the overall vote then passed in the same session [S].

### Greece — hard
- **Parliament** (hellenicparliament.gr) returns 403 to scripts [F].
- **Gazette:** `POST https://searchetv99.azurewebsites.net/api/search` with `{"selectYear":["2010"],"selectIssue":["1"],…}` [F]; gives issue counts, not laws (no act type).
- **Workaround:** laws numbered continuously since 1975; annual count = number gap at year end [S].
- **Text corpora:** Greek Legal Code (Hugging Face `AI-team-UoA/greek_legal_code`, 1834–2015, thematic) [S]; Nomothesi@ RDF 1990–2019 [S].
- **Budget:** constitution requires a vote before the year; on time every year 2000–25 including 2012 and 2015 [S].

### Cyprus — medium
- **Laws:** `https://www.cylaw.org/nomoi/{YEAR}_arith_index.html` (ISO-8859-7 HTML, back to 1901) [F]. Numbering: N(I) = general, N(II) = budget laws, N(III) = treaty ratifications [F]. 2020: 215 / 20 / 9 [F].
- **Origin:** parliament.cy returns 403 [F].
- **Budget:** 2021 budget late (2(II)/2021); 2013 on time despite the crisis [F]; twelfths allowed to end of February [S].

### Malta — medium
- **Laws:** `https://legislation.mt/eli/act/{YEAR}/{N}/eng` with schema.org JSON-LD; enumerate N until 404 (year listing is JavaScript) [F]. Found for 1990–2024 [F].
- **Budget:** 2013 late (Appropriation Act = Act I of 2013, gazetted 16 April 2013, after the budget vote was lost in Dec 2012) [F].

## B. New countries — Central and Eastern Europe

Shared: **ParlText CEE** laws (Dataverse doi:10.7910/DVN/6NQXHF; file IDs CZ 12077946, HU 12077948, SK 12077947; comma-separated despite `.tab`): CZ 1990–2023, HU 1990–2024, SK 1991–2023; no type/origin but `bill_ID` [F]. **ParlLawSpeech** (GESIS 10.7802/2824): CZ 2013–23, HR 2003–20, HU 1994–2022 [F]. **CAP Hungary**: laws and decree-laws 1222–2024, bills 1990–2022 [F].

### Czechia — easy
- `https://www.psp.cz/sqw/hp.sqw?k=1300`: `opendata/sbirka.zip` (Collection of Laws from 1993, `druh_predpisu`: 1 = law, 14 = constitutional law, 2 = treaty) and `tisky.zip` (all bills since 1993; origin `typ_zakon`: VL government, PO/SP deputies, SE Senate; history and outcomes) [F]. Pipe-delimited, cp1250. Counts match ParlText exactly [F].
- **Budget:** provisional budget 1999, 2000, 2022, 2026 [S].

### Slovakia — medium
- ParlText SK 1991–2023 [F]; nrsr.sk HTML overviews (member bills `?sid=zakony/prehlad/poslanecke`, fast-track `?sid=zakony/prehlad/slk`, rejected, vetoed) [F]; Slov-Lex static HTML/PDF per act from 1918, no API found [S].
- **Budget:** mostly on time; 1999 possible late year [B].

### Hungary — easy
- ParlText HU + CAP Hungary [F]; parlament.hu open data behind a CAPTCHA [F].
- **Budget:** always before 1 January; two-year budgets 1999/2000, 2001/2002; since ~2016 adopted mid-year in advance [B].

### Slovenia — easy (best in the group)
- `https://fotogalerija.dz-rs.si/datoteke/opendata/SZ.XML` (33 MB): every adopted law since June 1991 with `KARTICA_PREDLAGATELJ` (government / deputies / National Council / voters) and `KARTICA_POSTOPEK` (regular / shortened / urgent / ratification) [F]. `PZ2.XML`–`PZ10.XML`: every bill since Nov 1996 with end status [F].
- **Budget:** temporary financing decrees 1997, 1998, Q1 2000, Jan–Jun 2001 [S].

### Croatia — medium
- Gazette ELI pages `narodne-novine.nn.hr/eli/sluzbeni/{year}/{issue}/{n}` with RDFa (`type_document` = ZAKON, dates) [F]; certificate chain incomplete, needs `curl -k` [F]. Origin from sabor.hr by scraping [B].
- **Budget:** temporary financing 2008, 2012, 2016 [S]; 2000, 2004 likely [B].

### Romania — medium
- Promulgated laws per year: `https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.lista?cam=2&anl=2015` (358 in 2015; years from 1996) [F]. "Proiect de lege" = government, "Propunere legislativă" = MP/citizen [F].
- Emergency ordinances: free SOAP `http://legislatie.just.ro/apiws/FreeWebService.svc/SOAP` (`GetToken` anonymous, `Search` by year/number/type) [F]; year filter misbehaved once, check.
- **Budget:** 2026 adopted 20 Mar [S]; 2001, 2009, 2013, 2017, 2020, 2021, 2025 late [B].

### Bulgaria — medium from 2009
- Undocumented JSON: `POST https://www.parliament.bg/api/v1/fn-acts/1` with `{"date1":"2015-01-01","date2":"2015-12-31","search":1,…}` (2015: 138 laws) [F]; nothing before June 2009 [F]. Bills `/api/v1/fn-bills` with importer [F]. Pre-2009: State Gazette (dv.parliament.bg) or lex.bg [B].
- **Budget:** extension laws for 2022, 2023, 2025, 2026 [S].

### Estonia — easy
- `https://api.riigikogu.ee` (spec `/v3/api-docs`), no key, **HTTP 429 after 2–3 rapid calls**: throttle ~1 call / 5 s [F]. `/api/volumes/drafts?membership=N`: `draftTypeCode` (SE = law), `initiator`, `activeDraftStatus` (e.g. AVALDATUD_RIIGITEATAJAS = published) [F]. Confirmed from 1999 [F].
- **Budget:** always December; constitution forces snap elections if not passed within two months [S].

### Latvia — hard-medium
- data.gov.lv `saeimas-sedes` only from 2016 [F]; likumi.lv no API [F]; Saeima annual reports give laws adopted (2016: 252, 2017: 278) [S].
- **Budget:** late 2019 [B] and 2023 (passed 9 Mar) [S].

### Lithuania — medium
- Seimas open data `https://www.lrs.lt/sip/portal.show?p_r=35391&p_k=1` (XML, CC BY): terms from 1990, sittings, votes, MP-initiated bills (`apps.lrs.lt/sip/p2b.ad_sn_inicijuoti_ta_projektai`) [F]; no adopted-laws list, rebuild from agendas and votes.
- **Budget:** December in recent years; election years 2000, 2008, 2012 unverified [B].

### Non-EU (not recommended for v1)
Ukraine `data.rada.gov.ua` (bills per convocation, JSON/CSV) [F reachable]; Georgia `matsne.gov.ge` [F reachable]; Montenegro `skupstina.me` [F]; Serbia, North Macedonia, Albania HTML-only; Moldova 403 [F].

## C. Going back in time — current 13

| Country | Laws source (earliest) | Notes |
|---|---|---|
| UK | `legislation.gov.uk/ukpga/{year}/data.feed` facets: 1950 = 50, 1975 = 83, 1999 = 35 [F]; CAP 1911–2015 | Pre-1963 Acts numbered by regnal session |
| Ireland | Oireachtas API; CAP 1922–2021 [F] | A 1950 query returned 41 bills dated 1951: check which date field the filter uses |
| Italy | Camera SPARQL `ocd:legge` by `dc:date`: 1948 = 116, 1950 = 508, 1972 = 77, 1987 = 108 [F]; legislature totals match published (Leg. I = 2,317) [F] | Provisional-budget laws also in SPARQL (1950–53, 1966, 1973 found) [F] |
| France | Senate "Statistiques pluriannuelles": 1959 = 51, 1980 = 49, 1988 = 23, 1994 = 71 [F]; session years from 1995–96 | Only budget failure: 1980 (decision 79-110 DC) [B] |
| Germany | offenegesetze.de federal gazette API from 1949 (1950 = 210 publications incl. regulations, filter titles) [F]; Datenhandbuch 1949–99 per term | DIP API from 1976 (key) |
| Spain | BOE `sumario` API answers for 1978–79 [F]; consolidated API not usable for counts [F] | Budget roll-overs 1979, 1983, 1996, 2012, 2017–20, 2024–26 [S] |
| Portugal | Diário da República from 1976 (scrape) [B]; DILP report I–XIV [S] | Duodécimos 1996, 2016, 2020, 2022 (+2000, 2010) |
| Netherlands | CAP bills 1981–2009; Staatsblad API from 1995; Delpher scans earlier [S] | — |
| Belgium | CAP bills 1988–2022; earlier scans only [S] | 1986 bill: budgets "never voted before 1 January since 1830" [S] |
| Sweden | Government bills from 1971 [F]; **SFS API returned 128 for 1975, mostly in-force statutes** [F] | Fiscal year July–June until 1996 |
| Denmark | CAP bills 1953–2016 [F]; annual reports | Temporary appropriation acts searchable in Folketingstidende |
| Austria | RIS BgblPdf: 32,910 gazette documents 1945–2003 [F]; year parameter name to check | Budget provisoria in election years |
| Poland | Sejm ELI `/eli/acts/DU/{year}` type Ustawa: 1989 = 94, 1991 = 117, 1995 = 94 [F] | Democratic from Oct 1991 |

**Cross-national long-run datasets:** CAP (above); IPU Parline (2013– only); Döring/Tsebelis significant laws 1981–91 (validation only); Bromo 2025 caretaker dataset 1945–2024 (36 democracies, JoP supplement) [S]; CPDS government composition 1960–2023 [S].
