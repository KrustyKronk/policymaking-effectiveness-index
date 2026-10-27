"""Germany: row-level laws and bills from the Bundestag DIP API, plus per-Wahlperiode totals from Bundestag
PDFs as a cross-check.

DIP API (key from .env DIP_API_KEY; the public key is published on the DIP help page):
- /vorgang?f.vorgangstyp=Gesetzgebung&f.wahlperiode=N for N = 14..21 (1998-2026), cursor pagination, every
  page cached under raw/de/dip/vorgang_wpN_pXXX.json.
- /drucksache?f.drucksachetyp=Gesetzentwurf&f.wahlperiode=N (cached as dip/gesetzentwurf_wpN_pXXX.json): the
  earliest Gesetzentwurf date per Vorgang id gives date_introduced / year_introduced cheaply (one Drucksache
  list per term instead of one vorgangsposition call per Vorgang); Vorgänge without one fall back to the
  term start.
Mapping:
- origin from `initiative`: Bundesregierung -> government; Fraktion / Gruppe / Abgeordnete / Bundestag ->
  parliament; Bundesrat or a Land -> other (a Vorgang with several initiators takes the first class in that
  order); empty -> unknown.
- outcome from `beratungsstand`: "Verkündet" (or a non-empty `verkuendung` list) -> enacted; "Abgelehnt" /
  "Bundesrat hat Zustimmung versagt" -> defeated; "Zurückgezogen" -> withdrawn; "Für erledigt erklärt" /
  "Erledigt durch Ablauf der Wahlperiode" / "Abgeschlossen - Ergebnis siehe Vorgangsablauf" -> lapsed;
  anything else ("Nicht abgeschlossen ...", committee stages) -> pending in the running term, lapsed in a
  closed term (Diskontinuität).
- laws_de.csv: enacted Vorgänge only, one row each; date = earliest `verkuendungsdatum` (BGBl), year = its
  year; "Haushaltsgesetz" -> budget_law; "Grundgesetz" changes -> constitutional_law; "Gesetz zu dem/zu
  den/zum ... Vertrag/Abkommen/Übereinkommen/Protokoll" (or published only in BGBl II) -> ratification.
- bills_de.csv: all Gesetzgebung Vorgänge with outcome, incl. Land/Bundesrat initiatives that never reached
  the Bundestag (so bill totals exceed the Datenhandbuch "eingebracht" counts).
Cross-check: raw/de/dip_vs_datenhandbuch.csv compares DIP enacted counts per WP and initiator with the
"verkündet" totals in raw/de/gesetzgebung_wp.csv (expected within ~5%).

PDF totals (no key), kept as the cross-check and as counts_de.csv:
- Datenhandbuch Kap. 10.1 "Statistik zur Gesetzgebung" (Stand 16.5.2025): final WP 12-20 tables of
  bills tabled in the Bundestag, passed (verabschiedet) and promulgated (verkündet), by initiator.
- "Statistik der Gesetzgebung - 21. Wahlperiode" (running snapshot, "Stand der Datenbank" in the PDF)
  for WP 21; the WP 20 PDF (Stand 30.04.2025) is parsed only as a cross-check of the handbook.
Parsing is regex over pdfplumber text: table rows read "label n1 pct1 n2 pct2 ...", so the integer
tokens without a decimal comma give the per-WP counts in header order.
Outputs:
- raw/de/gesetzgebung_wp.csv: wahlperiode, start_date, end_date, initiator (Bundesregierung /
  Bundesrat / Bundestag / all), introduced, passed, promulgated, source_url. "all" includes merged or
  split bills that the tables do not attribute to one initiator.
- data/intermediate/counts_de.csv: instrument_type law; origin government (Bundesregierung),
  parliament (Bundestag initiatives) and all (incl. Bundesrat and merged bills).
  PRO-RATA METHOD: each WP's promulgated total is spread over calendar years in proportion to the number
  of WP days falling in each year (start and end dates inclusive), so n is fractional (rounded to 0.1).
  This smooths real within-WP timing (output bunches before elections). WP 21 is still running: its
  promulgated-to-date count is spread over 2025-03-25 .. the PDF's "Stand" date and only the 2025 share
  is kept, so 2025 is provisional. The normaliser prefers laws_de.csv rows when they exist.
If the DIP step fails (no key), laws_de.csv falls back to ParlLawSpeech if a Germany laws .RDS exists in raw/pls/.

Back-extension (2026-10-18):
- DIP row level now covers WP 7-21 (DIP holds no Gesetzgebung Vorgänge for WP 1-6; WP 7 starts 1972-12-13, so
  1973 is the first complete calendar year of rows; WP 8-13 = 1976-1998 as requested, WP 7 added so 1976 is whole).
- Reference totals for WP 7-11 come from the "Datenhandbuch zur Geschichte des Deutschen Bundestages 1949-1999"
  (Schindler), Kap. 11.5 "Statistik zur Gesetzgebung", Detailübersicht ab der 7. WP (pp. 2393-2395, "Verkündete
  Gesetze, aufgeschlüsselt nach Initiatoren"); WP 12-13 come from the current Kap. 10.1 as before. The zip
  (raw/de/datenhandbuch_1949_1999.zip, Gesamt.pdf) is kept for provenance; the figures are typed in HIST_WP
  below because the 4,393-page PDF lays the tables out column-wise and is not worth a generic parser.
- WP 1-6: the handbook's "Statistische Gesamtübersicht" (p. 2388) only gives "verabschiedete Gesetzentwürfe"
  (passed by the Bundestag; verkündet is typically 1-4% lower: WP 7 516 vs 506, WP 8 354 vs 339). They are
  used as the per-term total for WP 1-6 and flagged in gesetzgebung_wp.csv (promulgated empty, passed filled).
  counts_de.csv spreads WP 1-11 totals pro rata to calendar years with source = datenhandbuch_pro_rata
  (promulgated where known, else passed); "Vereinigung von Initiativen" counts only in origin all.
"""
from __future__ import annotations

import datetime as dt
import re
import time

import pandas as pd

from pipeline.common import (BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, env, get, get_json, log,
                             write_csv)

D = RAW / "de"
DHB_URL = ("https://www.bundestag.de/resource/blob/196202/ee30d500ea94ebf8146d0ed7b12a8972/"
           "kapitel_10_01_statistik_zur_gesetzgebung-data.pdf")
WP_URLS = {20: "https://www.bundestag.de/resource/blob/870008/gesetzgebung_wp20.pdf",
           21: "https://www.bundestag.de/resource/blob/1067756/gesetzgebung_wp21.pdf"}
DIP = "https://search.dip.bundestag.de/api/v1"
DIP_WPS = range(7, 22)
DIP_PAUSE = 0.3
WP_DATES = {1: ("1949-09-07", "1953-10-05"), 2: ("1953-10-06", "1957-10-14"), 3: ("1957-10-15", "1961-10-16"),
            4: ("1961-10-17", "1965-10-18"), 5: ("1965-10-19", "1969-10-19"), 6: ("1969-10-20", "1972-12-12"),
            7: ("1972-12-13", "1976-12-13"), 8: ("1976-12-14", "1980-11-03"), 9: ("1980-11-04", "1983-03-28"),
            10: ("1983-03-29", "1987-02-17"), 11: ("1987-02-18", "1990-12-19"), 12: ("1990-12-20", "1994-11-09"),
            13: ("1994-11-10", "1998-10-25"), 14: ("1998-10-26", "2002-10-16"), 15: ("2002-10-17", "2005-10-17"),
            16: ("2005-10-18", "2009-10-26"), 17: ("2009-10-27", "2013-10-21"),
            18: ("2013-10-22", "2017-10-23"), 19: ("2017-10-24", "2021-10-25"),
            20: ("2021-10-26", "2025-03-24"), 21: ("2025-03-25", None)}
YEARS = range(1949, 2026)
DHB4999_URL = "https://www.bundestag.de/resource/blob/283210/datenhandbuch_1949_1999.zip"
# Datenhandbuch 1949-1999, Kap. 11.5: {wp: {initiator: {measure: n}}}. WP 1-6 from the Statistische
# Gesamtübersicht (p. 2388: introduced + passed only); WP 7-11 from the Detailübersicht (pp. 2392-2395).
HIST_WP = {
    1: {"all": {"introduced": 805, "passed": 545}, "Bundesregierung": {"introduced": 472, "passed": 392},
        "Bundestag": {"introduced": 301, "passed": 141}, "Bundesrat": {"introduced": 32, "passed": 12}},
    2: {"all": {"introduced": 877, "passed": 507}, "Bundesregierung": {"introduced": 446, "passed": 368},
        "Bundestag": {"introduced": 414, "passed": 132}, "Bundesrat": {"introduced": 17, "passed": 7}},
    3: {"all": {"introduced": 613, "passed": 424}, "Bundesregierung": {"introduced": 401, "passed": 348},
        "Bundestag": {"introduced": 207, "passed": 74}, "Bundesrat": {"introduced": 5, "passed": 2}},
    4: {"all": {"introduced": 635, "passed": 427}, "Bundesregierung": {"introduced": 378, "passed": 329},
        "Bundestag": {"introduced": 245, "passed": 96}, "Bundesrat": {"introduced": 12, "passed": 2}},
    5: {"all": {"introduced": 665, "passed": 453}, "Bundesregierung": {"introduced": 417, "passed": 368},
        "Bundestag": {"introduced": 227, "passed": 76}, "Bundesrat": {"introduced": 21, "passed": 9}},
    6: {"all": {"introduced": 577, "passed": 335}, "Bundesregierung": {"introduced": 362, "passed": 259},
        "Bundestag": {"introduced": 171, "passed": 58}, "Bundesrat": {"introduced": 44, "passed": 13}},
    7: {"all": {"introduced": 670, "passed": 516, "promulgated": 506},
        "Bundesregierung": {"introduced": 461, "passed": 427, "promulgated": 421},
        "Bundestag": {"introduced": 136, "passed": 62, "promulgated": 58},
        "Bundesrat": {"introduced": 73, "passed": 17, "promulgated": 17}},
    8: {"all": {"introduced": 485, "passed": 354, "promulgated": 339},
        "Bundesregierung": {"introduced": 322, "passed": 288, "promulgated": 276},
        "Bundestag": {"introduced": 111, "passed": 39, "promulgated": 36},
        "Bundesrat": {"introduced": 52, "passed": 15, "promulgated": 15}},
    9: {"all": {"introduced": 242, "passed": 139, "promulgated": 136},
        "Bundesregierung": {"introduced": 146, "passed": 104, "promulgated": 102},
        "Bundestag": {"introduced": 58, "passed": 16, "promulgated": 15},
        "Bundesrat": {"introduced": 38, "passed": 8, "promulgated": 8}},
    10: {"all": {"introduced": 522, "passed": 320, "promulgated": 320},
         "Bundesregierung": {"introduced": 280, "passed": 237, "promulgated": 237},
         "Bundestag": {"introduced": 183, "passed": 42, "promulgated": 42},
         "Bundesrat": {"introduced": 59, "passed": 32, "promulgated": 32}},
    11: {"all": {"introduced": 595, "passed": 369, "promulgated": 366},
         "Bundesregierung": {"introduced": 321, "passed": 267, "promulgated": 265},
         "Bundestag": {"introduced": 227, "passed": 68, "promulgated": 67},
         "Bundesrat": {"introduced": 47, "passed": 15, "promulgated": 15}},
}
INIT = {"Regierungsvorlagen": "Bundesregierung", "Initiativen des Bundesrates": "Bundesrat",
        "Initiativen des Bundestages": "Bundestag"}
ORIGIN = {"Bundesregierung": "government", "Bundestag": "parliament", "all": "all"}


def pdf_pages(path) -> list[str]:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def ints(rest: str) -> list[int]:
    return [int(t) if t.isdigit() else 0 for t in rest.split() if "," not in t and (t.isdigit() or t in "–-")]


def parse_dhb(pages: list[str]) -> dict[int, dict]:
    """-> {wp: {initiator: {introduced|passed|promulgated: n}}}"""
    sections = {"introduced": ("Beim Bundestag eingebrachte Gesetzesvorhaben, aufgeschlüsselt nach Initiatoren",
                               r"^Beim Bundestag eingebrachte (\d.*)$"),
                "passed": ("Verabschiedete Gesetze, aufgeschlüsselt nach Initiatoren",
                           r"^Vom Bundestag verabschiedete (\d.*)$"),
                "promulgated": ("Verkündete Gesetze, aufgeschlüsselt nach Initiatoren", r"^Verkündete Gesetze (\d.*)$")}
    out: dict[int, dict] = {}
    for measure, (heading, total_re) in sections.items():
        page = next((p for p in pages if heading in p.splitlines()), None)
        if page is None:
            log.warning("de: Datenhandbuch section not found: %s", heading)
            continue
        lines = page.splitlines()
        hdr = next((ln for ln in lines if re.match(r"^\d+\. WP( \d+\. WP)+$", ln.strip())), "")
        wps = [int(x) for x in re.findall(r"(\d+)\. WP", hdr)]
        rows = {}
        for ln in lines:
            m = re.match(total_re, ln.strip())
            if m and "all" not in rows:
                rows["all"] = ints(m.group(1))
            for label, init in INIT.items():
                m = re.match(rf"^{label} (\d.*)$", ln.strip())
                if m and init not in rows:
                    rows[init] = ints(m.group(1))
        for init, vals in rows.items():
            if len(vals) != len(wps):
                log.warning("de: %s/%s: %d values for %d WPs, skipped", measure, init, len(vals), len(wps))
                continue
            for wp, v in zip(wps, vals):
                out.setdefault(wp, {}).setdefault(init, {})[measure] = v
    return out


def parse_wp_pdf(pages: list[str]) -> tuple[dict, str | None]:
    """Running 'Statistik der Gesetzgebung' PDF -> ({initiator: {measure: n}}, stand ISO date)."""
    text = "\n".join(pages)
    m = re.search(r"Stand der Datenbank: (\d{2})\.(\d{2})\.(\d{4})", text)
    stand = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
    marks = [("introduced", r"^2\. Beim Bundestag eingebracht (\d+)"),
             ("passed", r"^4\. Vom Bundestag verabschiedet.*?(\d+)$"),
             ("promulgated", r"^7\. Verkündungen (\d+)")]
    out: dict[str, dict] = {}
    lines = [ln.strip() for ln in text.splitlines()]
    for measure, rx in marks:
        idx = next((i for i, ln in enumerate(lines) if re.match(rx, ln)), None)
        if idx is None:
            log.warning("de: WP pdf section not found: %s", measure)
            continue
        out.setdefault("all", {})[measure] = int(re.match(rx, lines[idx]).group(1))
        for ln in lines[idx + 1:]:
            if re.match(r"^\d\. ", ln):
                break
            for label, init in INIT.items():
                mm = re.match(rf"^{label} (\d+)$", ln)
                if mm and measure not in out.get(init, {}):
                    out.setdefault(init, {})[measure] = int(mm.group(1))
    return out, stand


def year_shares(start: str, end: str) -> dict[int, float]:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    total = (b - a).days + 1
    out = {}
    for y in range(a.year, b.year + 1):
        lo, hi = max(a, dt.date(y, 1, 1)), min(b, dt.date(y, 12, 31))
        out[y] = ((hi - lo).days + 1) / total
    return out


def dip_list(entity: str, wp: int, filters: dict, prefix: str) -> list[dict]:
    """All documents of a DIP list endpoint for one Wahlperiode, following the cursor until it stops changing.
    Pages are cached as raw/de/dip/{prefix}_wp{wp}_p{page}.json."""
    key = env("DIP_API_KEY")
    if not key:
        raise RuntimeError("DIP_API_KEY missing in .env")
    headers = {"Authorization": f"ApiKey {key}"}
    docs, cursor, page, num_found = [], None, 1, None
    while True:
        dest = D / "dip" / f"{prefix}_wp{wp}_p{page:03d}.json"
        cached = dest.exists()
        params = {**filters, "f.wahlperiode": wp, "format": "json"}
        if cursor:
            params["cursor"] = cursor
        j = get_json(f"{DIP}/{entity}", dest, params=params, headers=headers)
        if not cached:
            time.sleep(DIP_PAUSE)
        num_found = j.get("numFound", num_found)
        batch = j.get("documents") or []
        docs.extend(batch)
        nxt = j.get("cursor")
        if not batch or not nxt or nxt == cursor:
            break
        cursor, page = nxt, page + 1
    if num_found is not None and len(docs) != num_found:
        log.warning("de dip %s wp%d: numFound %s, got %d", entity, wp, num_found, len(docs))
    return docs


PARL_RX = re.compile(r"^(Fraktion|Gruppe|Abgeordnete|Bundestag|Ausschuss)", re.I)
RATIF_RX = re.compile(r"Gesetz zu (dem|den|der|diesem|dieser|zum|zur) .*(Vertrag|Abkommen|Übereinkommen|Protokoll|"
                      r"Vereinbarung|Konvention|Charta|Satzung)|^Gesetz zu(m|r) .*(Vertrag|Abkommen|Übereinkommen|"
                      r"Protokoll)|Vertragsgesetz", re.I)
LAPSED = {"Für erledigt erklärt", "Erledigt durch Ablauf der Wahlperiode", "Abgeschlossen - Ergebnis siehe Vorgangsablauf"}
DEFEATED = {"Abgelehnt", "Bundesrat hat Zustimmung versagt"}


def dip_origin(initiative: list[str] | None) -> str:
    inits = initiative or []
    if any(i == "Bundesregierung" for i in inits):
        return "government"
    if any(PARL_RX.match(i) for i in inits):
        return "parliament"
    if inits:
        return "other"  # Bundesrat or Länder
    return "unknown"


def dip_outcome(v: dict, current: bool) -> str:
    st = (v.get("beratungsstand") or "").strip()
    if st == "Verkündet" or v.get("verkuendung"):
        return "enacted"
    if st in DEFEATED:
        return "defeated"
    if st == "Zurückgezogen":
        return "withdrawn"
    if st in LAPSED:
        return "lapsed"
    return "pending" if current else "lapsed"


def dip_law_date(v: dict) -> str | None:
    dates = []
    for e in v.get("verkuendung") or []:
        d = e.get("verkuendungsdatum") or e.get("ausfertigungsdatum")
        if d:
            dates.append(d[:10])
    return min(dates) if dates else (v.get("datum") or None)


def dip_instrument(title: str, v: dict) -> str:
    t = title or ""
    if re.search(r"Haushaltsgesetz", t):
        return "budget_law"
    if re.search(r"Grundgesetz", t) and re.search(r"Änderung|Ergänzung|ändernd", t):
        return "constitutional_law"
    blatt = {e.get("verkuendungsblatt_kuerzel") for e in v.get("verkuendung") or [] if e.get("verkuendungsblatt_kuerzel")}
    if RATIF_RX.search(t) or (blatt and blatt <= {"BGBl II"}):
        return "ratification"
    return "law"


def laws_from_dip(wp_rows: list[dict]) -> None:
    """laws_de.csv + bills_de.csv from DIP, and the per-WP comparison with the Datenhandbuch."""
    laws, bills, by_wp = [], [], {}
    for wp in DIP_WPS:
        current = WP_DATES[wp][1] is None
        intro: dict[str, str] = {}
        for ds in dip_list("drucksache", wp, {"f.drucksachetyp": "Gesetzentwurf"}, "gesetzentwurf"):
            d = (ds.get("datum") or "")[:10]
            for ref in ds.get("vorgangsbezug") or []:
                if d and ref.get("vorgangstyp") == "Gesetzgebung":
                    vid = str(ref.get("id"))
                    intro[vid] = min(intro[vid], d) if vid in intro else d
        vs = dip_list("vorgang", wp, {"f.vorgangstyp": "Gesetzgebung"}, "vorgang")
        log.info("de dip wp%d: %d Gesetzgebung Vorgänge, %d with a Gesetzentwurf date", wp, len(vs), len(intro))
        for v in vs:
            vid, title = str(v.get("id")), (v.get("titel") or "").strip()
            title = re.sub(r"\s*\(G-SIG: \d+\)\s*$", "", title)
            origin, outcome = dip_origin(v.get("initiative")), dip_outcome(v, current)
            d_intro = intro.get(vid)
            law_date = dip_law_date(v) if outcome == "enacted" else None
            bills.append({"country": "DE", "bill_id": vid, "title": title,
                          "year_introduced": int(d_intro[:4]) if d_intro else int(WP_DATES[wp][0][:4]),
                          "origin": origin, "outcome": outcome, "date_introduced": d_intro,
                          "date_final": law_date or (v.get("datum") or None), "instrument_type": dip_instrument(title, v),
                          "source": "bundestag_dip", "wahlperiode": wp, "beratungsstand": v.get("beratungsstand"),
                          "initiative": "; ".join(v.get("initiative") or []), "gesta": v.get("gesta"),
                          "sachgebiet": "; ".join(v.get("sachgebiet") or []), "year_introduced_estimated": d_intro is None})
            if outcome != "enacted":
                continue
            itype = dip_instrument(title, v)
            fund = "; ".join(e.get("fundstelle") or "" for e in v.get("verkuendung") or [])
            inits = v.get("initiative") or []
            by_wp.setdefault(wp, {}).setdefault("all", 0)
            by_wp[wp]["all"] += 1
            init_cls = ("Bundesregierung" if "Bundesregierung" in inits else "Bundestag" if origin == "parliament"
                        else "Bundesrat" if origin == "other" else "unknown")
            by_wp[wp][init_cls] = by_wp[wp].get(init_cls, 0) + 1
            laws.append({"country": "DE", "year": int(law_date[:4]) if law_date else int(WP_DATES[wp][0][:4]),
                         "date": law_date, "instrument_type": itype, "origin": origin, "title": title,
                         "length_words": None, "cap_topic": None, "is_budget": itype == "budget_law",
                         "is_ratification": itype == "ratification", "source": "bundestag_dip", "source_id": vid,
                         "source_url": f"https://dip.bundestag.de/vorgang/{vid}",
                         "wahlperiode": wp, "fundstelle": fund, "gesta": v.get("gesta"),
                         "sachgebiet": "; ".join(v.get("sachgebiet") or [])})
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["wahlperiode", "fundstelle", "gesta", "sachgebiet"])
    write_csv(laws_df, INTER / "laws_de.csv")
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS + ["wahlperiode", "beratungsstand", "initiative", "gesta",
                                                           "sachgebiet", "year_introduced_estimated"])
    write_csv(bills_df, INTER / "bills_de.csv")
    log.info("de dip: %d bills, %d enacted laws; outcomes %s", len(bills_df), len(laws_df),
             bills_df.outcome.value_counts().to_dict())

    # comparison with the Datenhandbuch / WP-PDF "verkündet" totals
    ref = {(r["wahlperiode"], r["initiator"]): r["promulgated"] for r in wp_rows}
    comp = []
    for wp in DIP_WPS:
        for init in ("Bundesregierung", "Bundesrat", "Bundestag", "all"):
            n_dip, n_ref = by_wp.get(wp, {}).get(init, 0), ref.get((wp, init))
            pct = round(100 * (n_dip - n_ref) / n_ref, 1) if n_ref else None
            comp.append({"wahlperiode": wp, "initiator": init, "dip_enacted": n_dip, "datenhandbuch_verkuendet": n_ref,
                         "pct_diff": pct})
            if init == "all":
                log.info("de wp%d enacted: DIP %d vs Datenhandbuch %s (%s%%)", wp, n_dip, n_ref, pct)
    pd.DataFrame(comp).to_csv(D / "dip_vs_datenhandbuch.csv", index=False)
    log.info("de: wrote raw/de/dip_vs_datenhandbuch.csv")


def laws_from_pls() -> None:
    files = [p for p in (RAW / "pls").glob("*") if p.suffix.lower() == ".rds"
             and re.search(r"(germany|_de|de_|bundestag)", p.name, re.I) and re.search(r"law", p.name, re.I)]
    if not files:
        log.info("de: no ParlLawSpeech Germany laws .RDS in raw/pls/; laws_de.csv skipped")
        return
    import pyreadr
    df = next(iter(pyreadr.read_r(str(files[0])).values()))
    tcol = next((c for c in ("text", "law_text", "full_text") if c in df.columns), None)
    rows = []
    for _, r in df.iterrows():
        date = str(r.get("adoption_date") or "")[:10]
        if not date[:4].isdigit() or not 2009 <= int(date[:4]) <= 2021:
            continue
        rows.append({"country": "DE", "year": int(date[:4]), "date": date, "instrument_type": "law",
                     "origin": "unknown", "title": r.get("title"),
                     "length_words": len(str(r[tcol]).split()) if tcol and pd.notna(r[tcol]) else None,
                     "cap_topic": None, "is_budget": bool(re.search(r"Haushalt", str(r.get("title")))),
                     "is_ratification": bool(re.search(r"Vertragsgesetz|zu dem (Abkommen|Übereinkommen|Vertrag)",
                                                       str(r.get("title")))),
                     "source": "parllawspeech", "source_id": r.get("law_id", r.get("id")),
                     "source_url": "https://doi.org/10.7802/2824"})
    write_csv(pd.DataFrame(rows, columns=LAWS_COLUMNS), INTER / "laws_de.csv")


def main():
    data: dict[int, dict] = {wp: v for wp, v in HIST_WP.items()}
    srcs: dict[int, str] = {wp: DHB4999_URL for wp in HIST_WP}
    try:
        get(DHB4999_URL, D / "datenhandbuch_1949_1999.zip", timeout=600)  # provenance copy of the source
    except Exception as e:  # noqa: BLE001
        log.warning("de: Datenhandbuch 1949-1999 zip not downloaded (%s); typed HIST_WP totals still used", e)
    try:
        dhb = parse_dhb(pdf_pages_cached(DHB_URL, D / "kapitel_10_01_statistik_zur_gesetzgebung.pdf"))
        for wp, v in dhb.items():
            if wp in WP_DATES and wp not in HIST_WP:
                data[wp], srcs[wp] = v, DHB_URL
    except Exception as e:  # noqa: BLE001
        log.warning("de: Datenhandbuch failed: %s", e)

    stand21 = None
    for wp, url in WP_URLS.items():
        try:
            time.sleep(0.3)
            v, stand = parse_wp_pdf(pdf_pages_cached(url, D / f"gesetzgebung_wp{wp}.pdf"))
        except Exception as e:  # noqa: BLE001
            log.warning("de: WP%d pdf failed: %s", wp, e)
            continue
        if wp in data:  # cross-check only
            for init, ms in v.items():
                for m, n in ms.items():
                    ref = data[wp].get(init, {}).get(m)
                    if ref is not None and ref != n:
                        log.info("de: WP%d %s %s: handbook %s vs WP pdf (Stand %s) %s", wp, init, m, ref, stand, n)
        else:
            data[wp], srcs[wp] = v, url
            if wp == 21:
                stand21 = stand

    rows = []
    for wp in sorted(data):
        start, end = WP_DATES[wp]
        for init in ("Bundesregierung", "Bundesrat", "Bundestag", "all"):
            ms = data[wp].get(init, {})
            rows.append({"wahlperiode": wp, "start_date": start, "end_date": end, "initiator": init,
                         "introduced": ms.get("introduced"), "passed": ms.get("passed"),
                         "promulgated": ms.get("promulgated"), "source_url": srcs[wp]})
    wp_df = pd.DataFrame(rows, columns=["wahlperiode", "start_date", "end_date", "initiator", "introduced",
                                        "passed", "promulgated", "source_url"])
    D.mkdir(parents=True, exist_ok=True)
    wp_df.to_csv(D / "gesetzgebung_wp.csv", index=False)
    log.info("de: gesetzgebung_wp.csv with WPs %s", sorted(data))

    acc: dict[tuple[int, str], float] = {}
    src_of: dict[tuple[int, str], set] = {}
    hist_keys: set[tuple[int, str]] = set()
    for r in rows:
        total = r["promulgated"] if r["promulgated"] is not None else (
            r["passed"] if r["wahlperiode"] in HIST_WP else None)  # WP 1-6: only "verabschiedet" is published
        if r["initiator"] not in ORIGIN or total is None:
            continue
        end = r["end_date"] or stand21 or dt.date.today().isoformat()
        for y, sh in year_shares(r["start_date"], end).items():
            if y in YEARS:
                k = (y, ORIGIN[r["initiator"]])
                acc[k] = acc.get(k, 0.0) + total * sh
                src_of.setdefault(k, set()).add(r["source_url"])
                if r["wahlperiode"] in HIST_WP:
                    hist_keys.add(k)
    counts = [{"country": "DE", "year": y, "instrument_type": "law", "origin": o, "n": round(n, 1),
               "source": "datenhandbuch_pro_rata" if (y, o) in hist_keys else "bundestag_statistik_pro_rata",
               "source_url": " ".join(sorted(src_of[(y, o)]))}
              for (y, o), n in sorted(acc.items())]
    write_csv(pd.DataFrame(counts, columns=COUNTS_COLUMNS), INTER / "counts_de.csv")
    if stand21:
        log.info("de: WP21 counted to Stand %s; 2025 is provisional", stand21)

    try:
        laws_from_dip(rows)
    except Exception as e:  # noqa: BLE001
        log.warning("de: DIP step failed (%s); falling back to ParlLawSpeech", e)
        try:
            laws_from_pls()
        except Exception as e2:  # noqa: BLE001
            log.warning("de: ParlLawSpeech step failed: %s", e2)


def pdf_pages_cached(url, dest) -> list[str]:
    get(url, dest)
    return pdf_pages(dest)


if __name__ == "__main__":
    main()
