"""Greece: laws (Νόμοι) 1975-2025 from the National Printing Office (Εθνικό Τυπογραφείο) search backend.

hellenicparliament.gr returns 403 to scripts, so the source is the Government Gazette search API behind
search.et.gr (found in its React bundle, "Αναζήτηση Νομοθεσίας"):
  POST https://searchetv99.azurewebsites.net/api/searchlegislation
       {"legislationCatalogues": "1", "legislationNumber": "", "selectYear": ["YYYY"]}
Catalogue 1 = ΝΟΜΟΣ. Each row = one law with its number (search_LawProtocolNumber), FEK A issue
(search_PrimaryLabel "Α 128/2010"), issue date and title (search_Description). Cached raw/gr/laws_YYYY.json.
Year = FEK publication year (the year the law number belongs to). Origin is not in the gazette -> unknown.
Classification (titles are upper case; diacritics stripped before matching; older katharevousa / demotic lead-ins
"ΠΕΡΙ ΚΥΡΩΣΕΩΣ ..." and "ΓΙΑ ΤΗΝ ΚΥΡΩΣΗ ..." are read as "ΚΥΡΩΣΗ ..."):
- budget_law: title starts "ΚΥΡΩΣΗ ΤΟΥ ΚΡΑΤΙΚΟΥ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ" (before the 1990s: "ΚΥΡΩΣΗ ΤΟΥ ΓΕΝΙΚΟΥ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ
  ΤΟΥ ΚΡΑΤΟΥΣ" (the annual budget law; fiscal-management laws that
  merely mention the state budget, closing accounts and PNP ratifications are not budgets).
- ratification: title starts with "ΚΥΡΩΣΗ" and names a treaty instrument (ΣΥΜΦΩΝΙ/ΣΥΜΒΑΣ/ΠΡΩΤΟΚΟΛΛ/ΜΝΗΜΟΝΙ/ΣΥΝΘΗΚ/
  ΚΑΤΑΣΤΑΤΙΚ/ΤΡΟΠΟΠΟΙΗΣ), excluding ratifications of Acts of Legislative Content (ΠΡΑΞΗΣ ΝΟΜΟΘΕΤΙΚΟΥ
  ΠΕΡΙΕΧΟΜΕΝΟΥ). Caveat: "ΚΥΡΩΣΗ ΣΥΜΒΑΣΗΣ" also covers state contracts with companies (e.g. concession
  contracts), which are classed as ratification here.
Completeness check: laws are numbered continuously since 1975 (from ν. 1/1975), so for each year the
expected count is last - first + 1 (consecutive with the previous year's last number; 1975 from 1). Missing numbers are logged and written to
raw/gr/numbering_check.csv; counts_gr.csv carries the row counts (origin 'all').
"""
from __future__ import annotations

import json
import time
import unicodedata

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

API = "https://searchetv99.azurewebsites.net/api/searchlegislation"
D = RAW / "gr"
YEARS = range(1975, 2026)
NUMBERING_FROM = 1975   # ν. 1/1975 starts the continuous sequence
TREATY = ("ΣΥΜΦΩΝΙ", "ΣΥΜΒΑΣ", "ΠΡΩΤΟΚΟΛΛ", "ΜΝΗΜΟΝΙ", "ΣΥΝΘΗΚ", "ΚΑΤΑΣΤΑΤΙΚ", "ΤΡΟΠΟΠΟΙΗΣ")


def strip(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def mdy(s: str) -> str | None:
    try:
        m, d, y = s.split(" ")[0].split("/")
        return f"{y}-{int(m):02d}-{int(d):02d}"
    except Exception:  # noqa: BLE001
        return None


def classify(title: str) -> tuple[str, bool, bool]:
    t = strip(title)
    for lead in ("ΠΕΡΙ ΚΥΡΩΣΕΩΣ", "ΓΙΑ ΤΗΝ ΚΥΡΩΣΗ"):
        if t.startswith(lead):
            t = "ΚΥΡΩΣΗ" + t[len(lead):]
    if t.startswith(("ΚΥΡΩΣΗ ΤΟΥ ΚΡΑΤΙΚΟΥ ΠΡΟΥΠΟΛΟΓΙΣΜΟΥ", "ΚΥΡΩΣΗ ΤΟΥ ΓΕΝΙΚΟΥ ΠΡΟΥΠΟΛΟΓΙΣΜΟΥ ΤΟΥ ΚΡΑΤΟΥΣ")):
        return "budget_law", True, False
    if t.startswith("ΚΥΡΩΣΗ") and any(k in t for k in TREATY) and "ΝΟΜΟΘΕΤΙΚΟΥ ΠΕΡΙΕΧΟΜΕΝΟΥ" not in t:
        return "ratification", False, True
    return "law", False, False


def main():
    D.mkdir(parents=True, exist_ok=True)
    rows, checks, prev_last = [], [], None
    for y in YEARS:
        dest = D / f"laws_{y}.json"
        cached = dest.exists()
        body = {"legislationCatalogues": "1", "legislationNumber": "", "selectYear": [str(y)]}
        try:
            raw = get(API, dest, method="POST", json_body=body, headers={"Content-Type": "application/json"}, timeout=180)
        except Exception as e:  # noqa: BLE001
            log.warning("gr %d: search failed (%s); year skipped", y, e)
            prev_last = None
            continue
        finally:
            if not cached:
                time.sleep(1.5)
        j = json.loads(raw.decode("utf-8"))
        data = json.loads(j["data"]) if isinstance(j.get("data"), str) and j["data"] else []
        seen = {}
        for x in data:
            num = (x.get("search_LawProtocolNumber") or "").strip()
            if not num.isdigit() or num in seen:
                continue
            seen[num] = x
            title = " ".join((x.get("search_Description") or "").split())
            itype, is_b, is_r = classify(title)
            rows.append({
                "country": "GR", "year": y, "date": mdy(x.get("search_IssueDate") or ""), "instrument_type": itype,
                "origin": "unknown", "title": title, "length_words": None, "cap_topic": None, "is_budget": is_b,
                "is_ratification": is_r, "source": "et_gr_searchlegislation", "source_id": f"ν. {num}/{y}",
                "source_url": f"https://search.et.gr/el/fek/?fek_id={x.get('search_ID')}",
            })
        nums = sorted(int(n) for n in seen)
        if nums:
            first = prev_last + 1 if prev_last else (1 if y == NUMBERING_FROM else nums[0])
            expected = set(range(first, nums[-1] + 1))
            missing = sorted(expected - set(nums))
            checks.append({"year": y, "first_listed": nums[0], "last_listed": nums[-1], "n_listed": len(nums),
                           "n_expected_from_numbering": len(expected), "missing": " ".join(map(str, missing))})
            if missing:
                log.warning("gr %d: %d law numbers missing from the listing: %s", y, len(missing), missing[:20])
            prev_last = nums[-1]
        else:
            log.warning("gr %d: no laws returned", y)
    df = pd.DataFrame(rows, columns=LAWS_COLUMNS).sort_values(["year", "source_id"])
    write_csv(df, INTER / "laws_gr.csv")
    pd.DataFrame(checks).to_csv(D / "numbering_check.csv", index=False)
    counts = (df.groupby(["year", "instrument_type"]).size().reset_index(name="n")
              .assign(country="GR", origin="all", source="et_gr_searchlegislation", source_url=API))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_gr.csv")
    log.info("gr laws per year: %s", df.groupby("year").size().to_dict())
    log.info("gr types: %s", df.instrument_type.value_counts().to_dict())


if __name__ == "__main__":
    main()
