"""Croatia, laws 1992-2025.
- Narodne novine (official gazette) per-issue listings of the 'Službeni dio' (kategorija=1):
  https://narodne-novine.nn.hr/search.aspx?sortiraj=4&kategorija=1&godina=YYYY&broj=NN&rpp=200&qtype=1&pretraga=da
  Each item carries its document type ('zakon', 'uredba', 'odluka', 'pravilnik', ...), title, sequential number
  (= the ELI 'n' in /eli/sluzbeni/{year}/{issue}/{n}) and publication date, so laws are taken from the issue
  tables of contents without opening every ELI page. Only type 'zakon' is kept.
- The host serves an incomplete TLS chain: fetched with verify=False through a local helper (not common.get),
  warnings suppressed for this host only. Raw cache = parsed items per issue (JSON), recorded in the manifest.
- Origin unknown in v1 (sabor.hr not scraped). Dates are publication dates (date_document would need one ELI
  page per law). Enumeration is time-boxed (TIME_BUDGET_S); years not fully covered are logged and listed in
  raw/hr/coverage.json so a rerun resumes from the cache."""
from __future__ import annotations

import datetime as dt
import json
import re
import time

import pandas as pd
import requests
import urllib3

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, UA, log, manifest_add, write_csv

D = RAW / "hr"
HOST = "https://narodne-novine.nn.hr"
SEARCH = f"{HOST}/search.aspx"
YEARS = list(range(2025, 1991, -1))   # 1992-2025, newest first so a time-boxed run covers recent years fully
TIME_BUDGET_S = 110 * 60
SLEEP = 0.2
MAX_ISSUE = 220

_S: requests.Session | None = None


def _sess() -> requests.Session:
    global _S
    if _S is None:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        _S = requests.Session()
        _S.headers.update({"User-Agent": UA, "Accept-Language": "hr,en;q=0.8"})
    return _S


ITEM_RX = re.compile(
    r'<div class="searchListItem">.*?<a href="/clanci/sluzbeni/(\d{4})_(\d+)_(\d+)_(\d+)\.html"[^>]*>(.*?)<span class="score"'
    r'.*?<div class="official-number-and-date">([^<]*)</div>', re.S)
TOTAL_RX = re.compile(r"Ukupno (?:je|su) pronađen\w* <span[^>]*>\s*(\d+)")


def parse_issue(html: str) -> tuple[int | None, list[dict]]:
    m = TOTAL_RX.search(html)
    total = int(m.group(1)) if m else None
    items = []
    for y, cat, issue, n, title, meta in ITEM_RX.findall(html):
        # meta: 'NN 141/2015, (2628),   odluka, 31.12.2015.'
        mm = re.match(r"NN\s+(\d+)/(\d{4}),\s*\((\d+)\),\s*(.*?),\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\.?\s*$", meta.strip())
        if mm:
            doc_type = mm.group(4).strip().lower()
            date = f"{mm.group(7)}-{int(mm.group(6)):02d}-{int(mm.group(5)):02d}"
        else:
            doc_type, date = re.sub(r"^NN [^,]*, \(\d+\),\s*", "", meta).rsplit(",", 1)[0].strip().lower(), None
        items.append({"year": int(y), "issue": int(issue), "n": int(n), "type": doc_type, "date": date,
                      "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip(),
                      "url": f"{HOST}/eli/sluzbeni/{y}/{int(issue)}/{int(n)}"})
    return total, items


def fetch_issue(year: int, issue: int) -> tuple[dict | None, bool]:
    """Return ({'total': int, 'items': [...]}, fetched_live) for one gazette issue (cached as JSON under raw/hr/issues/)."""
    dest = D / "issues" / str(year) / f"{issue:03d}.json"
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8")), False
    params = {"sortiraj": 4, "kategorija": 1, "godina": year, "broj": issue, "rpp": 200, "qtype": 1, "pretraga": "da"}
    last = None
    for attempt in range(3):
        try:
            r = _sess().get(SEARCH, params=params, verify=False, timeout=(15, 45))
            if r.status_code == 200:
                total, items = parse_issue(r.text)
                if total is None:
                    raise RuntimeError("no total on page")
                if total > 200:
                    log.warning("hr %d/%d: issue has %d documents, only 200 listed", year, issue, total)
                rec = {"year": year, "issue": issue, "total": total, "n_parsed": len(items), "items": items,
                       "url": r.url, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
                dest.parent.mkdir(parents=True, exist_ok=True)
                content = json.dumps(rec, ensure_ascii=False).encode("utf-8")
                dest.write_bytes(content)
                manifest_add(dest, r.url, content)
                return rec, True
            last = RuntimeError(f"HTTP {r.status_code}")
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "0") or 0) or 30 * 2 ** attempt
                log.warning("hr %d/%d: 429, sleeping %ds", year, issue, wait)
                time.sleep(wait)
                continue
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2.0 * (attempt + 1))
    log.warning("hr %d/%d failed: %s", year, issue, last)
    return None, True


def harvest(deadline: float) -> tuple[list[dict], dict]:
    """Walk issues 1..N per year until two consecutive empty issues. Returns (items, coverage per year)."""
    items, coverage = [], {}
    for year in YEARS:
        empties, last_issue, complete, failed = 0, 0, False, 0
        for issue in range(1, MAX_ISSUE + 1):
            if time.time() > deadline:
                break
            rec, live = fetch_issue(year, issue)
            if live:
                time.sleep(SLEEP)
            if rec is None:
                failed += 1
                if failed >= 5:
                    break
                continue
            if rec["total"] == 0:
                empties += 1
                if empties >= 2:
                    complete = True
                    break
                continue
            empties = 0
            last_issue = issue
            items.extend(rec["items"])
        if not complete:
            if time.time() > deadline:
                log.warning("hr %d: time budget hit after issue %d (year incomplete)", year, last_issue)
            else:
                log.warning("hr %d: stopped at MAX_ISSUE=%d or failures (%d)", year, MAX_ISSUE, failed)
        coverage[str(year)] = {"complete": complete, "last_issue": last_issue, "failed_issues": failed}
        if time.time() > deadline:
            for y in YEARS[YEARS.index(year) + 1:]:
                coverage[str(y)] = {"complete": False, "last_issue": 0, "failed_issues": 0}
            break
    return items, coverage


def classify(title: str) -> str:
    t = title.lower()
    if t.startswith("ustavni zakon"):
        return "constitutional_law"
    if "proračun" in t:
        return "budget_law"
    if "potvrđivanju" in t:
        return "ratification"
    return "law"


def main():
    t0 = time.time()
    items, coverage = harvest(t0 + TIME_BUDGET_S)
    D.mkdir(parents=True, exist_ok=True)
    (D / "coverage.json").write_text(json.dumps(coverage, indent=1), encoding="utf-8")
    all_df = pd.DataFrame(items)
    if all_df.empty:
        log.error("hr: nothing harvested")
        return
    all_df.to_csv(D / "nn_items.csv", index=False)
    laws = all_df[all_df["type"] == "zakon"].copy()
    rows = []
    for _, r in laws.iterrows():
        itype = classify(r["title"])
        rows.append({"country": "HR", "year": int(r["year"]), "date": r["date"] or f"{int(r['year'])}-01-01",
                     "instrument_type": itype, "origin": "unknown", "title": r["title"], "length_words": None,
                     "cap_topic": None, "is_budget": itype == "budget_law", "is_ratification": itype == "ratification",
                     "source": "narodne_novine", "source_id": f"{int(r['year'])}/{int(r['issue'])}/{int(r['n'])}",
                     "source_url": r["url"]})
    laws_df = pd.DataFrame(rows, columns=LAWS_COLUMNS).sort_values(["date", "source_id"]).reset_index(drop=True)
    write_csv(laws_df, INTER / "laws_hr.csv")
    counts = (laws_df.groupby(["year", "instrument_type"]).size().reset_index(name="n")
              .assign(country="HR", origin="all", source="narodne_novine", source_url=SEARCH))
    # flag incomplete years in the counts too
    counts["source"] = counts["year"].map(lambda y: "narodne_novine" if coverage.get(str(y), {}).get("complete") else "narodne_novine_partial")
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_hr.csv")
    n0320 = int(laws_df["year"].between(2003, 2020).sum())
    log.info("hr: %d laws (%d in 2003-2020 vs ParlLawSpeech HR 2,972); incomplete years: %s; %.0fs",
             len(laws_df), n0320, [y for y, c in coverage.items() if not c["complete"]], time.time() - t0)


if __name__ == "__main__":
    main()
