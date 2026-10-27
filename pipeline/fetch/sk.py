"""Slovakia.
- Laws 1993-2023: ParlText SK (Harvard Dataverse doi:10.7910/DVN/6NQXHF, datafile 12077947 -> raw/sk/SK_laws.tab).
  Columns law_ID, law_link, law_text, electoral_cycle, year_published, number_published, date_passed, law_title,
  bill_ID (all 9999 = no link), major_topic (CAP). The file is tab-separated in the archival format and comma-separated
  in the original; the separator is sniffed from the header. ParlText 2024 is partial (12 laws) and is dropped;
  ParlText 1991-92 (Czechoslovak-era SNR acts) are dropped too: the series starts in 1993, the Slovak Republic's first
  year (laws numbered 1/1993 Z. z. onward, some passed by the NR SR in late 1992).
- Origin and 2024-2025: NR SR bill search (https://www.nrsr.sk/web/Default.aspx?sid=zakony/sslp, ASP.NET postback),
  one query per electoral term (CisObdobia 2..9 = 1998-2002 .. 2023-; term 1 = 1994-98 returns nothing) and proposer (ctlPredkladatel 0 = deputies,
  1 = committee, 2 = government) restricted to bills with an approval date. Each row: title, print number (ČPT),
  approval date, proposer names, category. Cached as HTML under raw/sk/nrsr/.
  * The bill search only reaches approvals from Oct 1998 (term 2), so laws passed 1993-Sep 1998 keep origin 'unknown'.
  * ParlText laws are matched to approved bills by approval date (= ParlText date_passed) and normalised title;
    unmatched laws keep origin 'unknown'.
  * 2024-2025 laws are the approved bills of term 9 by APPROVAL year (publication in the Collection usually follows
    within weeks, so the 2023/24 boundary differs slightly from ParlText's publication year). Bills in the categories
    'Zákon vrátený prezidentom' (re-votes after a veto: the original bill already carries an approval date),
    'Medzinárodná zmluva' (treaties: consent by resolution, not a law), reports, information notes and petitions are
    not laws and are dropped.
  * ParlText has no constitutional laws, so approved bills in the category 'Ústavný zákon' are added for 2000-2023
    as well (approval year, 1998- in practice: the search does not reach 1993-98 constitutional laws, a known gap).
- Mapping: 'Ústavný zákon' -> constitutional_law; 'o štátnom rozpočte' -> budget_law; 'Úplné znenie' (consolidated
  text promulgated by the Speaker) -> consolidation; treaty wording at the start of the title -> ratification."""
from __future__ import annotations

import csv
import difflib
import html as H
import io
import re
import time
import unicodedata

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, dataverse_download, get, log, write_csv

D = RAW / "sk"
SEARCH = "https://www.nrsr.sk/web/Default.aspx?sid=zakony/sslp"
PARLTEXT_FILE_ID = 12077947
YEARS = range(1993, 2026)
FIRST_YEAR = 1993
PARLTEXT_LAST = 2023
TERMS = {2: 1998, 3: 2002, 4: 2006, 5: 2010, 6: 2012, 7: 2016, 8: 2020, 9: 2023}
PROPOSERS = {"0": "parliament", "1": "parliament", "2": "government"}   # deputies, NR SR committee, government
PROPOSER_LABEL = {"0": "deputies", "1": "committee", "2": "government"}
P = "_sectionLayoutContainer$ctl01$"
NOT_LAW_CATEGORIES = {"Zákon vrátený prezidentom", "Medzinárodná zmluva", "Správa", "Informácia", "Petícia"}
SLEEP = 1.0
TIME_BUDGET_S = 40 * 60


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def classify(title: str, category: str = "") -> str:
    t = fold(title)
    if t.startswith("uplne znenie"):
        return "consolidation"
    if category == "Ústavný zákon" or t.startswith("ustavny zakon") or re.search(r"(vydanie|navrh) ustavneho zakona", t[:200]):
        return "constitutional_law"
    if category == "Návrh zákona o štátnom rozpočte" or "o statnom rozpocte" in t:
        return "budget_law"
    if re.match(r"^(zmluva|dohoda|dohovor|protokol|memorandum)\b", t):
        return "ratification"
    return "law"


# ----------------------------------------------------------------------------------------------- ParlText
def parltext() -> pd.DataFrame:
    dest = D / "SK_laws.tab"
    raw = dataverse_download(PARLTEXT_FILE_ID, dest, original=False)
    head = raw[:2000].decode("utf-8", "replace").splitlines()[0]
    sep = "\t" if head.count("\t") > head.count(",") else ","
    csv.field_size_limit(10**9)
    df = pd.read_csv(io.BytesIO(raw), sep=sep, usecols=lambda c: c != "law_text")
    if "date_passed" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "date_passed"})
    return df


# ----------------------------------------------------------------------------------------------- NR SR search
def _hidden(h: str) -> dict:
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', h))


def nrsr_search(term: int, proposer: str) -> str:
    dest = D / "nrsr" / f"approved_t{term}_p{proposer}.html"
    if dest.exists():
        return dest.read_text(encoding="utf-8")
    form = get(SEARCH, None, retries=3).decode("utf-8", "replace")
    data = _hidden(form)
    data.update({P + "ctlCisObdobia": str(term), P + "ctlCategory": "-1", P + "ctlPredkladatel": proposer,
                 P + "_mpsCombo": "-1", P + "ctlView": "", P + "ctlNazov": "", P + "ctlCPT": "",
                 P + "ctlPredkladatelName": "", P + "_Ciastka": "", P + "_Cislo": "", P + "DatumOd": "",
                 P + "DatumDo": "", P + "txtDatumSchvaleniaOd": "1. 1. 1990", P + "txtDatumSchvaleniaDo": "31. 12. 2030",
                 P + "Type": "optSearchType", P + "cmdSearch": "Vyhľadať"})
    raw = get(SEARCH, dest, method="POST", data=data, retries=3, timeout=180)
    time.sleep(SLEEP)
    return raw.decode("utf-8", "replace")


def parse_search(h: str, term: int, proposer: str) -> list[dict]:
    j = h.find("Predkladateľ<span")
    out = []
    if j < 0:
        return out
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h[j:], re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 7:
            continue
        cell = [H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))).strip() for t in tds]
        mid = re.search(r"MasterID=(\d+)", tds[0])
        dm = re.match(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", cell[4])
        out.append({"term": term, "proposer_code": proposer, "origin": PROPOSERS[proposer],
                    "proposer_kind": PROPOSER_LABEL[proposer], "title": cell[0], "cpt": cell[1], "state": cell[2],
                    "date_received": cell[3],
                    "date_approved": f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}" if dm else None,
                    "proposers": cell[5], "category": cell[6], "master_id": mid.group(1) if mid else None})
    return out


def nrsr_bills() -> pd.DataFrame:
    rows, t0 = [], time.time()
    for term in TERMS:
        for p in PROPOSERS:
            if time.time() - t0 > TIME_BUDGET_S:
                log.warning("sk nrsr: time budget hit at term %d", term)
                break
            try:
                rows.extend(parse_search(nrsr_search(term, p), term, p))
            except Exception as e:  # noqa: BLE001
                log.warning("sk nrsr term %d proposer %s failed: %s", term, p, e)
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates(["term", "cpt", "master_id"])
    return df


_BILL_PREFIX = re.compile(r"^.*?(?:navrh|vydanie)\s+(?:ustavneho\s+)?zakona,?\s*")
_LAW_PREFIX = re.compile(r"^(?:ustavny\s+)?zakon(?:\s+z\s+\d+\.\s*\w+\s+\d{4})?,?\s*")


def norm_bill(t: str) -> str:
    t = _BILL_PREFIX.sub("", fold(t), count=1)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def norm_law(t: str) -> str:
    t = _LAW_PREFIX.sub("", fold(t), count=1)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def match_origin(laws: pd.DataFrame, bills: pd.DataFrame) -> pd.Series:
    """Origin for each ParlText law: approved bill on the same date with the most similar title (ratio >= 0.6),
    else the best title match within +-3 days (ratio >= 0.8)."""
    if bills.empty:
        return pd.Series("unknown", index=laws.index)
    b = bills[bills.date_approved.notna()].copy()
    b["n"] = b.title.map(norm_bill)
    b["d"] = pd.to_datetime(b.date_approved)
    by_date = {d: g for d, g in b.groupby("date_approved")}
    out = {}
    for i, r in laws.iterrows():
        nt = norm_law(r["law_title"])[:200]
        best, score = None, 0.0
        cands = by_date.get(str(r["date_passed"])[:10])
        if cands is not None:
            for _, c in cands.iterrows():
                s = difflib.SequenceMatcher(None, nt, c["n"][:200]).ratio()
                if s > score:
                    best, score = c, s
        if score < 0.6:
            try:
                d = pd.Timestamp(r["date_passed"])
                near = b[(b.d - d).abs() <= pd.Timedelta(days=3)]
            except Exception:  # noqa: BLE001
                near = b.iloc[0:0]
            best2, score2 = None, 0.0
            for _, c in near.iterrows():
                s = difflib.SequenceMatcher(None, nt, c["n"][:200]).ratio()
                if s > score2:
                    best2, score2 = c, s
            if score2 >= 0.8:
                best, score = best2, score2
            elif score < 0.6:
                best = None
        out[i] = best["origin"] if best is not None else "unknown"
    return pd.Series(out)


# ----------------------------------------------------------------------------------------------- main
def main():
    D.mkdir(parents=True, exist_ok=True)
    rows = []
    # 1. NR SR approved bills (origin + 2024-2025)
    try:
        bills = nrsr_bills()
    except Exception as e:  # noqa: BLE001
        log.warning("sk nrsr failed: %s", e)
        bills = pd.DataFrame()
    if len(bills):
        bills.to_csv(D / "nrsr_approved_bills.csv", index=False)
        lawlike = bills[~bills.category.isin(NOT_LAW_CATEGORIES) & bills.date_approved.notna()]
        log.info("sk nrsr: %d approved items, %d law-like; by approval year: %s", len(bills), len(lawlike),
                 lawlike.date_approved.str[:4].value_counts().sort_index().to_dict())
    else:
        lawlike = pd.DataFrame(columns=["date_approved", "title", "category", "origin", "cpt", "term", "master_id"])

    # 2. ParlText 2000-2023
    try:
        pt = parltext()
        pt = pt[pt.year_published.between(FIRST_YEAR, PARLTEXT_LAST)].copy()
        pt["origin"] = match_origin(pt, bills) if len(bills) else "unknown"
        cons = pt.law_title.map(lambda t: classify(t) == "consolidation")
        pt.loc[cons, "origin"] = "other"          # consolidated texts are published by the Speaker, not a bill
        for _, r in pt.iterrows():
            itype = classify(r["law_title"])
            y = int(r["year_published"])
            rows.append({"country": "SK", "year": y, "date": str(r["date_passed"])[:10] if pd.notna(r["date_passed"]) else f"{y}-01-01",
                         "instrument_type": itype, "origin": r["origin"], "title": r["law_title"], "length_words": None,
                         "cap_topic": int(r["major_topic"]) if pd.notna(r.get("major_topic")) else None,
                         "is_budget": itype == "budget_law", "is_ratification": itype == "ratification",
                         "source": "parltext_sk", "source_id": f"{int(r['number_published'])}/{y} Z. z.",
                         "source_url": str(r["law_link"]).strip()})
        m = pt[~cons]
        log.info("sk parltext: %d laws 1993-2023, origin matched for %.0f%% (%s)", len(pt),
                 100 * (m.origin != "unknown").mean(), m.origin.value_counts().to_dict())
    except Exception as e:  # noqa: BLE001
        log.warning("sk ParlText failed: %s", e)

    # 3. 2024-2025 from NR SR approved bills (approval year)
    # ParlText carries no constitutional laws: add NR SR approved constitutional bills for 2000-2023 too
    if len(lawlike):
        yr = lawlike.date_approved.str[:4]
        late = lawlike[yr.isin(["2024", "2025"]) | ((lawlike.category == "Ústavný zákon") & yr.between(str(FIRST_YEAR), str(PARLTEXT_LAST)))]
    else:
        late = lawlike
    for _, r in late.iterrows():
        itype = classify(r["title"], r["category"])
        rows.append({"country": "SK", "year": int(r["date_approved"][:4]), "date": r["date_approved"],
                     "instrument_type": itype, "origin": r["origin"], "title": r["title"], "length_words": None,
                     "cap_topic": None, "is_budget": itype == "budget_law", "is_ratification": False,
                     "source": "nrsr_approved_bills", "source_id": f"ČPT {r['cpt']} (term {r['term']})",
                     "source_url": f"https://www.nrsr.sk/web/Default.aspx?sid=zakony/zakon&MasterID={r['master_id']}"})

    if not rows:
        log.error("sk: nothing to write")
        return
    laws_df = pd.DataFrame(rows, columns=LAWS_COLUMNS).sort_values(["date", "source_id"]).reset_index(drop=True)
    write_csv(laws_df, INTER / "laws_sk.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin", "source"]).size().reset_index(name="n")
              .assign(country="SK"))
    counts["source_url"] = counts.source.map({"parltext_sk": "https://doi.org/10.7910/DVN/6NQXHF",
                                              "nrsr_approved_bills": SEARCH})
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_sk.csv")
    log.info("sk laws per year: %s", laws_df.groupby("year").size().to_dict())


if __name__ == "__main__":
    main()
