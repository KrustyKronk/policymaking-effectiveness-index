"""Czechia: Poslanecká sněmovna open data (psp.cz/sqw/hp.sqw?k=1300), pipe-delimited UNL files in cp1250.
- sbirka.zip: Collection of Laws since 1993 (druh_predpisu 1 = zákon, 14 = ústavní zákon); regulations (vyhláška,
  nařízení...) dropped. Treaty notices (druh 2, Mezinárodní smlouva) are dropped too: they are MFA communications,
  not acts of parliament, and appear in the Sbírka zákonů only until 1999 (from 2000 in the separate Sbírka
  mezinárodních smluv), so keeping them broke the series at 2000. Laws per year 1993-2023 match ParlText CZ to +-5 -> laws_cz.csv + counts_cz.csv. Title and origin come from the
  linked chamber print (tisky.id_tisk).
- tisky.zip: chamber prints; druh_tisku 1 = government bill, 2 = non-government bill (typ_zakon: PO/SP deputies,
  SE Senate, regions), 3 = state budget. Outcome from the final state (typ_stavu 6 = KONEC) and the last
  transition's action in hist/prechody/typ_akce -> bills_cz.csv."""
from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

BASE = "https://www.psp.cz/eknih/cdrom/opendata"
D = RAW / "cz"
TERMS = {165: 1993, 166: 1996, 167: 1998, 168: 2002, 169: 2006, 170: 2010, 171: 2013, 172: 2017, 173: 2021,
         174: 2025}   # organy.id_org of the chamber terms (bills before 1993 carry no dates and are dropped)
FIRST_YEAR = 1993                 # Czech Republic's first year; earlier Sb. years are Austrian/Czechoslovak/ČNR acts
DP_TYPE = {"1": "law", "14": "constitutional_law"}
TREATY_DRUH = "2"
BILL_DRUH = {"1", "2", "3"}
NAVRH_ORIGIN = {"1": "government", "2": "parliament", "3": "parliament", "4": "other"}  # 6..19 = regions -> other
DEFEAT_RE = re.compile(r"zamítnut|nepřijat|neschválen|nesouhlas|vrácen", re.I)
WITHDRAW_RE = re.compile(r"vzat zpět|vzat zpet", re.I)
ENACT_RE = re.compile(r"schválen|vyhlášen|sbirka zakonu|sbírka zákonů", re.I)

_SPLIT = re.compile(r"(?<!\\)\|")


def unl(zip_path, name: str) -> list[list[str]]:
    with zipfile.ZipFile(zip_path) as z:
        text = z.read(name).decode("cp1250", errors="replace")
    rows = []
    for line in io.StringIO(text):
        line = line.rstrip("\r\n")
        if not line:
            continue
        rows.append([re.sub(r"\\(.)", r"\1", c) for c in _SPLIT.split(line)])
    return rows


def ddmmyyyy(s: str) -> str | None:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def main():
    sb_zip = D / "sbirka.zip"
    ti_zip = D / "tisky.zip"
    get(f"{BASE}/sbirka.zip", sb_zip, timeout=300)
    get(f"{BASE}/tisky.zip", ti_zip, timeout=300)

    # --- chamber prints (bills) ---------------------------------------------------------------
    tisky = {r[0]: r for r in unl(ti_zip, "tisky.unl")}
    stavy = {r[0]: r for r in unl(ti_zip, "stavy.unl")}
    typ_stavu = {r[0]: r[1] for r in unl(ti_zip, "typ_stavu.unl")}
    prechody = {r[0]: r for r in unl(ti_zip, "prechody.unl")}
    typ_akce = {r[0]: r[1] for r in unl(ti_zip, "typ_akce.unl")}
    last_hist: dict[str, list[str]] = {}
    sb_hist: dict[str, list[str]] = {}
    for h in sorted(unl(ti_zip, "hist.unl"), key=lambda h: int(h[0])):
        last_hist[h[1]] = h
        if len(h) > 13 and h[13]:
            sb_hist[h[1]] = h

    def bill_origin(t: list[str]) -> str:
        if t[1] in ("1", "3"):
            return "government"
        return NAVRH_ORIGIN.get(t[5], "other" if t[5] else "unknown")

    def bill_title(t: list[str]) -> str:
        return t[15] or t[10]

    # --- Collection of Laws ------------------------------------------------------------------
    sbirka = unl(sb_zip, "sbirka.unl")
    enacted_tisk = {r[4]: r for r in sbirka if r[4]}
    laws, no_tisk, pre1993, treaties = [], 0, 0, 0
    for r in sbirka:
        itype = DP_TYPE.get(r[3])
        if itype is None:
            treaties += r[3] == TREATY_DRUH and r[2].isdigit() and int(r[2]) >= FIRST_YEAR
            continue
        cislo, rok = r[1], int(r[2])
        if rok < FIRST_YEAR:           # the file reaches back to 1867 (Austrian, Czechoslovak and ČNR acts)
            pre1993 += 1
            continue
        date = ddmmyyyy(r[5]) or f"{rok}-01-01"
        t = tisky.get(r[4]) if r[4] else None
        if t is None:
            no_tisk += 1
            title, origin = f"Zákon č. {cislo}/{rok} Sb.", "unknown"
        else:
            title, origin = bill_title(t), bill_origin(t)
        tl = title.lower()
        is_budget = (t is not None and t[1] == "3") or "o státním rozpočtu" in tl
        is_rat = False
        if is_budget and itype == "law":
            itype = "budget_law"
        laws.append({
            "country": "CZ", "year": rok, "date": date, "instrument_type": itype, "origin": origin, "title": title,
            "length_words": None, "cap_topic": None, "is_budget": is_budget, "is_ratification": is_rat,
            "source": "psp_sbirka", "source_id": f"{cislo}/{rok} Sb.",
            "source_url": f"https://www.psp.cz/sqw/sbirka.sqw?cz={cislo}&r={rok}",
        })
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_cz.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="CZ", source="psp_sbirka", source_url=f"{BASE}/sbirka.zip"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_cz.csv")
    chk = laws_df[laws_df.instrument_type.isin(["law", "budget_law"])].groupby("year").size()
    log.info("cz: %d treaty notices (druh 2, 1993-99) dropped", treaties)
    log.info("cz: %d laws from 1993 (%d without a linked print -> origin unknown; %d pre-1993 acts dropped); "
             "laws per year 2000=%s 2010=%s 2018=%s 2023=%s", len(laws_df), no_tisk, pre1993,
             chk.get(2000), chk.get(2010), chk.get(2018), chk.get(2023))

    # --- bills ---------------------------------------------------------------------------------
    current_term = max(TERMS)
    bills, unmapped = [], {}
    for t in tisky.values():
        if t[1] not in BILL_DRUH:
            continue
        term = int(t[7]) if t[7].isdigit() else None
        if term not in TERMS:
            continue
        intro = next((d for d in (ddmmyyyy(t[11]), ddmmyyyy(t[12])) if d and d[:4] >= "1992"), None)
        # 44 early-1993-term prints carry a placeholder 1900 date: keep them with the term start year only
        tid = t[0]
        st = stavy.get(t[2])
        finished = st is not None and st[1] == "6"
        h = last_hist.get(tid)
        action = typ_akce.get(prechody.get(h[4], [""] * 5)[3], "") if h else ""
        final_date = (h[2] or "")[:10] if h else None
        if tid in enacted_tisk or tid in sb_hist:
            outcome = "enacted"
            sbr = enacted_tisk.get(tid)
            final_date = ddmmyyyy(sbr[5]) if sbr else (sb_hist[tid][11] and ddmmyyyy(sb_hist[tid][11])) or final_date
        elif finished and WITHDRAW_RE.search(action):
            outcome = "withdrawn"
        elif finished and DEFEAT_RE.search(action):
            outcome = "defeated"
        elif finished and ENACT_RE.search(action):
            outcome = "enacted"
        elif finished:
            unmapped[action] = unmapped.get(action, 0) + 1
            outcome = "lapsed"
        elif term == current_term:
            outcome, final_date = "pending", None
        else:
            outcome = "lapsed"       # unfinished at the end of the term
        title = bill_title(t)
        itype = ("budget_law" if t[1] == "3" or "o státním rozpočtu" in title.lower()
                 else "constitutional_law" if re.search(r"^(vládní )?návrh ústavního zákona|^ústavní zákon", title, re.I)
                 else "law")
        bills.append({
            "country": "CZ", "bill_id": f"{TERMS[term]}ps/{t[3]}", "title": title, "year_introduced": int(intro[:4]) if intro else TERMS[term],
            "origin": bill_origin(t), "outcome": outcome, "date_introduced": intro, "date_final": final_date,
            "instrument_type": itype, "source": "psp_tisky", "term": TERMS[term], "druh": t[1], "navrh": t[5],
            "final_state": typ_stavu.get(st[1], "") if st else "", "last_action": action,
        })
    if unmapped:
        log.warning("cz: finished bills with unmapped last action (-> lapsed): %s", unmapped)
    bills_df = pd.DataFrame(bills).sort_values(["date_introduced", "bill_id"])
    write_csv(bills_df[BILLS_COLUMNS + ["term", "druh", "navrh", "final_state", "last_action"]], INTER / "bills_cz.csv")
    log.info("cz bills: %s", bills_df.outcome.value_counts().to_dict())


if __name__ == "__main__":
    main()
