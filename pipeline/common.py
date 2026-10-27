"""Shared helpers: paths, HTTP with retries, raw-file manifest, country codes."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import pathlib
import time
from typing import Any

import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
DATA = ROOT / "data"
INTER = DATA / "intermediate"
MANIFEST = RAW / "MANIFEST.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36 PEI-personal-research")

# Project codes (UK rather than GB on purpose), with the aliases external sources use.
# panel_b = Western Europe panel (1980-); every country is in panel_c (all Europe, 1993-/2000-).
def _c(name, iso3, lang, panel_b, democracy_from, repdem=None, parlgov=None):
    return {"name": name, "iso3": iso3, "lang": lang, "panel_b": panel_b, "democracy_from": democracy_from,
            "repdem": repdem or name, "parlgov": parlgov or name}


COUNTRIES = {
    # v0 thirteen
    "ES": _c("Spain", "ESP", "es", True, 1977),
    "UK": _c("United Kingdom", "GBR", "en", True, 1900),
    "FR": _c("France", "FRA", "fr", True, 1958),
    "DE": _c("Germany", "DEU", "de", True, 1949),
    "IT": _c("Italy", "ITA", "it", True, 1946),
    "NL": _c("Netherlands", "NLD", "nl", True, 1945),
    "BE": _c("Belgium", "BEL", "nl", True, 1945),
    "SE": _c("Sweden", "SWE", "sv", True, 1945),
    "DK": _c("Denmark", "DNK", "da", True, 1945),
    "IE": _c("Ireland", "IRL", "en", True, 1922),
    "PT": _c("Portugal", "PRT", "pt", True, 1976),
    "AT": _c("Austria", "AUT", "de", True, 1945),
    "PL": _c("Poland", "POL", "pl", False, 1991),
    # v1 West / North / South
    "FI": _c("Finland", "FIN", "fi", True, 1917),
    "NO": _c("Norway", "NOR", "nb", True, 1945),
    "IS": _c("Iceland", "ISL", "is", True, 1944),
    "LU": _c("Luxembourg", "LUX", "fr", True, 1945),
    "CH": _c("Switzerland", "CHE", "de", True, 1848, repdem=None),
    "GR": _c("Greece", "GRC", "el", True, 1974),
    "CY": _c("Cyprus", "CYP", "el", True, 1960),
    "MT": _c("Malta", "MLT", "en", True, 1964),
    # v1 Central and Eastern Europe
    "CZ": _c("Czechia", "CZE", "cs", False, 1993, parlgov="Czech Republic"),
    "SK": _c("Slovakia", "SVK", "sk", False, 1993),
    "HU": _c("Hungary", "HUN", "hu", False, 1990),
    "SI": _c("Slovenia", "SVN", "sl", False, 1991),
    "HR": _c("Croatia", "HRV", "hr", False, 1991),
    "RO": _c("Romania", "ROU", "ro", False, 1990),
    "BG": _c("Bulgaria", "BGR", "bg", False, 1990),
    "EE": _c("Estonia", "EST", "et", False, 1992),
    "LV": _c("Latvia", "LVA", "lv", False, 1993),
    "LT": _c("Lithuania", "LTU", "lt", False, 1992),
}
# Long-history panel (laws and budgets back to 1950 where sources allow)
PANEL_A = ["UK", "IE", "IT", "DE", "AT", "DK", "FR", "LU", "FI", "IS"]
# Reference-period boundaries for within-country scoring: a country is only compared with itself inside one era.
ERAS = {"IT": [1948, 1993], "DE": [1949, 1990], "FR": [1959], "ES": [1979], "PT": [1976], "PL": [1991],
        "CZ": [1993], "SK": [1993], "HR": [2000], "GR": [1975], "CY": [1960], "MT": [1964], "BG": [1991],
        "RO": [1990], "HU": [1990], "SI": [1992], "EE": [1992], "LV": [1993], "LT": [1993]}
# Fiscal-year start by era ({first fiscal year: "MM-DD"}); default 01-01.
FY_START = {"IT": {1900: "07-01", 1965: "01-01"}, "DE": {1900: "04-01", 1961: "01-01"}, "SE": {1900: "07-01", 1997: "01-01"},
            "DK": {1900: "04-01", 1979: "01-01"}, "UK": {1900: "04-01"}}
# Earliest year with a robust annual law series (filled by the session-2 fetchers; coverage view reports actual).
LAWS_FROM = {"UK": 1950, "IE": 1922, "IT": 1948, "DE": 1949, "AT": 1945, "DK": 1953, "FR": 1959, "LU": 1950, "FI": 1980,
             "IS": 1991, "ES": 1979, "PT": 1976, "NL": 1981, "BE": 1988, "SE": 2003, "NO": 1986, "CH": 1978, "GR": 1975,
             "CY": 1960, "MT": 1990, "PL": 1991, "CZ": 1993, "SK": 1993, "HU": 1990, "SI": 1992, "HR": 1992, "RO": 1996,
             "BG": 2009, "EE": 1992, "LV": 2010, "LT": 1993}


def scoring_from(cc: str) -> int:
    """First year a country-year is scored: its first era start (regime/democracy), else its democratic start."""
    return min(ERAS[cc]) if cc in ERAS else COUNTRIES[cc]["democracy_from"]


def era_of(cc: str, year: int) -> int:
    """Start year of the reference period a (country, year) belongs to."""
    starts = sorted(ERAS.get(cc, [COUNTRIES[cc]["democracy_from"]]))
    return max([e for e in starts if e <= year] or [starts[0]])


def fy_start_for(cc: str, fiscal_year: int) -> str:
    rule = FY_START.get(cc, {1900: "01-01"})
    mmdd = rule[max(k for k in rule if k <= fiscal_year)]
    return f"{fiscal_year}-{mmdd}"


# Countries REPDEM does not cover (stability falls back to ParlGov)
NO_REPDEM = {"CH", "CY", "MT"}
PANEL_B = [k for k, v in COUNTRIES.items() if v["panel_b"]]
PANEL_C = list(COUNTRIES)
ISO3_TO_CC = {v["iso3"]: k for k, v in COUNTRIES.items()}
NAME_TO_CC = {v["name"]: k for k, v in COUNTRIES.items()}

LAWS_COLUMNS = ["country", "year", "date", "instrument_type", "origin", "title", "length_words",
                "cap_topic", "is_budget", "is_ratification", "source", "source_id", "source_url"]

log = logging.getLogger("pei")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def load_params() -> dict:
    with open(ROOT / "params.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en,es;q=0.8,fr;q=0.7,de;q=0.6"})
    return s


_SESSION: requests.Session | None = None


def _s() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = session()
    return _SESSION


def get(url: str, dest: pathlib.Path | None = None, *, params: dict | None = None,
        headers: dict | None = None, retries: int = 4, backoff: float = 2.0, timeout: int = 90,
        method: str = "GET", json_body: Any = None, data: Any = None, force: bool = False,
        ok_statuses: tuple[int, ...] = (200, 206)) -> bytes:
    """Fetch url with retries/backoff. If dest is given and exists (and not force), return cached bytes.
    Every file written to disk is recorded in raw/MANIFEST.json."""
    if dest is not None and dest.exists() and not force:
        return dest.read_bytes()
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = _s().request(method, url, params=params, headers=headers, json=json_body, data=data,
                             timeout=timeout)
            if r.status_code in ok_statuses:
                content = r.content
                if dest is not None:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(content)
                    manifest_add(dest, r.url, content)
                return content
            last_err = RuntimeError(f"HTTP {r.status_code} for {r.url}")
            if r.status_code in (400, 401, 403, 404):
                break  # not transient
        except requests.RequestException as e:  # noqa: PERF203
            last_err = e
        sleep = backoff ** attempt
        log.warning("retry %d/%d for %s after %s (sleep %.0fs)", attempt + 1, retries, url, last_err, sleep)
        time.sleep(sleep)
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def get_json(url: str, dest: pathlib.Path | None = None, **kw) -> Any:
    kw.setdefault("headers", {})
    kw["headers"] = {"Accept": "application/json", **kw["headers"]}
    return json.loads(get(url, dest, **kw).decode("utf-8"))


def manifest_add(dest: pathlib.Path, url: str, content: bytes) -> None:
    """Record a downloaded file. Safe under concurrent fetchers: lock file + atomic replace, and a
    half-written or unreadable manifest is never reset to empty (the entry is retried, then skipped)."""
    import fcntl
    import os
    import tempfile
    RAW.mkdir(parents=True, exist_ok=True)
    rel = str(dest.relative_to(RAW)) if dest.is_relative_to(RAW) else str(dest)
    entry = {"url": url, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    with open(RAW / ".manifest.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            entries = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
        except (json.JSONDecodeError, OSError):
            log.warning("manifest unreadable; skipping entry for %s (rebuild with pipeline.rebuild_manifest)", rel)
            return
        entries[rel] = entry
        fd, tmp = tempfile.mkstemp(dir=RAW, prefix=".manifest.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(entries.items())), f, indent=1, ensure_ascii=False)
        os.replace(tmp, MANIFEST)


def write_csv(df, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("wrote %s (%d rows)", path.relative_to(ROOT), len(df))
    return path


def dataverse_files(doi: str) -> list[dict]:
    """List files of a Harvard Dataverse dataset: [{filename, id, contentType}]"""
    j = get_json(f"https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:{doi}")
    out = []
    for f in j["data"]["latestVersion"]["files"]:
        d = f["dataFile"]
        out.append({"filename": d["filename"], "id": d["id"], "contentType": d.get("contentType", "")})
    return out


def dataverse_download(file_id: int, dest: pathlib.Path, original: bool = True) -> bytes:
    url = f"https://dataverse.harvard.edu/api/access/datafile/{file_id}"
    if original:
        url += "?format=original"
    return get(url, dest)

# Aggregate-count rows (for sources that only give totals, e.g. Bundestag PDFs, SI counts, IPU)
COUNTS_COLUMNS = ["country", "year", "instrument_type", "origin", "n", "source", "source_url"]
# Bill-level rows (for pass rates and durations)
BILLS_COLUMNS = ["country", "bill_id", "title", "year_introduced", "origin", "outcome", "date_introduced",
                 "date_final", "instrument_type", "source"]


def norm_title(t: str) -> str:
    """Lower-case, strip punctuation and generic suffixes so Act/Bill titles can be matched."""
    import re as _re
    t = (t or "").lower()
    t = _re.sub(r"\((no\.?\s*\d+|\w+)\)", " ", t)
    t = _re.sub(r"\b(act|bill)\b(\s+\d{4})?", " ", t)
    t = _re.sub(r"[^a-z0-9 ]+", " ", t)
    return _re.sub(r"\s+", " ", t).strip()


def env(key: str, default: str | None = None) -> str | None:
    """Read KEY=value from the project .env (no dependency); environment variables win."""
    import os
    if os.environ.get(key):
        return os.environ[key]
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"')
    return default
