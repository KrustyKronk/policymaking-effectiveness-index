"""Austria.
- Parliament "Filter" JSON API (POST https://www.parlament.gv.at/Filter/api/filter/data/101?js=eval&showAll=true):
  * VHG=BNR per GP (Beschlüsse des Nationalrates, from GP XXII / 2002) -> one law row each (Art == "BNR";
    "BS" = Sonstiger Beschluss is dropped). Date = Nationalrat decision date (list column "Datum").
  * Each BNR's detail page (`<HIS_URL>?json=TRUE`) has `reference` -> the underlying bill: /I/<n> (an RV,
    RVS = treaty, BUA = Ausschussantrag, VOLKBG, GABR...) or /A/<n> (Initiativantrag). That gives the origin.
  * ITYP=I per GP (to classify /I/ numbers) and ITYP=A per GP (members' bills; Art "A" only, A(E) resolutions
    dropped) -> bills_at.csv, outcome from the BNR references and the list status code.
- Fallback / cross-check: "Parlament in Zahlen" yearly pages (only 2024 and 2025 exist) -> Gesetzesbeschlüsse totals.

Back-extension (2026-10-18):
- GP XX-XXI (1996-2002): the filter API returns no BNR list for these GPs (VHG=BNR retried 2026-10-18: count 0).
  Enactments are derived from the bills instead: every RV / RVS / BUA / VOLKBG (ITYP=I) and Initiativantrag
  (ITYP=A, Art "A") with list status 5 is opened (`?json=TRUE`, cached under raw/at/detail/), and counted as a
  law when its NR plenary phase has a "Gesetzesvorschlag ... angenommen" stage (third reading, or the single
  reading of a treaty) and the item carries a BGBl link (status.bgbllinks); items merged into another bill
  (miterledigt) have neither and are dropped. date = NR decision date (as for BNR rows), origin from the Art.
  Same source label (parlament_gv_at_filter); source_id = "<GP> <Nummer>" of the bill.
- 1945-1995 totals: RIS OGD API v2.6 (https://data.bka.gv.at/ris/api/v2.6/Bundesrecht, Applikation=BgblPdf,
  the scanned BGBl 1945-2003, 32,910 documents). Parameters (from the API's Examples/bgblpdf.html):
  Kundgemacht.Von / Kundgemacht.Bis = calendar year, Typ.SucheInGesetzen=true (documents whose Typ is
  "Bundesgesetz" or "Bundesverfassungsgesetz"), DokumenteProSeite=OneHundred, Seitennummer=n. Every page is
  cached as raw/at/ris/bgbl_<year>_p<n>.json. counts_at.csv gets, per year 1945-1995, instrument_type law
  (Bundesgesetz) and constitutional_law (Bundesverfassungsgesetz), origin all, source = ris_bgbl. Treaties
  (Staatsverträge) are published as Kundmachung/Sonstiges, so they are not in these counts, unlike the RVS rows
  in laws_at.csv. 1996-2003 are fetched too, only for raw/at/ris_vs_parlament.csv (BGBl laws by
  Kundmachungsdatum vs parliament rows by NR decision date, excluding ratifications).
  1945 includes the Staatsgesetzblatt-era documents only insofar as RIS files them under BgblPdf."""
from __future__ import annotations

import datetime as dt
import json
import re
import time

import pandas as pd

from pipeline.common import (BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, get_json, log,
                             write_csv)

BASE = "https://www.parlament.gv.at"
FILTER = f"{BASE}/Filter/api/filter/data/101?js=eval&showAll=true"
PIZ = f"{BASE}/recherchieren/statistiken/parlament-in-zahlen/{{year}}"
GPS_LAWS = ["XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII"]   # BNR lists exist from XXII
GPS_BILLS = ["XX", "XXI"] + GPS_LAWS
CURRENT_GP = "XXVIII"
YEARS = range(1996, 2026)
GPS_DERIVED = ["XX", "XXI"]
RIS = "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"
RIS_YEARS = range(1945, 1996)
RIS_CHECK_YEARS = range(1996, 2004)
BILL_YEARS = range(1996, 2026)
D = RAW / "at"
DETAIL_SLEEP = 0.1

GOV_ARTS = {"RV", "RVS", "RVESM", "RVEU"}
PARL_ARTS = {"BUA", "A"}
OTHER_ARTS = {"VOLKBG", "GABR", "GABR13", "EBR"}


def _iso(d: str | None) -> str | None:
    try:
        return dt.datetime.strptime(d, "%d.%m.%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def filter_list(body: dict, name: str) -> list[dict]:
    """POST the filter API; return rows as dicts keyed by header label. Cached per query."""
    j = json.loads(get(FILTER, D / "filter" / f"{name}.json", method="POST", json_body=body,
                       headers={"Accept": "application/json"}, timeout=180).decode("utf-8"))
    labels = [h.get("label") for h in j["header"]]
    rows = [dict(zip(labels, r)) for r in j["rows"]]
    if j.get("count") is not None and j["count"] != len(rows):
        log.warning("at: %s: count %s but %d rows", name, j["count"], len(rows))
    time.sleep(0.5)
    return rows


_ART: dict[str, dict[str, str]] = {}


def i_arts(gp: str) -> dict[str, str]:
    """INR -> Art for the ITYP=I list of a GP (RV, RVS, BUA, AUB, VOLKBG, ...)."""
    if gp not in _ART:
        try:
            rows = filter_list({"NRBR": ["NR"], "GP_CODE": [gp], "ITYP": ["I"]}, f"I_{gp}")
            _ART[gp] = {str(r["INR"]): r["Art"] for r in rows}
        except Exception as e:  # noqa: BLE001
            log.warning("at: ITYP=I list for GP %s failed: %s", gp, e)
            _ART[gp] = {}
    return _ART[gp]


def ref_kind(url: str) -> tuple[str, str | None]:
    """'/gegenstand/XXVII/I/1478' -> ('RV', path)."""
    m = re.match(r"^/gegenstand/([A-Z]+)/([A-Z]+)/(\d+)", url or "")
    if not m:
        return "", None
    gp, ityp, inr = m.groups()
    if ityp == "I":
        return i_arts(gp).get(inr, "I?"), m.group(0)
    return ityp, m.group(0)


def origin_of(kind: str) -> str:
    if kind in GOV_ARTS:
        return "government"
    if kind in PARL_ARTS:
        return "parliament"
    if kind in OTHER_ARTS or kind == "III":
        return "other"
    return "unknown"


def instrument(title: str, kind: str) -> str:
    t = title or ""
    if re.search(r"Bundesfinanzgesetz|Bundesfinanzrahmengesetz", t):
        return "budget_law"
    if kind == "RVS" or re.search(r"Staatsvertrag|Abkommen|Übereinkommen|Protokoll|Vertrag zwischen", t):
        return "ratification"
    if re.search(r"Bundesverfassungsgesetz|\(BVG\)|Bundes-Verfassungsgesetz", t):
        return "constitutional_law"
    return "law"


def bnr_rows() -> list[dict]:
    out = []
    for gp in GPS_LAWS:
        try:
            rows = filter_list({"NRBR": ["NR"], "GP_CODE": [gp], "VHG": ["BNR"]}, f"BNR_{gp}")
        except Exception as e:  # noqa: BLE001
            log.warning("at: BNR list for GP %s failed: %s", gp, e)
            continue
        kept = [r for r in rows if r.get("Art") == "BNR"]
        log.info("at: GP %s: %d BNR (%d other Beschlüsse dropped)", gp, len(kept), len(rows) - len(kept))
        out.extend(kept)
    return out


def bnr_detail(r: dict) -> dict | None:
    path = r["HIS_URL"]
    dest = D / "detail" / (path.strip("/").replace("/", "_") + ".json")
    cached = dest.exists()
    try:
        j = get_json(f"{BASE}{path}?json=TRUE", dest, retries=3, timeout=60)
    except Exception as e:  # noqa: BLE001
        log.warning("at: detail %s failed: %s", path, e)
        return None
    if not cached:
        time.sleep(DETAIL_SLEEP)
    return j.get("content") or {}


ENACT_RX = re.compile(r"Gesetzesvorschlag[^<]*?(in dritter Lesung )?angenommen|Nationalrates:\s*Genehmigung(?!\s*abgelehnt)",
                      re.I)


def nr_decision(c: dict) -> tuple[str | None, bool]:
    """(NR decision date ISO, has 'Gesetzesvorschlag ... angenommen' stage) from a detail page's phases."""
    third, any_ = None, None
    for ph in c.get("phase") or []:
        if ph.get("id") != 4:
            continue
        for st in ph.get("stages") or []:
            txt = re.sub(r"<[^>]+>", " ", st.get("text") or "")
            if ENACT_RX.search(txt):
                d = _iso(st.get("date"))
                if "dritter Lesung" in txt and third is None:
                    third = d
                if any_ is None:
                    any_ = d
    d = third or any_
    return d, d is not None


def derived_rows(gp: str) -> list[dict]:
    """Laws for a GP without a BNR list: enacted bills found via their detail pages."""
    cand = []
    try:
        cand += [r for r in filter_list({"NRBR": ["NR"], "GP_CODE": [gp], "ITYP": ["I"]}, f"I_{gp}")
                 if r.get("Art") in ("RV", "RVS", "BUA", "VOLKBG") and str(r.get("Status")) == "5"]
    except Exception as e:  # noqa: BLE001
        log.warning("at: I list GP %s failed: %s", gp, e)
    try:
        cand += [r for r in filter_list({"NRBR": ["NR"], "GP_CODE": [gp], "ITYP": ["A"]}, f"A_{gp}")
                 if r.get("Art") == "A" and str(r.get("Status")) == "5"]
    except Exception as e:  # noqa: BLE001
        log.warning("at: A list GP %s failed: %s", gp, e)
    out, n_fail, n_nolaw = [], 0, 0
    for r in cand:
        c = bnr_detail(r)
        if c is None:
            n_fail += 1
            continue
        date, adopted = nr_decision(c)
        bgbl = [b.get("title") for b in (c.get("status") or {}).get("bgbllinks") or []
                if "Bundesgesetzblatt" in (b.get("title") or "")]
        if not (adopted and bgbl and date):
            n_nolaw += 1
            continue
        kind = r["Art"]
        title = r.get("Betreff") or c.get("title") or ""
        it = instrument(title + " " + (c.get("description") or ""), kind)
        out.append({
            "country": "AT", "year": int(date[:4]), "date": date, "instrument_type": it,
            "origin": origin_of(kind), "title": title, "length_words": None, "cap_topic": None,
            "is_budget": it == "budget_law", "is_ratification": it == "ratification",
            "source": "parlament_gv_at_filter", "source_id": f"{gp} {r.get('Nummer')}",
            "source_url": f"{BASE}{r['HIS_URL']}", "_ref": r["HIS_URL"], "_ref_kind": kind, "_bgbl": bgbl[0],
        })
    log.info("at: GP %s (derived): %d candidates, %d laws, %d not enacted/merged, %d detail failures",
             gp, len(cand), len(out), n_nolaw, n_fail)
    return out


def ris_year(y: int) -> dict[str, int] | None:
    """{Typ: n} for BGBl laws published in calendar year y (RIS BgblPdf). None if RIS failed."""
    typ: dict[str, int] = {}
    page, hits = 1, None
    while True:
        params = {"Applikation": "BgblPdf", "Kundgemacht.Von": f"{y}-01-01", "Kundgemacht.Bis": f"{y}-12-31",
                  "Typ.SucheInGesetzen": "true", "DokumenteProSeite": "OneHundred", "Seitennummer": page}
        try:
            j = get_json(RIS, D / "ris" / f"bgbl_{y}_p{page:02d}.json", params=params, timeout=90)
        except Exception as e:  # noqa: BLE001
            log.warning("at: RIS %d page %d failed: %s", y, page, e)
            return None
        res = (j.get("OgdSearchResult") or {}).get("OgdDocumentResults") or {}
        hits = int((res.get("Hits") or {}).get("#text") or 0)
        docs = res.get("OgdDocumentReference") or []
        docs = docs if isinstance(docs, list) else [docs]
        for d in docs:
            b = d["Data"]["Metadaten"]["Bundesrecht"]
            meta = b.get("BgblPdf") or {}
            if str(meta.get("Kundmachungsdatum", ""))[:4] != str(y):
                continue
            t = meta.get("Typ") or ("Bundesgesetz" if (b.get("Titel") or "").startswith("Bundesgesetz") else "?")
            typ[t] = typ.get(t, 0) + 1
        if not docs or page * 100 >= hits:
            break
        page += 1
        time.sleep(0.3)
    if sum(typ.values()) != hits:
        log.warning("at: RIS %d: %d hits but %d documents counted", y, hits, sum(typ.values()))
    return typ


def ris_bgbl_counts() -> dict[int, dict[str, int]]:
    out = {}
    for y in list(RIS_YEARS) + list(RIS_CHECK_YEARS):
        t = ris_year(y)
        if t is not None:
            out[y] = t
    log.info("at: RIS BgblPdf laws for %d years", len(out))
    return out


def piz_totals() -> dict[int, int]:
    """'Es wurden 108 Gesetzesbeschlüsse gefasst' from the Parlament-in-Zahlen pages (2024- only)."""
    out = {}
    for y in YEARS:
        if y < 2024:
            continue  # pages for earlier years return 404 (checked 2026-10-16)
        try:
            html = get(PIZ.format(year=y), D / "piz" / f"{y}.html").decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            log.warning("at: Parlament in Zahlen %d failed: %s", y, e)
            continue
        html = html.replace("&uuml;", "ü").replace("&nbsp;", " ")
        m = re.search(r"Es wurden ([\d.]+)\s+Gesetzesbeschlüsse", html)
        if m:
            out[y] = int(m.group(1).replace(".", ""))
    return out


def main():
    for sub in ("filter", "detail", "piz", "ris"):
        (D / sub).mkdir(parents=True, exist_ok=True)

    # ---- 1. laws (BNR + detail references)
    laws, enacted_paths, n_fail = [], {}, 0
    rows = bnr_rows()
    for i, r in enumerate(rows):
        date = _iso(r.get("Datum"))
        if not date or int(date[:4]) not in YEARS:
            continue
        c = bnr_detail(r)
        kind, ref_path = "", None
        if c is None:
            n_fail += 1
        else:
            for ref in c.get("reference") or []:
                k, p = ref_kind(ref.get("url"))
                if p:
                    kind, ref_path = k, p
                    break
        if ref_path:
            enacted_paths[ref_path] = date
        title = r.get("Betreff") or ""
        it = instrument(title, kind)
        laws.append({
            "country": "AT", "year": int(date[:4]), "date": date, "instrument_type": it,
            "origin": origin_of(kind), "title": title, "length_words": None, "cap_topic": None,
            "is_budget": it == "budget_law", "is_ratification": it == "ratification",
            "source": "parlament_gv_at_filter", "source_id": f"{r['GP_CODE']} {r.get('Nummer')}",
            "source_url": f"{BASE}{r['HIS_URL']}", "_ref": ref_path, "_ref_kind": kind,
        })
        if i and i % 500 == 0:
            log.info("at: %d / %d BNR processed", i, len(rows))
    if n_fail:
        log.warning("at: %d BNR detail pages failed; their origin is 'unknown'", n_fail)
    for gp in GPS_DERIVED:
        try:
            for r in derived_rows(gp):
                if r["year"] in YEARS:
                    enacted_paths[r["_ref"]] = r["date"]
                    laws.append({k: v for k, v in r.items() if k != "_bgbl"})
        except Exception as e:  # noqa: BLE001
            log.warning("at: derived laws for GP %s failed: %s", gp, e)
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["_ref", "_ref_kind"])
    if not laws_df.empty:
        laws_df = laws_df.sort_values(["date", "source_id"], ignore_index=True)
        laws_df.drop(columns=["_ref"]).rename(columns={"_ref_kind": "ref_kind"}).to_csv(
            D / "laws_at_with_refkind.csv", index=False)
    write_csv(laws_df[LAWS_COLUMNS], INTER / "laws_at.csv")

    # ---- 2. counts: aggregated from rows + Parlament in Zahlen totals (cross-check / fallback)
    counts = []
    if not laws_df.empty:
        agg = laws_df.groupby(["year", "instrument_type", "origin"]).size().rename("n").reset_index()
        for _, a in agg.iterrows():
            counts.append({"country": "AT", "year": int(a.year), "instrument_type": a.instrument_type,
                           "origin": a.origin, "n": int(a.n), "source": "parlament_gv_at_filter",
                           "source_url": FILTER})
    piz = piz_totals()
    for y, n in sorted(piz.items()):
        counts.append({"country": "AT", "year": y, "instrument_type": "law", "origin": "all", "n": n,
                       "source": "parlament_in_zahlen", "source_url": PIZ.format(year=y)})
        if not laws_df.empty:
            got = int((laws_df.year == y).sum())
            if got != n:
                log.warning("at: %d: Parlament in Zahlen says %d Gesetzesbeschlüsse, filter API rows %d", y, n, got)
    try:
        ris = ris_bgbl_counts()
    except Exception as e:  # noqa: BLE001
        log.warning("at: RIS BGBl counts failed: %s", e)
        ris = {}
    for y, t in sorted(ris.items()):
        if y not in RIS_YEARS:
            continue
        for it, n in (("law", sum(v for k, v in t.items() if k != "Bundesverfassungsgesetz")),
                      ("constitutional_law", t.get("Bundesverfassungsgesetz", 0))):
            counts.append({"country": "AT", "year": y, "instrument_type": it, "origin": "all", "n": n,
                           "source": "ris_bgbl", "source_url": f"{RIS}?Applikation=BgblPdf"})
    chk = []
    for y in RIS_CHECK_YEARS:
        if y in ris and not laws_df.empty:
            sub = laws_df[(laws_df.year == y) & (laws_df.instrument_type != "ratification")]
            n_r = sum(ris[y].values())
            chk.append({"year": y, "ris_bgbl_laws": n_r, "parlament_rows_excl_ratification": len(sub),
                        "pct_diff": round(100 * (len(sub) - n_r) / n_r, 1) if n_r else None})
    if chk:
        pd.DataFrame(chk).to_csv(D / "ris_vs_parlament.csv", index=False)
        log.info("at: wrote raw/at/ris_vs_parlament.csv")
    write_csv(pd.DataFrame(counts, columns=COUNTS_COLUMNS), INTER / "counts_at.csv")

    # ---- 3. bills: RV / RVS (government) and A (members) per GP
    bills = []
    for gp in GPS_BILLS:
        has_bnr = gp in GPS_LAWS
        cand = []
        arts = i_arts(gp)
        if arts:
            try:
                ilist = filter_list({"NRBR": ["NR"], "GP_CODE": [gp], "ITYP": ["I"]}, f"I_{gp}")
                cand += [r for r in ilist if r.get("Art") in ("RV", "RVS")]
            except Exception as e:  # noqa: BLE001
                log.warning("at: RV list GP %s failed: %s", gp, e)
        if has_bnr:  # without BNR references there is no reliable outcome for members' bills (GP XX, XXI)
            try:
                alist = filter_list({"NRBR": ["NR"], "GP_CODE": [gp], "ITYP": ["A"]}, f"A_{gp}")
                cand += [r for r in alist if r.get("Art") == "A"]
            except Exception as e:  # noqa: BLE001
                log.warning("at: A list GP %s failed: %s", gp, e)
        for r in cand:
            path = r["HIS_URL"]
            status = str(r.get("Status") or "")
            date_in = _iso(r.get("Datum"))
            if path in enacted_paths:
                outcome, final = "enacted", enacted_paths[path]
            elif not has_bnr and r["Art"] in ("RV", "RVS") and status == "5":
                outcome, final = "enacted", None  # GP XX/XXI: status 5 = erledigt, nearly always enacted
            elif status == "4" or (status == "5" and has_bnr):
                outcome, final = "defeated", None  # rejected, or disposed of without a Gesetzesbeschluss
            elif gp == CURRENT_GP:
                outcome, final = "pending", None
            else:
                outcome, final = "lapsed", None
            bills.append({
                "country": "AT", "bill_id": f"{gp} {r.get('Nummer')}", "title": r.get("Betreff"),
                "year_introduced": int(date_in[:4]) if date_in else None,
                "origin": "government" if r["Art"] in ("RV", "RVS") else "parliament", "outcome": outcome,
                "date_introduced": date_in, "date_final": final,
                "instrument_type": "ratification" if r["Art"] == "RVS" else "law",
                "source": "parlament_gv_at_filter", "gp": gp, "art": r["Art"], "status_code": status,
            })
        log.info("at: GP %s: %d bills", gp, sum(1 for b in bills if b["gp"] == gp))
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS + ["gp", "art", "status_code"])
    if not bills_df.empty:
        bills_df = bills_df[bills_df.year_introduced.isin(BILL_YEARS)]
    write_csv(bills_df, INTER / "bills_at.csv")
    log.info("at: %d laws (%d with known origin), %d bills", len(laws_df),
             (laws_df.origin != "unknown").sum() if not laws_df.empty else 0, len(bills_df))


if __name__ == "__main__":
    main()
