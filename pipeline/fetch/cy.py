"""Cyprus: CyLaw yearly indexes -> laws_cy.csv, counts_cy.csv, 1960-2025.

Source: https://www.cylaw.org/nomoi/{YEAR}_arith_index.html (ISO-8859-7 HTML), one page per year listing
every law as "Ν. N(part)/YEAR - title" with a link to the PDF. Numbering parts: N(I) = general laws -> law,
N(II) = budget laws (state and public-body budgets, supplementary budgets) -> budget_law, N(III) = treaty
ratifications -> ratification. One row per distinct law number per part (the index occasionally repeats an
entry). Titles are Greek.
Before 1992 the index uses a single sequence "Ν. N/YEAR" (no I/II/III parts): those laws are all mapped to
instrument_type law (budgets and ratifications are not separated) and date_note says so. 1960 covers only the
Republic's first months (from 16 Aug 1960). The 1960-65 pages also list laws of the Greek and Turkish Communal
Chambers ("Ν. N/YEARΕΚΣ", "Ν. N/YEARΤΚΣ"); those are not laws of the House of Representatives and are skipped.
Corrigenda entries ("Ν. N/YEAR_ΔΙΟΡΘΩΣΗ") are skipped.

Date: the index shows no date, so date = YEAR-01-01 and the extra column `date_note` says so.
Origin: unknown (parliament.cy returns 403 to scripts; not attempted)."""
from __future__ import annotations

import re
import time

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

D = RAW / "cy"
BASE = "https://www.cylaw.org"
YEARS = range(1960, 2026)
PARTS_FROM = 1992   # first year numbered N(I)/N(II)/N(III)
OLD_NOTE = "pre-1992 single numbering N/YEAR mapped to law (budgets/ratifications not separated); index gives no date; YEAR-01-01 used"
RE_OLD = re.compile(r'<a href="([^"]+)">\s*[ΝN]\.?\s*(\d+)\s*/\s*(\d{4})(ΕΚΣ|ΤΚΣ|_ΔΙΟΡΘΩΣΗ)?\s*-?\s*(.*?)</a>', re.S)
PART_TYPE = {"I": "law", "II": "budget_law", "III": "ratification"}
RE_ENTRY = re.compile(r'<a href="([^"]+)">\s*[ΝN]\.?\s*(\d+)\s*\((I{1,3})\)\s*/\s*(\d{4})\s*-?\s*(.*?)</a>', re.S)
RE_LOOSE = re.compile(r"[ΝN]\.?\s*(\d+)\s*\((I{1,3})\)\s*/\s*(\d{4})\s*-?\s*([^<\n]*)")


def index_html(year: int) -> str:
    dest = D / f"{year}_arith_index.html"
    cached = dest.exists()
    raw = get(f"{BASE}/nomoi/{year}_arith_index.html", dest)
    if not cached:
        time.sleep(0.3)
    return raw.decode("iso-8859-7", errors="replace")


def parse_year_old(html: str, year: int) -> list[dict]:
    """Pre-1992 pages: 'Ν. N/YEAR - title' (part ''); communal-chamber laws and corrigenda skipped."""
    out, skipped = {}, {}
    for href, num, yr, suffix, title in RE_OLD.findall(html):
        if int(yr) != year:
            continue
        if suffix:
            skipped[suffix] = skipped.get(suffix, 0) + 1
            continue
        key = (int(num), "")
        if key in out:
            continue
        title = re.sub(r"<[^>]+>", " ", title)
        out[key] = {"num": int(num), "part": "", "title": re.sub(r"\s+", " ", title).strip(),
                    "url": href if href.startswith("http") else BASE + href}
    if skipped:
        log.info("cy %d: skipped %s", year, skipped)
    return [out[k] for k in sorted(out)]


def parse_year(html: str, year: int) -> list[dict]:
    if year < PARTS_FROM:
        return parse_year_old(html, year)
    out = {}
    for href, num, part, yr, title in RE_ENTRY.findall(html):
        if int(yr) != year:
            continue
        key = (int(num), part)
        if key in out:
            continue
        title = re.sub(r"<[^>]+>", " ", title)
        out[key] = {"num": int(num), "part": part, "title": re.sub(r"\s+", " ", title).strip(),
                    "url": href if href.startswith("http") else BASE + href}
    # entries not wrapped in a link (rare) still count
    for num, part, yr, title in RE_LOOSE.findall(re.sub(r"<a [^>]*>.*?</a>", " ", html, flags=re.S)):
        key = (int(num), part)
        if int(yr) == year and key not in out and part in PART_TYPE:
            out[key] = {"num": int(num), "part": part, "title": re.sub(r"\s+", " ", title).strip(), "url": None}
    return [out[k] for k in sorted(out)]


def main():
    laws = []
    for year in YEARS:
        try:
            entries = parse_year(index_html(year), year)
        except Exception as e:  # noqa: BLE001
            log.warning("cy %d: index failed: %s", year, e)
            continue
        for e in entries:
            itype = PART_TYPE.get(e["part"], "other") if e["part"] else "law"
            laws.append({
                "country": "CY", "year": year, "date": f"{year}-01-01", "instrument_type": itype,
                "origin": "unknown", "title": e["title"], "length_words": None, "cap_topic": None,
                "is_budget": itype == "budget_law", "is_ratification": itype == "ratification",
                "source": "cylaw_index",
                "source_id": f"{e['num']}({e['part']})/{year}" if e["part"] else f"{e['num']}/{year}",
                "source_url": e["url"] or f"{BASE}/nomoi/{year}_arith_index.html",
                "date_note": "index gives no date; YEAR-01-01 used" if e["part"] else OLD_NOTE,
            })
        parts = pd.Series([e["part"] or "N" for e in entries]).value_counts().to_dict() if entries else {}
        log.info("cy %d: %s", year, parts)
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["date_note"])
    write_csv(laws_df, INTER / "laws_cy.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="CY", source="cylaw_index", source_url=f"{BASE}/nomoi/"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_cy.csv")


if __name__ == "__main__":
    main()
