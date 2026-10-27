"""Finland: Finlex open data (opendata.finlex.fi, Akoma Ntoso, no key).
- List (query-parameter form only): /akn/fi/act/statute/list?startYear=Y&endYear=Y&langAndVersion=fin@
  &typeStatute=act&limit=10&page=N (limit is capped at 10 by the API; typeStatute=act keeps acts (laki) and
  drops decrees (asetus) and decisions). Cached as raw/fi/lists/acts_YYYY.json.
- Per act: /akn/fi/act/statute/Y/N/fin@ (XML) -> docTitle, FRBR date, typeStatute, categoryStatute and the
  preliminary-work references (HE n/yyyy = government bill, LA n/yyyy = member's bill, KA = citizens'
  initiative; older acts spell these out, 'Hallituksen esitys' / 'Lakialoite') -> origin. Only compact metadata is cached (raw/fi/acts_YYYY.jsonl, appended per act).
Finlex returns HTTP 429 under parallel load, so everything is fetched strictly serially with 429-aware backoff
(Retry-After if sent, else 2, 4, 8 ... s). Per-act requests are capped (count and wall time); acts beyond the
cap keep a placeholder title and origin 'unknown'.
Budget: the Finnish state budget is a parliamentary decision, not a statute, so no budget_law rows.
Backfill (years before 2000): years are fetched newest first under their own wall-time budget (BACKFILL_BUDGET_S);
a backfill year is written only when every act of it has metadata, and only the contiguous run of complete years
down from 1999 is kept, so the series never has a hole or a half-fetched year. The caches make reruns resume."""
from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import time

import pandas as pd
import requests
from lxml import etree

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, log, manifest_add, session, write_csv

D = RAW / "fi"
BASE = "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute"
FIRST_YEAR = 1990          # 1980 was the target, but at ~7-8 min per year (throttled API) 1980-89 overran the
                           # 90-min backfill budget; 1990-1999 took ~75 min
YEARS = range(FIRST_YEAR, 2026)
BACKFILL_FROM = 2000       # years below this are backfill
BACKFILL_BUDGET_S = 90 * 60
PAGE = 10
ACT_REQUEST_CAP = 20000      # fresh per-act XML requests per run
TIME_BUDGET_S = 3.5 * 3600    # stop fresh per-act requests after this much wall time
AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"
FX = "{http://data.finlex.fi/schema/finlex}"
_SESS: requests.Session | None = None
MIN_INTERVAL = 0.7   # s between requests (pacing; the API throttles bursts)
_LAST = [0.0]


def polite_get(url: str, dest=None, *, params: dict | None = None, retries: int = 8, timeout: int = 60,
               record: bool = True) -> bytes:
    """Serial, 429-aware GET: cached at dest if given; on 429/5xx/network error waits Retry-After when the
    server sends it, else 2, 4, 8, ... s. 400/401/403/404 are not retried."""
    if dest is not None and dest.exists():
        return dest.read_bytes()
    global _SESS
    if _SESS is None:
        _SESS = session()
    last = None
    for attempt in range(retries):
        wait = 2.0 ** (attempt + 1)
        gap = MIN_INTERVAL - (time.time() - _LAST[0])
        if gap > 0:
            time.sleep(gap)
        try:
            _LAST[0] = time.time()
            r = _SESS.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                if dest is not None:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(r.content)
                    if record:
                        manifest_add(dest, r.url, r.content)
                return r.content
            last = f"HTTP {r.status_code}"
            if r.status_code in (400, 401, 403, 404):
                break
            ra = r.headers.get("Retry-After")
            if ra:
                try:
                    wait = max(1.0, float(ra))
                except ValueError:
                    try:
                        wait = max(1.0, (email.utils.parsedate_to_datetime(ra) - dt.datetime.now(dt.timezone.utc)).total_seconds())
                    except Exception:  # noqa: BLE001
                        pass
        except requests.RequestException as e:
            last = str(e)
        if attempt < retries - 1:
            log.warning("%s: %s, sleeping %.0fs (attempt %d/%d)", url, last, wait, attempt + 1, retries)
            time.sleep(min(wait, 300))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def _num(uri: str) -> int:
    m = re.search(r"/(\d{4})/(\d+)/fin@", uri)
    return int(m.group(2)) if m else 0


def list_year(year: int) -> list[str]:
    """All act URIs of a year (typeStatute=act), paging by 10, serially; cached as one JSON per year."""
    dest = D / "lists" / f"acts_{year}.json"
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    uris, page = [], 1
    while True:
        raw = polite_get(f"{BASE}/list", None, params={"startYear": year, "endYear": year, "limit": PAGE, "page": page,
                                                      "langAndVersion": "fin@", "typeStatute": "act"})
        j = json.loads(raw.decode("utf-8"))
        if not isinstance(j, list) or not j:
            break
        uris.extend(x["akn_uri"] for x in j if isinstance(x, dict) and x.get("akn_uri"))
        if len(j) < PAGE:
            break
        page += 1
    uris = sorted(set(uris), key=_num)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(uris, ensure_ascii=False)
    dest.write_text(body, encoding="utf-8")
    manifest_add(dest, f"{BASE}/list?startYear={year}&endYear={year}&langAndVersion=fin@&typeStatute=act", body.encode())
    return uris


def parse_act(xml: bytes, uri: str) -> dict:
    root = etree.fromstring(xml)
    meta = {"uri": uri}
    t = root.find(f".//{AKN}preface//{AKN}docTitle")
    meta["title"] = re.sub(r"\s+", " ", "".join(t.itertext())).strip() if t is not None else None
    n = root.find(f".//{AKN}preface//{AKN}docNumber")
    meta["number"] = n.text.strip() if n is not None and n.text else None
    d = root.find(f".//{AKN}FRBRWork/{AKN}FRBRdate")
    meta["date"] = d.get("date") if d is not None else None
    ts = root.find(f".//{FX}typeStatute")
    meta["type"] = (ts.get("refersTo") or "").lstrip("#") if ts is not None else None
    cs = root.find(f".//{FX}categoryStatute")
    meta["category"] = (cs.get("refersTo") or "").lstrip("#") if cs is not None else None
    sb = root.find(f".//{FX}statuteBookOfFinlandReference/{FX}date")
    meta["published"] = sb.get("date") if sb is not None else None
    pw = root.find(f".//{AKN}hcontainer[@name='preliminaryWork']")
    refs = " ".join(pw.itertext()) if pw is not None else ""
    meta["refs"] = re.sub(r"\s+", " ", refs).strip()[:300]
    body = root.find(f".//{AKN}body")
    meta["length_words"] = len(" ".join(body.itertext()).split()) if body is not None else None
    return meta


def acts_for_year(year: int, state: dict) -> list[dict]:
    """Metadata of every act of the year: per-year JSONL cache plus fresh serial fetches (bounded by state)."""
    uris = list_year(year)
    cache = D / f"acts_{year}.jsonl"
    have: dict[str, dict] = {}
    if cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            try:
                m = json.loads(line)
                if "error" not in m:
                    have[m["uri"]] = m
            except json.JSONDecodeError:
                pass
    missing = [u for u in uris if u not in have]
    fetched = failed = 0
    budget = (state["t0"], TIME_BUDGET_S) if year >= BACKFILL_FROM else (state["t0_backfill"], BACKFILL_BUDGET_S)
    if missing:
        with cache.open("a", encoding="utf-8") as f:
            for u in missing:
                if state["left"] <= 0 or time.time() - budget[0] > budget[1]:
                    break
                state["left"] -= 1
                try:
                    m = parse_act(polite_get(u, None), u)
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    log.warning("fi: act %s failed: %s", u, e)
                    continue
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
                f.flush()
                have[u] = m
                fetched += 1
        if fetched:
            manifest_add(cache, f"{BASE}/{year}/<n>/fin@", cache.read_bytes())
    left = sum(1 for u in uris if u not in have)
    if left:
        log.warning("fi %d: %d acts left without metadata (cap/time budget or failures: %d failed)", year, left, failed)
    return [have.get(u) or {"uri": u} for u in uris]


def origin_from_refs(refs: str) -> str:
    # acts before ~1992 spell the references out: "Hallituksen esitys 272/90", "Lakialoite 139/90"
    if re.search(r"\bHE \d+|\bHallituksen esitys \d+", refs):
        return "government"
    if re.search(r"\bLA \d+|\bLakialoite \d+", refs):
        return "parliament"
    if re.search(r"\bKAA? \d+", refs):      # citizens' initiative (kansalaisaloite)
        return "other"
    return "unknown"


def classify(title: str) -> tuple[str, bool]:
    """(instrument_type, is_ratification). No budget_law: the state budget is not a statute in Finland."""
    t = (title or "").lower()
    is_rat = "voimaansaattamisesta" in t
    if re.search(r"^(laki )?suomen perustuslain .*muuttamisesta|perustuslain muuttamisesta", t):
        return "constitutional_law", is_rat
    if is_rat:
        return "ratification", True
    return "law", False


def main():
    state = {"left": ACT_REQUEST_CAP, "t0": time.time(), "t0_backfill": None}
    laws = []
    complete_from = BACKFILL_FROM   # earliest year of the contiguous run of complete backfill years
    for year in sorted(YEARS, reverse=True):
        if year < BACKFILL_FROM and state["t0_backfill"] is None:
            state["t0_backfill"] = time.time()
        if year < BACKFILL_FROM and complete_from != year + 1:
            continue    # a newer backfill year is incomplete: stop here (no holes)
        try:
            acts = acts_for_year(year, state)
        except Exception as e:  # noqa: BLE001
            log.warning("fi %d: failed (%s)", year, e)
            continue
        if year < BACKFILL_FROM:
            if not acts or any("title" not in m for m in acts):
                log.warning("fi %d: incomplete (%d acts, %d without metadata); backfill stops at %d", year, len(acts),
                            sum("title" not in m for m in acts), complete_from)
                continue
            complete_from = year
        n_known = 0
        for m in acts:
            num = _num(m["uri"])
            if m.get("type") and m["type"] != "act":
                continue    # defensive: the list filter already keeps acts only
            # year = Statute Book year (from the URI); FRBR date can be the treaty/signature date for old texts
            date = next((d for d in (m.get("date"), m.get("published"))
                         if re.match(rf"{year}-\d{{2}}-\d{{2}}", d or "")), f"{year}-01-01")
            title = m.get("title") or f"Laki {num}/{year}"
            itype, is_rat = classify(title)
            origin = origin_from_refs(m.get("refs") or "")
            n_known += origin != "unknown"
            laws.append({
                "country": "FI", "year": year, "date": date[:10],
                "instrument_type": itype, "origin": origin, "title": title,
                "length_words": m.get("length_words"), "cap_topic": None, "is_budget": False,
                "is_ratification": is_rat, "source": "finlex_opendata", "source_id": f"{year}/{num}",
                "source_url": f"https://www.finlex.fi/fi/lainsaadanto/{year}/{num}",
            })
        log.info("fi %d: %d acts, origin known %d, %.0fs elapsed, %d requests left", year, len(acts), n_known,
                 time.time() - state["t0"], state["left"])
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS)
    if laws_df.empty:
        log.error("fi: no acts collected, nothing written")
        return
    laws_df = laws_df[laws_df.year.between(min(complete_from, BACKFILL_FROM), 2025)].sort_values(["date", "source_id"])
    log.info("fi: series starts %d (target %d)", int(laws_df.year.min()), FIRST_YEAR)
    write_csv(laws_df, INTER / "laws_fi.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="FI", source="finlex_opendata", source_url=f"{BASE}/list"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_fi.csv")
    log.info("fi: %d acts; origin %s; types %s", len(laws_df), laws_df.origin.value_counts().to_dict(),
             laws_df.instrument_type.value_counts().to_dict())


if __name__ == "__main__":
    main()
