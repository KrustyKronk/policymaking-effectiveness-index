"""Italy.
- Primary: Senato SPARQL (https://dati.senato.it/sparql, osr:Ddl). Enacted laws at row level, one query per year
  (FILTER on YEAR(osr:dataLegge)), plus bills per legislature 13-19 with osr:statoDdl.
- 1948-1997 (and fallback for any Senato year that stays down): Camera SPARQL (https://dati.camera.it/sparql),
  class ocd:legge, one query per calendar year of dc:date (YYYYMMDD), cached as raw/it/camera/legge_<year>_*.json.
  Fields: dc:identifier (law number), dc:title, dc:type (Ordinaria / Costituzionale), ocd:rif_leg, and the
  initiative of the linked Camera bill(s) (ocd:lavoriPreparatori -> ocd:rif_attoCamera -> ocd:iniziativa:
  Governo / Parlamentare / Regioni / Popolare / CNEL / Mista). ocd:rif_natura is only populated from
  legislature XVI, so natura is read from dc:type plus the title: "Conversione in legge" -> decree_law,
  bilancio / rendiconto / legge finanziaria -> budget_law, ratifica / adesione / (approvazione ed) esecuzione
  di accordi -> ratification, Costituzionale -> constitutional_law, else law. Checked 2026-10-18 against the
  endpoint: 1948 = 116, 1950 = 508, 1972 = 77, 1987 = 108, legislature I = 2,317 laws.
  The 1996-1997 overlap (Camera vs Senato, both fetched; only Camera rows kept for those years) is written to
  raw/it/camera_vs_senato_overlap.csv.
- If both stay down: header-only laws_it.csv (the pipeline has a last-resort path).

The endpoints are flaky (503/502 seen on 2026-10-16). Each endpoint is probed first with exponential backoff
(6 attempts, ~5 minutes of waiting at most); after that, each query retries a few times with a short backoff.
Every successful response is cached under raw/it/ and reused on re-runs."""
from __future__ import annotations

import json
import re
import time

import pandas as pd

from pipeline.common import (BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv)

SENATO = "https://dati.senato.it/sparql"
CAMERA = "https://dati.camera.it/sparql"
YEARS = range(1998, 2026)
CAMERA_YEARS = range(1948, 1998)
OVERLAP_YEARS = (1996, 1997)
LEGISLATURES = range(13, 20)
CURRENT_LEG = 19
D = RAW / "it"
FMT = "application/sparql-results+json"
POLITE = 0.5
PAGE = 5000

PROBE_DELAYS = [5, 10, 20, 40, 80, 145]  # 6 attempts, ~300 s of waiting in total
QUERY_DELAYS = [5, 15, 30]              # per-query retries once the endpoint has answered
MAX_GIVEUPS = 2                         # consecutive failed queries before an endpoint is treated as down
_DEAD: set[str] = set()
_GIVEUPS: dict[str, int] = {}


def _sparql(endpoint: str, query: str, dest, delays: list[int]) -> list[dict] | None:
    """Run a SELECT query, cached at dest. Returns bindings or None after the retries are spent."""
    if dest.exists():
        try:
            return json.loads(dest.read_text(encoding="utf-8"))["results"]["bindings"]
        except (json.JSONDecodeError, KeyError):
            dest.unlink()
    if endpoint in _DEAD:
        return None
    last: Exception | None = None
    for i, wait in enumerate([0] + delays):
        if wait:
            log.warning("it: %s attempt %d/%d failed, sleeping %ds", endpoint, i, len(delays) + 1, wait)
            time.sleep(wait)
        try:
            raw = get(endpoint, dest, params={"query": query, "format": FMT}, headers={"Accept": FMT},
                      retries=1, timeout=180)
            time.sleep(POLITE)
            j = json.loads(raw.decode("utf-8"))
            _GIVEUPS[endpoint] = 0
            return j["results"]["bindings"]
        except Exception as e:  # noqa: BLE001
            if dest.exists():
                dest.unlink()  # never keep an HTML error page in the cache
            last = e
            if "HTTP 403" in str(e):
                break  # blocked: retrying only makes it worse
    log.warning("it: giving up on query to %s: %s", endpoint, str(last)[:160])
    _GIVEUPS[endpoint] = _GIVEUPS.get(endpoint, 0) + 1
    if "HTTP 403" in str(last) or _GIVEUPS[endpoint] >= MAX_GIVEUPS:
        log.warning("it: treating %s as down for the rest of this run (403 or %d consecutive failures)",
                    endpoint, MAX_GIVEUPS)
        _DEAD.add(endpoint)
    return None


def _paged(endpoint: str, query: str, stem: str) -> list[dict] | None:
    """LIMIT/OFFSET pagination (Virtuoso caps result sets at ~10k rows). Query must have ORDER BY."""
    out, offset = [], 0
    while True:
        b = _sparql(endpoint, f"{query}\nLIMIT {PAGE} OFFSET {offset}", D / f"{stem}_o{offset:06d}.json",
                    QUERY_DELAYS)
        if b is None:
            return out or None
        out.extend(b)
        if len(b) < PAGE:
            return out
        offset += PAGE


def _v(b: dict, k: str) -> str | None:
    x = b.get(k)
    return x["value"] if x else None


def probe(endpoint: str) -> bool:
    q = "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1"
    d = D / f"probe_{'senato' if 'senato' in endpoint else 'camera'}.json"
    if d.exists():
        d.unlink()  # liveness check must hit the network
    ok = _sparql(endpoint, q, d, PROBE_DELAYS) is not None
    log.info("it: endpoint %s %s", endpoint, "is up" if ok else "stayed down")
    return ok


# ---------------------------------------------------------------- mapping
def instrument(natura: str | None, title: str) -> str:
    n, t = (natura or "").lower(), (title or "").lower()
    if "conversione" in n or t.startswith("conversione in legge"):
        return "decree_law"
    if "costituzional" in n:
        return "constitutional_law"
    if "bilancio" in n or re.search(r"bilancio di previsione|legge di stabilit|legge finanziaria|"
                                    r"disposizioni per la formazione del bilancio", t):
        return "budget_law"
    if "ratifica" in n or "trattato" in n or re.match(r"^(ratifica|adesione)", t):
        return "ratification"
    return "law"


def origin(tipi: set[str]) -> str:
    t = {x.lower() for x in tipi if x}
    if not t:
        return "unknown"
    if any(x.startswith("governativ") for x in t):
        return "government"
    if any(x.startswith("parlamentar") for x in t):
        return "parliament"
    return "other"  # Popolare / Regionale / CNEL


def _collapse(bindings: list[dict]) -> dict[str, dict]:
    """One dict per ddl URI; tipoIniziativa values unioned (a ddl has one osr:iniziativa node per presenter)."""
    by: dict[str, dict] = {}
    for b in bindings:
        u = _v(b, "ddl")
        r = by.setdefault(u, {"ddl": u, "tipi": set()})
        for k in ("d", "num", "natura", "titolo", "leg", "stato", "pres", "iter", "prog"):
            if r.get(k) is None and _v(b, k) is not None:
                r[k] = _v(b, k)
        if _v(b, "tipo"):
            r["tipi"].add(_v(b, "tipo"))
    return by


# ---------------------------------------------------------------- Senato
LAWS_Q = """PREFIX osr: <http://dati.senato.it/osr/>
SELECT DISTINCT ?ddl ?d ?num ?natura ?tipo ?titolo ?leg WHERE {{
  ?ddl a osr:Ddl ; osr:dataLegge ?d .
  FILTER(YEAR(?d) = {year})
  OPTIONAL {{ ?ddl osr:numeroLegge ?num }}
  OPTIONAL {{ ?ddl osr:natura ?natura }}
  OPTIONAL {{ ?ddl osr:titolo ?titolo }}
  OPTIONAL {{ ?ddl osr:legislatura ?leg }}
  OPTIONAL {{ ?ddl osr:iniziativa ?ini . ?ini osr:tipoIniziativa ?tipo }}
}} ORDER BY ?ddl"""

BILLS_Q = """PREFIX osr: <http://dati.senato.it/osr/>
SELECT DISTINCT ?ddl ?iter ?prog ?pres ?stato ?d ?natura ?tipo ?titolo WHERE {{
  ?ddl a osr:Ddl ; osr:legislatura {leg} ; osr:dataPresentazione ?pres .
  FILTER(YEAR(?pres) = {year})
  OPTIONAL {{ ?ddl osr:idDdl ?iter }}
  OPTIONAL {{ ?ddl osr:progressivoIter ?prog }}
  OPTIONAL {{ ?ddl osr:statoDdl ?stato }}
  OPTIONAL {{ ?ddl osr:dataLegge ?d }}
  OPTIONAL {{ ?ddl osr:natura ?natura }}
  OPTIONAL {{ ?ddl osr:titolo ?titolo }}
  OPTIONAL {{ ?ddl osr:iniziativa ?ini . ?ini osr:tipoIniziativa ?tipo }}
}} LIMIT 10000"""
# Calendar years spanned by each legislature (bills are partitioned by presentation year so that no page needs
# OFFSET >= 10000, which the Senato Virtuoso rejects with HTTP 500).
LEG_YEARS = {13: (1996, 2001), 14: (2001, 2006), 15: (2006, 2008), 16: (2008, 2013), 17: (2013, 2018),
             18: (2018, 2022), 19: (2022, 2026)}


def senato_laws() -> tuple[list[dict], list[int]]:
    laws, missing = [], []
    for y in YEARS:
        b = _paged(SENATO, LAWS_Q.format(year=y), f"senato/laws_{y}")
        if b is None:
            missing.append(y)
            continue
        ddls = _collapse(b)
        # One law can carry several Senate ddl numbers (navette readings, e.g. 123 and 123-B): keep one per
        # (law number, date), merging initiative types.
        by_law: dict[tuple, dict] = {}
        for r in ddls.values():
            key = (r.get("num") or r["ddl"], r["d"][:10])
            if key in by_law:
                by_law[key]["tipi"] |= r["tipi"]
            else:
                by_law[key] = r
        for r in by_law.values():
            title = r.get("titolo") or ""
            it = instrument(r.get("natura"), title)
            laws.append({
                "country": "IT", "year": int(r["d"][:4]), "date": r["d"][:10], "instrument_type": it,
                "origin": origin(r["tipi"]), "title": title, "length_words": None, "cap_topic": None,
                "is_budget": it == "budget_law", "is_ratification": it == "ratification",
                "source": "senato_sparql",
                "source_id": f"L {r.get('num')}/{r['d'][:4]}" if r.get("num") else r["ddl"],
                "source_url": r["ddl"],
            })
        log.info("it: %d laws %d (%d ddl rows)", y, len(by_law), len(ddls))
    return laws, missing


def bill_outcome(stato: str | None, has_law: bool, leg: int) -> str:
    s = (stato or "").lower()
    if has_law or "legge" in s:
        return "enacted"
    if "respint" in s:
        return "defeated"
    if "ritirat" in s or "restit" in s:
        return "withdrawn"
    if leg == CURRENT_LEG and "decadut" not in s and "assorbit" not in s and "t.u." not in s:
        return "pending"
    return "lapsed"  # end of legislature, D-L decaduto, absorbed / merged into another text


def senato_bills() -> list[dict]:
    """One row per bill = osr:idDdl (groups every navette phase, Senate- and Camera-numbered)."""
    bills = []
    for leg in LEGISLATURES:
        y0, y1 = LEG_YEARS[leg]
        b, gaps = [], []
        for y in range(y0, y1 + 1):
            part = _sparql(SENATO, BILLS_Q.format(leg=leg, year=y), D / f"senato/bills_leg{leg}_{y}.json",
                           QUERY_DELAYS)
            if part is None:
                gaps.append(y)
            else:
                if len(part) >= 10000:
                    log.warning("it: legislature %d year %d hit the 10000-row cap; bills truncated", leg, y)
                b.extend(part)
        if gaps:
            log.warning("it: legislature %d: bills for presentation years %s unavailable", leg, gaps)
        iters: dict[str, list[dict]] = {}
        for r in _collapse(b).values():
            iters.setdefault(r.get("iter") or r["ddl"], []).append(r)
        for iid, phases in iters.items():
            phases.sort(key=lambda r: int(r.get("prog") or 0))
            first, last = phases[0], phases[-1]
            law = next((p for p in phases if p.get("d")), None)
            tipi = set().union(*(p["tipi"] for p in phases))
            title = first.get("titolo") or ""
            pres = (first.get("pres") or "")[:10] or None
            bills.append({
                "country": "IT", "bill_id": f"{leg}-{iid}", "title": title,
                "year_introduced": int(pres[:4]) if pres else None, "origin": origin(tipi),
                "outcome": bill_outcome(last.get("stato"), law is not None, leg), "date_introduced": pres,
                "date_final": law["d"][:10] if law else None,
                "instrument_type": instrument(first.get("natura"), title), "source": "senato_sparql",
                "legislature": leg, "stato_ddl": last.get("stato"), "n_phases": len(phases),
            })
        log.info("it: legislature %d: %d bills from %d ddl phases", leg,
                 sum(1 for x in bills if x["legislature"] == leg), sum(len(v) for v in iters.values()))
    return bills


# ---------------------------------------------------------------- Camera (ocd:legge)
CAMERA_Q = """PREFIX ocd: <http://dati.camera.it/ocd/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
SELECT DISTINCT ?l ?d ?num ?tipo ?titolo ?leg ?atto ?ini WHERE {{
  ?l a ocd:legge ; dc:date ?d .
  FILTER(STRSTARTS(STR(?d), "{year}"))
  OPTIONAL {{ ?l dc:identifier ?num }}
  OPTIONAL {{ ?l dc:type ?tipo }}
  OPTIONAL {{ ?l dc:title ?titolo }}
  OPTIONAL {{ ?l ocd:rif_leg ?leg }}
  OPTIONAL {{ ?l ocd:lavoriPreparatori ?lp . ?lp ocd:rif_attoCamera ?atto .
             OPTIONAL {{ ?atto ocd:iniziativa ?ini }} }}
}} ORDER BY ?l ?atto"""
CAMERA_INI = {"governo": "Governativa", "parlamentare": "Parlamentare", "regioni": "Regionale",
              "popolare": "Popolare", "cnel": "CNEL"}
RATIF_IT = re.compile(r"^(ratifica|adesione|(approvazione ed )?esecuzione (del|della|dell'|degli|delle|di) ?.{0,40}?"
                      r"(accord|convenzion|protocoll|trattat|scambi[o ]|patto|intes|emendament|atto final|"
                      r"dichiarazion|statut|regolament|carta))", re.I)


def camera_instrument(tipo: str | None, title: str) -> str:
    t = " ".join((title or "").split()).lower()
    if (tipo or "").lower().startswith("costituzional"):
        return "constitutional_law"
    if t.startswith("conversione in legge") or re.search(r"^conversione.{0,40}decreto[- ]legge", t):
        return "decree_law"
    if re.search(r"bilancio di previsione|^rendiconto generale|legge finanziaria|legge di stabilit|"
                 r"disposizioni per la formazione del bilancio|^approvazione del rendiconto", t):
        return "budget_law"
    if RATIF_IT.search(t):
        return "ratification"
    return "law"


def camera_tipi(inis: set[str]) -> set[str]:
    out = set()
    for i in inis:
        low = i.lower()
        if low.startswith("mista"):
            out |= {CAMERA_INI[k] for k in CAMERA_INI if k in low}
        else:
            out.add(CAMERA_INI.get(low, i))
    return out


def camera_laws(years) -> tuple[list[dict], list[int]]:
    laws, missing = [], []
    for y in years:
        b = _paged(CAMERA, CAMERA_Q.format(year=y), f"camera/legge_{y}")
        if b is None:
            missing.append(y)
            continue
        by: dict[str, dict] = {}
        for x in b:
            u = _v(x, "l")
            r = by.setdefault(u, {"inis": set()})
            for k in ("d", "num", "tipo", "titolo", "leg"):
                if r.get(k) is None and _v(x, k) is not None:
                    r[k] = _v(x, k)
            if _v(x, "ini"):
                r["inis"].add(_v(x, "ini"))
        for u, r in by.items():
            d = r.get("d") or ""
            date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d) else d[:10]
            title = " ".join((r.get("titolo") or "").split())
            it = camera_instrument(r.get("tipo"), title)
            laws.append({
                "country": "IT", "year": y, "date": date, "instrument_type": it,
                "origin": origin(camera_tipi(r["inis"])), "title": title, "length_words": None, "cap_topic": None,
                "is_budget": it == "budget_law", "is_ratification": it == "ratification", "source": "camera_sparql",
                "source_id": f"L {r.get('num')}/{y}" if r.get("num") else u, "source_url": u,
            })
        log.info("it: camera %d: %d laws", y, len(by))
    return laws, missing


def overlap_report(camera_rows: list[dict]) -> None:
    """Camera vs Senato for the overlap years: totals and law numbers present in only one source."""
    out = []
    for y in OVERLAP_YEARS:
        cam = {r["source_id"] for r in camera_rows if r["year"] == y}
        b = _paged(SENATO, LAWS_Q.format(year=y), f"senato/laws_{y}")
        if b is None:
            log.warning("it: Senato %d unavailable; no overlap check", y)
            continue
        sen = {f"L {r.get('num')}/{r['d'][:4]}" for r in _collapse(b).values() if r.get("num")}
        out.append({"year": y, "camera": len(cam), "senato": len(sen), "both": len(cam & sen),
                    "camera_only": len(cam - sen), "senato_only": len(sen - cam),
                    "camera_only_ids": " ".join(sorted(cam - sen)[:50]),
                    "senato_only_ids": " ".join(sorted(sen - cam)[:50])})
        log.info("it: overlap %d: Camera %d, Senato %d, both %d", y, len(cam), len(sen), len(cam & sen))
    if out:
        pd.DataFrame(out).to_csv(D / "camera_vs_senato_overlap.csv", index=False)


# ---------------------------------------------------------------- main
def write_counts(laws_df: pd.DataFrame) -> None:
    if laws_df.empty:
        counts = pd.DataFrame(columns=COUNTS_COLUMNS)
    else:
        counts = (laws_df.groupby(["country", "year", "instrument_type", "origin", "source"]).size()
                  .rename("n").reset_index())
        counts["source_url"] = counts["source"].map({"senato_sparql": SENATO, "camera_sparql": CAMERA})
        counts = counts[COUNTS_COLUMNS]
    write_csv(counts, INTER / "counts_it.csv")


def main():
    (D / "senato").mkdir(parents=True, exist_ok=True)
    (D / "camera").mkdir(parents=True, exist_ok=True)
    laws: list[dict] = []
    missing = list(YEARS)

    senato_up = probe(SENATO)
    if not senato_up:
        _DEAD.add(SENATO)  # cached years are still used below; uncached ones are skipped without retrying
    try:
        laws, missing = senato_laws()
    except Exception as e:  # noqa: BLE001
        log.warning("it: senato laws failed: %s", e)
    if missing:
        log.warning("it: %d years missing from Senato (%s); will try Camera", len(missing), missing)
    cam_years = list(CAMERA_YEARS) + list(missing)
    camera_up = probe(CAMERA)
    if not camera_up:
        _DEAD.add(CAMERA)  # cached years still load
    try:
        cam_rows, cam_missing = camera_laws(cam_years)
        laws.extend(cam_rows)
        if cam_missing:
            log.warning("it: Camera years unavailable this run: %s", cam_missing)
        try:
            overlap_report(cam_rows)
        except Exception as e:  # noqa: BLE001
            log.warning("it: overlap report failed: %s", e)
    except Exception as e:  # noqa: BLE001
        log.warning("it: camera laws failed: %s", e)

    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).sort_values(["date", "source_id"], ignore_index=True)
    write_csv(laws_df, INTER / "laws_it.csv")
    if laws_df.empty:
        log.warning("it: NO LAWS FETCHED - both SPARQL endpoints unavailable; wrote header-only laws_it.csv")
    write_counts(laws_df)

    bills: list[dict] = []
    try:  # cache first; uncached partitions are skipped quickly if the endpoint is marked down
        bills = senato_bills()
    except Exception as e:  # noqa: BLE001
        log.warning("it: senato bills failed: %s", e)
    extra = ["legislature", "stato_ddl", "n_phases"]
    if not bills and (INTER / "bills_it.csv").exists():
        log.warning("it: no bills fetched this run; keeping the existing bills_it.csv")
        return
    write_csv(pd.DataFrame(bills, columns=BILLS_COLUMNS + extra), INTER / "bills_it.csv")
    log.info("it: %d laws (%d with known origin), %d bills", len(laws_df), (laws_df.origin != "unknown").sum(),
             len(bills))


if __name__ == "__main__":
    main()
