"""Malta: legislation.mt ELI pages -> laws_mt.csv, counts_mt.csv, 1990-2025.

Source: https://legislation.mt/eli/act/{YEAR}/{N}/eng (redirects to .../portalpdf), a page carrying schema.org
JSON-LD (legislationIdentifier, dates, name = "XL of 2024 – Appropriation (2025) Act, 2024 <BR>... Gazette
... – 24.12.2024"). The year listing is JavaScript-rendered, so N = 1, 2, ... is enumerated until two
consecutive misses (a missing act returns an HTTP 200 page without JSON-LD). Hits are cached in raw/mt/.

Date: datePublished when it falls in the act's year, else the gazette date in the name, else legislationDate
if in the year, else YEAR-01-01 (noted in `date_note`). legislationDate alone is unreliable on older acts
(it carries the portal upload date, e.g. 2010 for acts of 2000).
Instrument types: "Appropriation" -> budget_law; "Ratification" -> ratification; "Constitution of Malta"
amendments -> constitutional_law; "(Amendment)" stays law.
Origin: government for every act. Nearly all Maltese bills are government bills and parlament.mt blocks
scripts, so private members' acts (very rare) are not separated out."""
from __future__ import annotations

import json
import re
import time

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, manifest_add, write_csv

D = RAW / "mt"
BASE = "https://legislation.mt"
YEARS = range(1990, 2026)
MAX_N = 120
RE_JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
RE_GAZ_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
ERROR = {"_error": True}  # transport failure (DNS, reset, 5xx): not evidence that the act is missing
MAX_ERRORS = 4            # consecutive transport failures before a year is abandoned (logged as a gap)


def act_page(year: int, n: int) -> dict | None:
    """JSON-LD of act N of YEAR; None when the portal has no such act (404, or a 200 page without JSON-LD);
    ERROR on a transport failure."""
    dest = D / f"act_{year}_{n:03d}.html"
    url = f"{BASE}/eli/act/{year}/{n}/eng"
    if dest.exists():
        raw = dest.read_bytes()
    else:
        try:
            raw = get(url, retries=3)
        except Exception as e:  # noqa: BLE001
            if "HTTP 404" in str(e) or "HTTP 410" in str(e):
                return None
            log.warning("mt %d/%d: %s", year, n, e)
            time.sleep(5)
            return ERROR
        finally:
            time.sleep(0.3)
    m = RE_JSONLD.search(raw.decode("utf-8", errors="replace"))
    if not m:
        return None
    try:
        j = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not j.get("legislationIdentifier"):
        return None
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        manifest_add(dest, url, raw)
    return j


def clean_name(name: str) -> tuple[str, str]:
    """-> (roman number, title) from 'XL of 2024 – Appropriation (2025) Act, 2024 <BR>...'"""
    head = re.split(r"<br\s*/?>|<p[^>]*>|<i>", name, flags=re.I)[0]
    head = re.sub(r"<[^>]+>", " ", head)
    head = re.sub(r"\s+", " ", head).strip()
    m = re.match(r"^([IVXLCDM]+)\s+of\s+\d{4}\s*[–\-—]\s*(.*)$", head)
    return (m.group(1), m.group(2).strip()) if m else ("", head)


def pick_date(j: dict, year: int) -> tuple[str, str | None]:
    for key in ("datePublished", "legislationDateVersion", "dateCreated"):
        v = j.get(key)
        if isinstance(v, str) and v[:4] == str(year):
            return v[:10], None
    m = RE_GAZ_DATE.search(j.get("name") or "")
    if m and m.group(3) == str(year):
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}", None
    v = j.get("legislationDate")
    if isinstance(v, str) and v[:4] == str(year):
        return v[:10], None
    return f"{year}-01-01", "no date in the year on the page; YEAR-01-01 used"


def main():
    laws, gaps = [], []
    for year in YEARS:
        misses, errors, n, found = 0, 0, 1, 0
        while misses < 2 and n <= MAX_N:
            j = act_page(year, n)
            if j is ERROR:
                errors += 1
                if errors >= MAX_ERRORS:
                    gaps.append(f"{year} from N={n}")
                    log.warning("mt %d: abandoned at N=%d after %d transport errors (year incomplete)", year, n, errors)
                    break
                continue  # retry the same N
            errors = 0
            if j is None:
                misses += 1
                n += 1
                continue
            misses = 0
            roman, title = clean_name(j.get("name") or j.get("alternateName") or "")
            tl = title.lower()
            if "appropriation" in tl:
                itype = "budget_law"
            elif "ratification" in tl:
                itype = "ratification"
            elif tl.startswith("constitution of malta"):
                itype = "constitutional_law"
            else:
                itype = "law"
            date, note = pick_date(j, year)
            ident = j.get("legislationIdentifier") or f"eli/act/{year}/{n}"
            laws.append({
                "country": "MT", "year": year, "date": date, "instrument_type": itype, "origin": "government",
                "title": title, "length_words": None, "cap_topic": None, "is_budget": itype == "budget_law",
                "is_ratification": itype == "ratification", "source": "legislation_mt", "source_id": ident,
                "source_url": f"{BASE}/{ident}/eng", "act_number": f"{roman} of {year}" if roman else None,
                "date_note": note,
            })
            found += 1
            n += 1
        log.info("mt %d: %d acts", year, found)
    if gaps:
        log.warning("mt: incomplete years (transport errors): %s", gaps)
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["act_number", "date_note"])
    write_csv(laws_df, INTER / "laws_mt.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="MT", source="legislation_mt", source_url=f"{BASE}/eli/act/"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_mt.csv")


if __name__ == "__main__":
    main()
