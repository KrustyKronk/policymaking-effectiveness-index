"""Hungary.
- Laws: ParlText HU (Harvard Dataverse doi:10.7910/DVN/6NQXHF, datafile 12077948) -> every promulgated
  torveny 1990-2024 (laws_hu.csv starts 1990, the first freely elected Országgyűlés) with title, promulgation date, bill_ID and CAP major topic.
- Origin: Comparative Agendas Project Hungary "Laws and Decree Laws" (and bills) CSVs served from
  minio.la.utexas.edu; joined on (year, law number). introducer_type 1 = minister/government,
  4 = parliamentary committee, 5 = MP(s); other codes -> other.
parlament.hu itself sits behind a CAPTCHA and is not used."""
from __future__ import annotations

import csv
import io
import re

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, dataverse_download, get, log, write_csv

D = RAW / "hu"
DATAVERSE_ID = 12077948
CAP_BASE = "https://minio.la.utexas.edu/compagendas/datasetfiles/"
CAP_LAWS = CAP_BASE + "CAP%20-%20Laws%20and%20Decree%20Laws.csv"
CAP_BILLS = CAP_BASE + "cap_-_bills.csv"
YEARS = range(1990, 2026)

# CAP Hungary codebook: introducer_type
CAP_ORIGIN = {1: "government", 4: "parliament", 5: "parliament", 2: "other", 3: "other", 6: "other",
              12: "other", 13: "other", 18: "other"}


def load_parltext() -> pd.DataFrame:
    raw = dataverse_download(DATAVERSE_ID, D / "HU_laws.tab", original=False)
    head = raw[:2000].decode("utf-8", "replace").splitlines()[0]
    sep = "\t" if head.count("\t") >= head.count(",") else ","
    csv.field_size_limit(10 ** 9)
    df = pd.read_csv(io.BytesIO(raw), sep=sep, dtype=str, escapechar="\\", quoting=csv.QUOTE_MINIMAL,
                     engine="c", on_bad_lines="warn")
    df["length_words"] = df["law_text"].fillna("").map(lambda t: len(t.split()))
    df = df.drop(columns=["law_text"])
    df["year_published"] = pd.to_numeric(df["year_published"], errors="coerce").astype("Int64")
    df["number_published"] = pd.to_numeric(df["number_published"], errors="coerce").astype("Int64")
    log.info("hu parltext: %d laws, %s-%s", len(df), df.year_published.min(), df.year_published.max())
    return df


def load_cap_origin() -> dict[tuple[int, int], str]:
    """(year, law number) -> origin from the CAP laws file; empty dict if anything fails."""
    out: dict[tuple[int, int], str] = {}
    try:
        raw = get(CAP_LAWS, D / "cap_laws.csv")
        cap = pd.read_csv(io.BytesIO(raw), low_memory=False, usecols=["year", "law_number", "introducer_type"])
        cap = cap[cap.year >= 1990]
        cap["law_number"] = pd.to_numeric(cap["law_number"], errors="coerce")
        cap = cap.dropna(subset=["law_number"])
        for r in cap.itertuples(index=False):
            if r.law_number == 9999 or r.introducer_type == 9999:
                continue
            out[(int(r.year), int(r.law_number))] = CAP_ORIGIN.get(int(r.introducer_type), "other")
        log.info("hu CAP laws: origin for %d (year, number) pairs", len(out))
    except Exception as e:  # noqa: BLE001
        log.warning("hu: CAP laws origin join unavailable (%s); origin = unknown", e)
    try:  # cached for reference only; the laws file already carries the introducer
        get(CAP_BILLS, D / "cap_bills.csv")
    except Exception as e:  # noqa: BLE001
        log.warning("hu: CAP bills download failed (%s)", e)
    return out


def classify(title: str) -> tuple[str, bool, bool]:
    t = (title or "").lower()
    is_budget = bool(re.search(r"költségvetés", t)) and not re.search(r"zárszámadás|végrehajtás", t)
    is_rat = bool(re.search(r"kihirdetés", t))
    if is_budget:
        return "budget_law", True, is_rat
    if re.search(r"alaptörvény|alkotmány", t) and re.search(r"módosítás", t):
        return "constitutional_law", False, is_rat
    if is_rat:
        return "ratification", False, True
    return "law", False, False


def main():
    df = load_parltext()
    origin_map = load_cap_origin()
    laws = []
    for r in df.itertuples(index=False):
        y = r.year_published
        if pd.isna(y) or int(y) not in YEARS:
            continue
        itype, is_budget, is_rat = classify(r.law_title)
        key = (int(y), int(r.number_published)) if not pd.isna(r.number_published) else None
        date = (r.date_published or "")[:10]
        if not re.match(r"\d{4}-\d{2}-\d{2}", date):
            date = f"{int(y)}-01-01"
        laws.append({
            "country": "HU", "year": int(y), "date": date, "instrument_type": itype,
            "origin": origin_map.get(key, "unknown"), "title": r.law_title, "length_words": r.length_words,
            "cap_topic": r.major_topic, "is_budget": is_budget, "is_ratification": is_rat,
            "source": "parltext_hu", "source_id": r.law_ID,
            "source_url": ("https://" + r.law_link) if isinstance(r.law_link, str) and r.law_link else None,
        })
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_hu.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="HU", source="parltext_hu+cap_hu",
                      source_url="https://dataverse.harvard.edu/api/access/datafile/12077948"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_hu.csv")
    log.info("hu: %d laws 1990-2024, origin known for %d; by type %s", len(laws_df),
             (laws_df.origin != "unknown").sum(), laws_df.instrument_type.value_counts().to_dict())


if __name__ == "__main__":
    main()
