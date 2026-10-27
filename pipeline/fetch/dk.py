"""Denmark: Folketinget ODA (OData v3). Sag typeid 3 = lovforslag (bills) with category (government / private),
status, law number and date -> bills_dk.csv (2004/05 onward) and laws_dk.csv (bills that became law).

1953 - Oct 2004: CAP Denmark laws file (raw/cap/DK_bills__Love_01092019_-_Sheet1.csv, the Danish Policy Agendas
"Love" dataset, folketingsår 1953-2016). Codebook not reachable, so the columns were identified against ODA
(2005-2016): description = bill title; var4 = bill number within the session (L nr.); var17 = date of adoption
(third reading; median 5-15 days before ODA's lovnummerdato); calendar_year = year of var17; year = session year;
var3 = proposer (3 -> government bill in 99% of ODA matches; 2/4/6 mostly private members); var18/var19 = topic
codes. There is no adoption flag or law number: the file is a laws dataset and its per-year totals match ODA laws
within ~2% in 2008-2014; of the rows that match an ODA bill by title in 2005-2016, ~98.5% were enacted (the rest are
a few defeated/lapsed private-member bills). All rows are therefore written as enacted, source cap_dk,
origin unknown, year = year of var17, for adoption dates before the start of the first ODA session (2004-10-05),
so 2004 is CAP (Jan-Sep) + ODA (from the 2004-05 session) without overlap. 1953 is partial (the unicameral
Folketing from the autumn 1953 session only). CAP vs ODA per year 2004-2016 -> raw/dk/cap_overlap.csv."""
from __future__ import annotations

import pandas as pd

import time

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get_json, log, write_csv

D = RAW / "dk"
ODA = "https://oda.ft.dk/api"
ENACTED = {10, 11, 17, 34, 39}
DEFEATED = {3, 16, 35, 37, 38}
WITHDRAWN = {4}
LAPSED = {9, 13}
GOV_CATS = {13, 17}
PARL_CATS = {10, 12, 15}


def fetch_all(entity: str, filt: str | None = None) -> list[dict]:
    out, skip = [], 0
    while True:
        params = {"$top": 100, "$skip": skip, "$orderby": "id"}
        if filt:
            params["$filter"] = filt
        dest = D / f"{entity}_skip{skip:06d}.json"
        live = not dest.exists()
        for attempt in range(4):
            try:
                j = get_json(f"{ODA}/{entity}", dest, params=params)
                break
            except RuntimeError as e:
                if "HTTP 429" in str(e) and attempt < 3:
                    log.warning("dk: 429, sleeping %ds", 30 * 2 ** attempt)
                    time.sleep(30 * 2 ** attempt)
                    continue
                raise
        if live:
            time.sleep(0.3)
        vals = j.get("value", [])
        out.extend(vals)
        if len(vals) < 100:
            break
        skip += 100
    return out


CAP_FILE = RAW / "cap" / "DK_bills__Love_01092019_-_Sheet1.csv"
CAP_URL = "https://www.comparativeagendas.net/datasets_codebooks"


def cap_laws(cutoff: str, oda_df: pd.DataFrame) -> pd.DataFrame:
    """CAP Denmark rows adopted before `cutoff` (start of the first ODA session) as laws_dk rows; logs and writes
    the CAP-vs-ODA per-year overlap 2004-2016."""
    try:
        cap = pd.read_csv(CAP_FILE, encoding_errors="replace", sep=None, engine="python")
    except Exception as e:  # noqa: BLE001
        log.warning("dk CAP file unreadable, no pre-2004 rows: %s", e)
        return pd.DataFrame(columns=LAWS_COLUMNS)
    cap["dt"] = pd.to_datetime(cap.var17, format="%m/%d/%Y", errors="coerce")
    cap = cap[cap.dt.notna()].drop_duplicates(["description", "var17", "var4"])
    ov = pd.DataFrame({"cap": cap.dt.dt.year.value_counts(), "oda": oda_df.year.value_counts()}).loc[2004:2016]
    ov["pct_diff_cap_vs_oda"] = (100 * (ov.cap - ov.oda) / ov.oda).round(1)
    ov.rename_axis("year").to_csv(D / "cap_overlap.csv")
    log.info("dk CAP vs ODA laws per calendar year (ODA 2004 = 2004-05 session only):\n%s", ov.to_string())
    c = cap[cap.dt < pd.Timestamp(cutoff)]
    title = c.description.astype(str).str.strip()
    is_budget = title.str.lower().str.match(r"^(forslag til )?finanslov")
    return pd.DataFrame({
        "country": "DK", "year": c.dt.dt.year.astype(int), "date": c.dt.dt.strftime("%Y-%m-%d"),
        "instrument_type": is_budget.map({True: "budget_law", False: "law"}), "origin": "unknown", "title": title,
        "length_words": None, "cap_topic": c.majortopic, "is_budget": is_budget, "is_ratification": False,
        "source": "cap_dk", "source_id": "cap_dk_" + c["id"].astype(str) + "_L" + c.var4.astype(str),
        "source_url": CAP_URL})[LAWS_COLUMNS]


def main():
    perioder = {p["id"]: p for p in fetch_all("Periode", "type eq 'samling'")}
    sager = fetch_all("Sag", "typeid eq 3")
    log.info("dk: %d bills, %d sessions", len(sager), len(perioder))
    bills, laws = [], []
    for s in sager:
        per = perioder.get(s.get("periodeid"), {})
        start = (per.get("startdato") or "")[:10]
        year_intro = int(start[:4]) if start else None
        st = s.get("statusid")
        outcome = ("enacted" if st in ENACTED or s.get("lovnummerdato") else "defeated" if st in DEFEATED
                   else "withdrawn" if st in WITHDRAWN else "lapsed" if st in LAPSED else "pending")
        cat = s.get("kategoriid")
        origin = "government" if cat in GOV_CATS else "parliament" if cat in PARL_CATS else "unknown"
        is_budget = bool(s.get("statsbudgetsag")) or str(s.get("titel", "")).lower().startswith("forslag til finanslov")
        itype = "budget_law" if is_budget else "law"
        bills.append({
            "country": "DK", "bill_id": s["id"], "title": s.get("titel"), "year_introduced": year_intro,
            "origin": origin, "outcome": outcome, "date_introduced": None,
            "date_final": (s.get("lovnummerdato") or "")[:10] or None, "instrument_type": itype,
            "source": "folketing_oda", "samling": per.get("titel"), "nummer": s.get("nummer"),
        })
        if s.get("lovnummerdato"):
            d = s["lovnummerdato"][:10]
            laws.append({
                "country": "DK", "year": int(d[:4]), "date": d, "instrument_type": itype, "origin": origin,
                "title": s.get("titel"), "length_words": None, "cap_topic": None, "is_budget": is_budget,
                "is_ratification": False, "source": "folketing_oda", "source_id": f"lov {s.get('lovnummer')}/{d[:4]}",
                "source_url": s.get("retsinformationsurl") or f"https://www.ft.dk/samling/{(per.get('kode') or '')}/lovforslag/{str(s.get('nummer','')).replace(' ', '')}",
            })
    bills_df = pd.DataFrame(bills)
    write_csv(bills_df[BILLS_COLUMNS + ["samling", "nummer"]], INTER / "bills_dk.csv")
    oda_df = pd.DataFrame(laws, columns=LAWS_COLUMNS)
    # cutoff = start of the session (samling) in which ODA's earliest law was adopted
    first = oda_df.date.min() if len(oda_df) else "2004-11-24"
    starts = [p["startdato"][:10] for p in perioder.values() if (p.get("startdato") or "9")[:10] <= first]
    cutoff = max(starts) if starts else "2004-10-05"
    log.info("dk: CAP rows before %s, ODA from its first law %s", cutoff, first)
    cap_df = cap_laws(cutoff, oda_df)
    laws_df = pd.concat([cap_df, oda_df], ignore_index=True).sort_values("date")
    write_csv(laws_df, INTER / "laws_dk.csv")
    counts = (laws_df.groupby(["source", "year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="DK", source_url=lambda d: d.source.map({"cap_dk": CAP_URL}).fillna(ODA)))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_dk.csv")


if __name__ == "__main__":
    main()
