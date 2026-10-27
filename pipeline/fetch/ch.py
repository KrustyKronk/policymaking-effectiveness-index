"""Switzerland: parliament OData -> bills_ch.csv; Fedlex SPARQL -> laws_ch.csv (deduplicated), counts_ch.csv.

(1) Parliament: https://ws.parlament.ch/odata.svc/ (JSON, Language 'DE'), one page set per year:
    Business (BusinessType 1 = Geschäft des Bundesrates -> government, 4 = Parlamentarische Initiative ->
    parliament, 3 = Standesinitiative -> other; SubmissionDate in the year), Bill (the draft acts attached to
    a business, with BillTypeName: Bundesgesetz / Bundesbeschluss / Einfacher Bundesbeschluss / Verordnung)
    and Resolution (council decisions per bill, by ResolutionDate). BusinessStatus is only a coarse
    history ("Im Rat noch nicht behandelt", "Behandelt vom Nationalrat", "Von beiden Räten behandelt",
    "Folge gegeben", "Erledigt"); "Erledigt" covers adopted, rejected and written-off alike, so the outcome
    comes from the resolution texts (see OUTCOME MAPPING above classify()/outcome()): any bill of the business
    adopted in a final vote -> enacted; else a final-vote / overall-vote / conciliation rejection -> rejected;
    else not "Erledigt" -> pending; else the last classifiable resolution (accept -> enacted, reject -> rejected,
    abgeschrieben -> lapsed, zurückgezogen -> withdrawn), none -> other. Popular votes that later defeat an
    adopted act (optional referendum) are not in the OData, so such bills stay "enacted" in bills_ch.csv.
    bills_ch.csv holds businesses of types 1/4/3 submitted 2000-2025 (outcome as of the fetch date).

(2) Fedlex: https://fedlex.data.admin.ch/sparqlendpoint, acts of type 21 (Bundesgesetz) and 22 (dringliches
    Bundesgesetz) with jolux:dateDocument (= date of adoption, the final vote) in the year. The same act is
    published in the federal gazette (family fga: draft and referendum text) and the official compilation
    (family oc) and consolidated in the SR (family cc); the raw type-21/22 count over all families double-counts
    (2000: 445). DEDUP: the query keeps only family oc, and rows are keyed by the oc act URI, so each adopted act
    is one row (2000: 57). Validated against CAP Switzerland: of 378 CAP "law" rows adopted 2000-2008, 363 match
    one Fedlex act on (adoption date, AS publication date); 14 of the 15 CAP-only rows have no AS date (defeated
    in a referendum); the Fedlex-only rows are mostly 2008 acts published after CAP's cut-off. Acts adopted but not (yet) in the AS - referendum pending or
    failed - are therefore absent; 2025 is incomplete for that reason. Origin: the dateDocument is the
    final-vote date, so it is matched against the bills adopted in a final vote that same day (bills of 1999
    businesses and older/other-type businesses are fetched for this lookup only), by title tokens, by a
    single-origin day, or by rare shared tokens (see match_origin; column origin_match); else unknown (~35%).
    The budget (Voranschlag) is a federal decree, not a law: no budget_law rows; treaty approvals are
    Bundesbeschlüsse, so ratification appears only in bills_ch.csv.

(3) CAP Switzerland legislation 1978-2008 (minio.la.utexas.edu, raw/ch/switzerland_legislation.csv; columns id,
    year, majortopic, subtopic, description (French title), source (AS publication date), date (adoption date),
    type (law / decree / treaty / popular_initiative / constitution / counter_proposal), filter_enacted_legislation).
    1978-1999: rows with type 'law' and filter_enacted_legislation == 1 -> laws_ch.csv (source cap_ch, year = year
    of the adoption date, origin unknown: the file has no initiator), the same instrument as Fedlex types 21/22.
    2000-2008: per-year overlap CAP (same filter) vs Fedlex logged and written to raw/ch/cap_overlap.csv.

If Fedlex fails entirely, laws_ch.csv is written from the parliament side (enacted businesses with a
Bundesgesetz bill) and the log says so."""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import re
import time
import unicodedata

import pandas as pd

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

D = RAW / "ch"
ODATA = "https://ws.parlament.ch/odata.svc/"
FEDLEX = "https://fedlex.data.admin.ch/sparqlendpoint"
CAP_URL = "https://minio.la.utexas.edu/compagendas/datasetfiles/switzerland_legislation.csv"
YEARS = range(2000, 2026)
CAP_YEARS = range(1978, 2000)
ORIGIN = {1: "government", 4: "parliament", 3: "other"}
PAGE = 1000

# --- OUTCOME MAPPING (resolution texts, lower-cased, trailing dot stripped) ------------------------------
# final decisions: a final vote (Schlussabstimmung) is the last word for acts subject to referendum
FINAL_ENACT = ("annahme in der schlussabstimmung", "die verordnung der bundesversammlung wird in der schlussabstimmung ang",
               "das geschäftsreglement wird in der schlussabstimmung angenommen")
FINAL_REJECT = ("ablehnung in der schlussabstimmung", "ablehnung in der gesamtabstimmung",
                "das bundesgesetz wird in der gesamtabstimmung abgelehnt", "der antrag der einigungskonferenz wird abgelehnt",
                "ablehnung des antrages der einigungskonferenz")
# non-final decisions: the chronologically last one decides once the business is "Erledigt"
ACCEPT = ("zustimmung", "beschluss gemäss entwurf", "beschluss abweichend vom entwurf",
          "beschluss gemäss antrag der einigungskonferenz", "beschluss nach entwurf der kommission", "annahme",
          "folge gegeben", "folge geben", "beschluss gemäss antrag", "beschluss, einen erlassentwurf")
REJECT = ("keine folge gegeben", "keine folge geben", "zustimmung (= nichteintreten)", "festhalten (= nichteintreten)",
          "nichteintreten", "nicht eintreten", "ablehnung", "keine zustimmung",
          "verwerfung", "dringlichkeit abgelehnt")
LAPSED = ("abgeschrieben", "abschreibung")
WITHDRAWN = ("zurückgezogen", "rückzug")


def classify(text: str) -> str | None:
    t = (text or "").strip().lower().rstrip(".")
    for group, name in ((FINAL_ENACT, "final_enact"), (FINAL_REJECT, "final_reject"), (LAPSED, "lapsed"),
                        (WITHDRAWN, "withdrawn"), (REJECT, "reject"), (ACCEPT, "accept")):
        if any(t.startswith(k) for k in group):
            return name
    return None


def outcome(resolutions: list[dict], status_text: str) -> str:
    """resolutions: [{date, text}] over all bills of the business."""
    kinds = [(r["date"], classify(r["text"])) for r in sorted(resolutions, key=lambda r: r["date"] or "")]
    kinds = [(d, k) for d, k in kinds if k]
    # a business can carry several bills: one adopted in a final vote makes the business "enacted"
    if any(k == "final_enact" for _, k in kinds):
        return "enacted"
    if any(k == "final_reject" for _, k in kinds):
        return "rejected"
    if status_text != "Erledigt":
        return "pending"
    if not kinds:
        return "other"
    last = kinds[-1][1]
    return {"accept": "enacted", "reject": "rejected", "lapsed": "lapsed", "withdrawn": "withdrawn"}.get(last, "other")


# --- helpers ---------------------------------------------------------------------------------------------
def odata_date(v) -> str | None:
    m = re.match(r"/Date\((-?\d+)", str(v or ""))
    if not m:
        return None
    return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=int(m.group(1)))).date().isoformat()


def odata_pages(entity: str, flt: str, select: str, tag: str) -> list[dict]:
    out, skip = [], 0
    while True:
        dest = D / f"{tag}_p{skip // PAGE:02d}.json"
        cached = dest.exists()
        j = json.loads(get(ODATA + entity, dest, headers={"Accept": "application/json"},
                           params={"$format": "json", "$filter": flt, "$select": select, "$top": PAGE, "$skip": skip},
                           timeout=180).decode("utf-8"))
        if not cached:
            time.sleep(0.3)
        d = j.get("d", j)
        rows = d if isinstance(d, list) else d.get("results", [])
        out.extend(rows)
        if len(rows) < PAGE:
            return out
        skip += PAGE


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").lower()
    t = re.sub(r"\([^)]*\)", " ", t)                       # abbreviations / sub-titles in brackets
    t = re.sub(r"\bvom \d{1,2}\. \w+ \d{4}\b", " ", t)       # "vom 14. Juni 2024"
    t = re.sub(r"[^a-z0-9äöüß ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# --- parliament ------------------------------------------------------------------------------------------
def fetch_parliament() -> tuple[list[dict], dict[int, list[dict]], dict[str, list[dict]]]:
    businesses, bills_by_business, res_by_bill = [], {}, {}
    for y in range(1999, 2026):  # 1999 only feeds the origin lookup for acts adopted in 2000-01
        try:
            businesses += odata_pages(
                "Business",
                f"Language eq 'DE' and (BusinessType eq 1 or BusinessType eq 4 or BusinessType eq 3) "
                f"and year(SubmissionDate) eq {y}",
                "ID,BusinessShortNumber,BusinessType,BusinessTypeName,Title,SubmissionDate,BusinessStatus,"
                "BusinessStatusText,BusinessStatusDate,ResponsibleDepartmentAbbreviation", f"business_{y}")
        except Exception as e:  # noqa: BLE001
            log.warning("ch business %d failed: %s", y, e)
    for y in range(1999, 2026):
        try:
            for b in odata_pages("Bill", f"Language eq 'DE' and BusinessNumber ge {y}0000 and BusinessNumber lt {y + 1}0000",
                                 "ID,BusinessNumber,BillNumber,BillType,BillTypeName,Title,BusinessStatusText",
                                 f"bill_{y}"):
                bills_by_business.setdefault(int(b["BusinessNumber"]), []).append(b)
        except Exception as e:  # noqa: BLE001
            log.warning("ch bills %d failed: %s", y, e)
    for y in range(2000, 2027):
        try:
            for r in odata_pages("Resolution",
                                 f"Language eq 'DE' and ResolutionDate ge datetime'{y}-01-01T00:00:00' "
                                 f"and ResolutionDate lt datetime'{y + 1}-01-01T00:00:00'",
                                 "ID,IdBill,ResolutionNumber,ResolutionId,ResolutionText,ResolutionDate,CouncilAbbreviation",
                                 f"resolution_{y}"):
                res_by_bill.setdefault(r["IdBill"], []).append(
                    {"date": odata_date(r["ResolutionDate"]), "text": r.get("ResolutionText") or "",
                     "council": r.get("CouncilAbbreviation")})
        except Exception as e:  # noqa: BLE001
            log.warning("ch resolutions %d failed: %s", y, e)
    return businesses, bills_by_business, res_by_bill


BUSINESS_SELECT = ("ID,BusinessShortNumber,BusinessType,BusinessTypeName,Title,SubmissionDate,BusinessStatus,"
                   "BusinessStatusText,BusinessStatusDate,ResponsibleDepartmentAbbreviation")


def fetch_orphans(businesses: list[dict], bills_by_business: dict[int, list[dict]],
                  res_by_bill: dict[str, list[dict]]) -> None:
    """Bills adopted in a final vote 2000-2026 whose business predates 1999 (or is of another type, e.g. 2 =
    Geschäft des Parlaments) are not in the yearly pages: fetch each such bill and its business by ID (cached
    as raw/ch/orphan_bill_<guid>.json / orphan_business_<n>.json) so the Fedlex origin match sees them."""
    known = {bl["ID"] for v in bills_by_business.values() for bl in v}
    have = {int(b["ID"]) for b in businesses}
    orphans = sorted(bid for bid, rs in res_by_bill.items()
                     if bid not in known and any(classify(r["text"]) == "final_enact" for r in rs))
    for bid in orphans:
        try:
            rows = odata_pages("Bill", f"Language eq 'DE' and ID eq guid'{bid}'",
                               "ID,BusinessNumber,BillNumber,BillType,BillTypeName,Title,BusinessStatusText",
                               f"orphan_bill_{bid}")
        except Exception as e:  # noqa: BLE001
            log.warning("ch orphan bill %s failed: %s", bid, e)
            continue
        for b in rows:
            bn = int(b["BusinessNumber"])
            bills_by_business.setdefault(bn, []).append(b)
            if bn in have:
                continue
            try:
                businesses += odata_pages("Business", f"Language eq 'DE' and ID eq {bn}", BUSINESS_SELECT,
                                          f"orphan_business_{bn}")
                have.add(bn)
            except Exception as e:  # noqa: BLE001
                log.warning("ch orphan business %d failed: %s", bn, e)
    log.info("ch: %d final-vote bills outside the yearly pages fetched by ID", len(orphans))


RE_TREATY = re.compile(r"abkommen|übereinkommen|vertrag|protokoll|konvention|charta", re.I)


def bill_instrument(bills: list[dict], business_title: str) -> str:
    names = [(b.get("BillTypeName") or "", b.get("Title") or "") for b in bills]
    if any(n.startswith("Bundesgesetz") or n.startswith("Dringliches Bundesgesetz") for n, _ in names):
        return "law"
    if any("verfassung" in t.lower() for _, t in names) or "bundesverfassung" in business_title.lower():
        return "constitutional_law"
    if any(n.startswith("Bundesbeschluss") and "genehmigung" in t.lower() and RE_TREATY.search(t) for n, t in names):
        return "ratification"
    return "other"


def build_bills(businesses, bills_by_business, res_by_bill) -> pd.DataFrame:
    rows = []
    for b in businesses:
        bid = int(b["ID"])
        sub = odata_date(b.get("SubmissionDate")) or ""
        if int(b["BusinessType"]) not in ORIGIN or not ("2000" <= sub[:4] <= "2025"):
            continue  # 1999 and orphan businesses only feed the Fedlex origin lookup
        bills = bills_by_business.get(bid, [])
        res = [r for bl in bills for r in res_by_bill.get(bl["ID"], [])]
        status = b.get("BusinessStatusText") or ""
        oc = outcome(res, status)
        final_votes = sorted(r["date"] for r in res if classify(r["text"]) in ("final_enact", "final_reject") and r["date"])
        rows.append({
            "country": "CH", "bill_id": b.get("BusinessShortNumber") or str(bid), "title": b.get("Title"),
            "year_introduced": int((odata_date(b.get("SubmissionDate")) or str(bid)[:4])[:4]),
            "origin": ORIGIN.get(int(b["BusinessType"]), "other"), "outcome": oc,
            "date_introduced": odata_date(b.get("SubmissionDate")),
            "date_final": final_votes[-1] if final_votes else (odata_date(b.get("BusinessStatusDate")) if status == "Erledigt" else None),
            "instrument_type": bill_instrument(bills, b.get("Title") or ""), "source": "parlament_ch_odata",
            "business_type": b.get("BusinessTypeName"), "status": status, "n_bills": len(bills),
            "bill_titles": " || ".join((bl.get("Title") or "") for bl in bills),
            "bill_types": " || ".join((bl.get("BillTypeName") or "") for bl in bills),
            "last_resolution": max(res, key=lambda r: r["date"] or "")["text"] if res else None,
        })
    return pd.DataFrame(rows)


# --- Fedlex ----------------------------------------------------------------------------------------------
FX_QUERY = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?a ?t ?d ?pub ?title ?sr WHERE {
  VALUES ?t { <https://fedlex.data.admin.ch/vocabulary/resource-type/21>
              <https://fedlex.data.admin.ch/vocabulary/resource-type/22> }
  ?a jolux:typeDocument ?t ; jolux:dateDocument ?d ;
     jolux:legalResourceFamilyType <https://fedlex.data.admin.ch/vocabulary/resource-family/oc> .
  FILTER(YEAR(?d) = %d)
  OPTIONAL { ?a jolux:publicationDate ?pub }
  OPTIONAL { ?a jolux:historicalId ?sr }
  OPTIONAL { ?a jolux:isRealizedBy ?e . ?e jolux:title ?title .
             ?e jolux:language <http://publications.europa.eu/resource/authority/language/DEU> }
}"""


def fetch_fedlex(year: int) -> list[dict]:
    dest = D / f"fedlex_oc_{year}.json"
    cached = dest.exists()
    raw = get(FEDLEX, dest, params={"query": FX_QUERY % year}, headers={"Accept": "application/sparql-results+json"},
              timeout=240)
    if not cached:
        time.sleep(0.3)
    return json.loads(raw.decode("utf-8"))["results"]["bindings"]


# origin for the Fedlex match: business types 1/4/3 as in bills_ch.csv, plus 2 (Geschäft des Parlaments, e.g.
# the Parlamentsgesetz) -> parliament
LAW_ORIGIN = {**ORIGIN, 2: "parliament"}
STOP = set("der die das des dem den und uber vom von zum zur zu im in fur an auf mit betreffend sowie "
           "bundesgesetz bundesgesetzes gesetz anderung schweizerisches schweizerische".split())


def toks(t: str) -> set[str]:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\bvom \d{1,2}\. \w+ \d{4}\b", " ", t)
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in STOP and len(w) > 1}


def origin_lookup(businesses, bills_by_business, res_by_bill):
    """final-vote date -> ([(token set of bill + business title, origin)], all final votes that day mapped?)"""
    btype = {int(b["ID"]): LAW_ORIGIN.get(int(b["BusinessType"]), "other") for b in businesses}
    btitle = {int(b["ID"]): b.get("Title") or "" for b in businesses}
    known = {bl["ID"] for v in bills_by_business.values() for bl in v}
    by_date: dict[str, list[tuple[set[str], str | None]]] = {}
    complete: dict[str, bool] = {}
    for bid, rs in res_by_bill.items():
        for d in {r["date"] for r in rs if classify(r["text"]) == "final_enact" and r["date"]}:
            complete[d] = complete.get(d, True) and bid in known
    for bn, bills in bills_by_business.items():
        for bl in bills:
            for d in {r["date"] for r in res_by_bill.get(bl["ID"], []) if classify(r["text"]) == "final_enact" and r["date"]}:
                by_date.setdefault(d, []).append((toks(bl.get("Title")) | toks(btitle.get(bn)), btype.get(bn)))
    return by_date, complete


def match_origin(title: str, date: str, by_date, complete, df: dict[str, int] | None = None) -> tuple[str, str]:
    """-> (origin, method). Fedlex dateDocument is the final-vote date, so candidates are the bills adopted in a
    final vote that day. (a) title: best token containment >= 0.5 and no runner-up of another origin with the same
    score; (b) day: every final vote that day is mapped to a business and all share one origin; (c) idf: Fedlex
    titles name the amended act ("Bundesgesetz über die Krankenversicherung (KVG)") while bills name the reform,
    so a weaker match is accepted when the shared tokens carry >= 25% of the title's idf weight, include a rare
    token (in <= 8 titles, e.g. "schkg", "co2", "tabaksteuergesetz") and beat every other-origin candidate by 1.5x."""
    cands = by_date.get(date, [])
    ta = toks(title)
    scored = sorted(((len(ta & tb) / max(1, min(len(ta), len(tb))), o) for tb, o in cands),
                    key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.5 and scored[0][1]:
        top = {o for sc, o in scored if sc == scored[0][0]}
        if len(top) == 1:
            return scored[0][1], "title"
    origins = {o for _, o in cands}
    if cands and complete.get(date) and len(origins) == 1 and None not in origins:
        return origins.pop(), "day"
    if df and cands:
        n = max(df.values())
        idf = {w: math.log(n / df.get(w, 1)) for w in ta}
        tot = sum(idf.values()) or 1.0
        sc = sorted(((sum(idf[w] for w in ta & tb) / tot, o, ta & tb) for tb, o in cands), key=lambda x: -x[0])
        best, o, shared = sc[0]
        rival = max((s for s, o2, _ in sc if o2 != o), default=0.0)
        if o and best >= 0.25 and best >= 1.5 * rival and any(df.get(w, 0) <= 8 for w in shared):
            return o, "idf"
    return "unknown", ""


def build_laws_fedlex(by_date, complete) -> pd.DataFrame | None:
    laws, failed = {}, 0
    fx: dict[int, list[dict]] = {}
    for y in YEARS:
        try:
            fx[y] = fetch_fedlex(y)
        except Exception as e:  # noqa: BLE001
            log.warning("ch fedlex %d failed: %s", y, e)
    # document frequency over Fedlex titles + candidate bill titles ("__n__" holds the corpus size)
    docs = [toks(b.get("title", {}).get("value", "")) for rows in fx.values() for b in rows]
    docs += [tb for v in by_date.values() for tb, _ in v]
    df = collections.Counter(w for d in docs for w in d)
    df["__n__"] = len(docs)
    for y in YEARS:
        if y not in fx:
            failed += 1
            continue
        rows = fx[y]
        n0 = len(laws)
        for b in rows:
            uri = b["a"]["value"]
            if uri in laws:
                continue
            title = re.sub(r"\s+", " ", b.get("title", {}).get("value", "")).strip()
            date = b["d"]["value"][:10]
            origin, how = match_origin(title, date, by_date, complete, df)
            laws[uri] = {
                "country": "CH", "year": int(date[:4]), "date": date, "instrument_type": "law", "origin": origin,
                "title": title, "length_words": None, "cap_topic": None, "is_budget": False, "is_ratification": False,
                "source": "fedlex_sparql", "source_id": uri, "source_url": uri,
                "urgent": b["t"]["value"].endswith("/22"), "as_reference": b.get("sr", {}).get("value"),
                "publication_date": b.get("pub", {}).get("value", "")[:10] or None, "origin_match": how or None,
            }
        log.info("ch fedlex %d: %d raw rows -> %d acts", y, len(rows), len(laws) - n0)
    if failed == len(YEARS):
        return None
    return pd.DataFrame(list(laws.values()), columns=LAWS_COLUMNS + ["urgent", "as_reference", "publication_date", "origin_match"])


def build_laws_parliament(bills_df: pd.DataFrame) -> pd.DataFrame:
    sub = bills_df[(bills_df.outcome == "enacted") & (bills_df.instrument_type == "law")]
    rows = []
    for _, b in sub.iterrows():
        date = b["date_final"] or f"{b['year_introduced']}-01-01"
        rows.append({"country": "CH", "year": int(date[:4]), "date": date, "instrument_type": "law", "origin": b["origin"],
                     "title": b["title"], "length_words": None, "cap_topic": None, "is_budget": False,
                     "is_ratification": False, "source": "parlament_ch_odata", "source_id": b["bill_id"],
                     "source_url": f"https://www.parlament.ch/de/ratsbetrieb/suche-curia-vista/geschaeft?AffairId={b['bill_id'].replace('.', '')}"})
    return pd.DataFrame(rows, columns=LAWS_COLUMNS)


def cap_laws() -> pd.DataFrame:
    """CAP Switzerland enacted federal laws adopted 1978-1999 as laws_ch rows."""
    try:
        get(CAP_URL, D / "switzerland_legislation.csv", timeout=180)
        cap = pd.read_csv(D / "switzerland_legislation.csv", low_memory=False)
    except Exception as e:  # noqa: BLE001
        log.warning("ch CAP file unavailable, no 1978-1999 rows: %s", e)
        return pd.DataFrame(columns=LAWS_COLUMNS)
    cap = cap[(cap["type"] == "law") & (cap["filter_enacted_legislation"] == 1)].copy()
    d = pd.to_datetime(cap["date"], errors="coerce")
    cap["y"] = d.dt.year.fillna(cap["year"]).astype(int)
    cap = cap[cap["y"].isin(CAP_YEARS)]
    return pd.DataFrame({
        "country": "CH", "year": cap["y"], "date": d[cap.index].dt.strftime("%Y-%m-%d").fillna(cap["y"].astype(str) + "-01-01"),
        "instrument_type": "law", "origin": "unknown", "title": cap["description"], "length_words": None,
        "cap_topic": cap["majortopic"], "is_budget": False, "is_ratification": False, "source": "cap_ch",
        "source_id": "cap_ch_" + cap["id"].astype(str), "source_url": CAP_URL, "urgent": None,
        "as_reference": None, "publication_date": cap["source"], "origin_match": None})


def cap_crosscheck(laws_df: pd.DataFrame) -> None:
    """CAP Switzerland (1978-2008): rows of type 'law' carry the adoption date (`date`) and the AS publication date
    (`source`), the same pair as Fedlex dateDocument / publicationDate, so overlap is counted on that pair."""
    try:
        get(CAP_URL, D / "switzerland_legislation.csv", timeout=180)
        cap = pd.read_csv(D / "switzerland_legislation.csv", low_memory=False)
        cap = cap[(cap["type"] == "law") & cap["year"].between(2000, 2008)]
        ours = laws_df[laws_df["year"].between(2000, 2008)] if "publication_date" in laws_df else laws_df.iloc[0:0]
        cc = collections.Counter(zip(cap["date"], cap["source"]))
        oc = collections.Counter(zip(ours["date"], ours.get("publication_date", pd.Series(dtype=str))))
        both = sum((cc & oc).values())
        log.info("ch CAP cross-check 2000-2008: CAP laws %d, Fedlex acts %d, matched on (adoption, AS date) %d; "
                 "CAP-only %d (of which %d have no AS date: failed in referendum), Fedlex-only %d",
                 len(cap), len(ours), both, len(cap) - both, int(cap["source"].isna().sum()), len(ours) - both)
        enacted = cap[cap["filter_enacted_legislation"] == 1]
        rows = []
        for y in range(2000, 2009):
            n_cap, n_fx = int((enacted["year"] == y).sum()), int((ours["year"] == y).sum())
            rows.append({"year": y, "cap_enacted_laws": n_cap, "fedlex_acts": n_fx,
                         "pct_diff_fedlex_vs_cap": round(100 * (n_fx - n_cap) / n_cap, 1) if n_cap else None})
        ov = pd.DataFrame(rows)
        ov.to_csv(D / "cap_overlap.csv", index=False)
        log.info("ch CAP (type law, enacted) vs Fedlex per year 2000-2008:\n%s", ov.to_string(index=False))
    except Exception as e:  # noqa: BLE001
        log.warning("ch CAP download/cross-check skipped: %s", e)


def main():
    businesses, bills_by_business, res_by_bill = fetch_parliament()
    fetch_orphans(businesses, bills_by_business, res_by_bill)
    bills_df = build_bills(businesses, bills_by_business, res_by_bill)
    if len(bills_df):
        write_csv(bills_df[BILLS_COLUMNS + ["business_type", "status", "n_bills", "bill_types", "bill_titles", "last_resolution"]],
                  INTER / "bills_ch.csv")
        log.info("ch bills outcome mix: %s", bills_df.groupby(["origin", "outcome"]).size().to_dict())
    else:
        bills_df = pd.DataFrame(columns=BILLS_COLUMNS + ["bill_titles"])

    laws_df = build_laws_fedlex(*origin_lookup(businesses, bills_by_business, res_by_bill))
    if laws_df is None or laws_df.empty:
        log.warning("ch: Fedlex unavailable, writing laws_ch.csv from the parliament side (enacted Bundesgesetz bills)")
        laws_df = build_laws_parliament(bills_df)
    fed_df = laws_df
    laws_df = pd.concat([cap_laws(), laws_df], ignore_index=True).sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_ch.csv")
    log.info("ch laws: %d acts, origin known for %d", len(laws_df), (laws_df.origin != "unknown").sum())
    counts = (laws_df.groupby(["source", "year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="CH", source_url=lambda d: d.source.map({"cap_ch": CAP_URL}).fillna(FEDLEX)))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_ch.csv")
    cap_crosscheck(fed_df)


if __name__ == "__main__":
    main()
