"""Bulgaria: National Assembly undocumented JSON API (parliament.bg), 2009-2025.

- POST /api/v1/fn-acts/1 {"date1","date2","search":1}: laws promulgated in the State Gazette (the date filter
  is on L_Act_date2 = State Gazette date; L_Act_dv_year/dv_iss = gazette year/issue). One call per year
  2009..2025, cached as raw/bg/acts_YYYY.json. Year = gazette year. The register starts in June 2009 (41st NA):
  2009 is a part year and 2000-2008 is a GAP (pre-2009 would need the State Gazette dv.parliament.bg or lex.bg).
- POST /api/v1/fn-bills {"date1","date2","search":1}: bills by submission date (L_Act_date), 2008-07..2026, cached
  as raw/bg/bills_YYYY.json. Importer: imp_list_min non-empty = Council of Ministers (A_ns_C_id 6167, constant
  across assemblies) -> government; imp_list = MPs -> parliament. Bills with neither are committee
  "consolidated bills" (Общ законопроект / ЗИД, signature NNN-553-..), which merge bills passed at first
  reading; their members come from GET /api/v1/bill/{id} union_list (cached raw/bg/bill_ID.json).
- Join: acts carry L_Act_sign = signature of the bill that became the law. Signatures repeat across assemblies,
  so the act is matched to the latest bill with that signature submitted on/before the gazette date (bill_id in
  bills_bg.csv = "signature#L_Act_id"). A law's origin is its bill's origin;
  for a consolidated bill: government if all members are government bills, parliament if all are MP bills,
  else other (mixed). Unmatched signatures -> unknown.
- bills_bg.csv: one row per original bill (consolidated bills excluded, they are not new initiatives).
  Outcome: enacted if its signature is in the acts register or it is a member of an enacted consolidated
  bill; otherwise pending if submitted to the current 51st NA (from 2024-11-11), else lapsed. The list
  endpoint does not distinguish defeated/withdrawn from lapsed, so "lapsed" here = not enacted.
- Classification: title contains "бюджет" -> budget_law (state budget, social security and health-fund
  budget laws and budget-extension laws); "ратифициране" -> ratification.

Back-extension 2003-2008 (counts only, counts_bg.csv, source "dv_parliament_bg_contents", origin "all"):
- State Gazette web archive dv.parliament.bg (MyFaces JSF, stateful postbacks). broeveList.faces filtered by
  date range (from_date/to_date) lists the year's issues 10 per page; each issue's "Съдържание на официалния
  раздел" postback (materiali.faces) lists the official-section materials, 30 per page, grouped by issuer. A law
  = a material issued by "Народно събрание" whose title starts with "Закон" or ends in "кодекс" (decisions,
  declarations and rules of procedure dropped); "ратифициране" -> ratification, "бюджет" -> budget_law.
  Year = gazette issue year. Pages cached under raw/bg/dv/.
- The archive holds issues back to 1992 but the per-issue contents are empty before 2003 (scanned PDFs only),
  so 1991-2002 remains a GAP (no machine-readable yearly listing found on dv.parliament.bg, lex.bg or the
  parliament.bg API, which starts in June 2009).
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import time

import pandas as pd

from pipeline.common import (BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, manifest_add,
                             session, write_csv)

API = "https://www.parliament.bg/api/v1"
D = RAW / "bg"
YEARS = range(2009, 2026)
GOV_ID = 6167
CURRENT_NA_START = "2024-11-11"
HDR = {"Content-Type": "application/json", "Accept": "application/json"}


DV = "https://dv.parliament.bg/DVWeb"
DV_YEARS = range(2003, 2009)


def _vs(t: str) -> str:
    return re.search(r'name="javax.faces.ViewState"[^>]*value="([^"]*)"', t).group(1)


def _broi_form(t: str, extra: dict) -> dict:
    d = {"broi_form:not_first": "1", "broi_form:_idJsp61": "", "broi_form:_idJsp67": "", "broi_form:_idJsp69": "",
         "broi_form:from_date": "", "broi_form:to_date": "", "broi_form:period_": "", "broi_form:selectPageTop": "1",
         "broi_form:selectPage": "1", "broi_form_SUBMIT": "1", "broi_form:_link_hidden_": "", "id_": "",
         "date_izd_": "", "idObj": "", "broi_form:_idcl": "", "razdel_": "", "broi_": "", "javax.faces.ViewState": _vs(t)}
    d.update(extra)
    return d


def _form_inputs(t: str, form_id: str) -> dict:
    m = re.search(rf'<form id="{form_id}".*?</form>', t, re.S)
    out = {}
    for tag in re.findall(r"<input[^>]*>", m.group(0) if m else ""):
        n = re.search(r'name="([^"]*)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n and "type=\"checkbox\"" not in tag:
            out[n.group(1)] = htmlmod.unescape(v.group(1)) if v else ""
    return out


def _text(t: str) -> str:
    t = re.sub(r"<(script|style).*?</\1>", "", t, flags=re.S)
    return htmlmod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))


def _ns_laws(page_html: str) -> list[str]:
    """Titles of National Assembly laws in one contents page."""
    out = []
    for chunk in _text(page_html).split("Преглед на материала"):
        chunk = chunk.strip()
        m = re.search(r"Народно събрание (.+?) стр\. \d+\s*$", chunk)
        if not m:
            continue
        title = m.group(1).strip()
        if title.startswith("Закон") or re.search(r"кодекс$", title, re.I) or title.startswith("Кодекс"):
            out.append(title)
    return out


def _save(dest, url: str, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    b = text.encode("utf-8")
    dest.write_bytes(b)
    manifest_add(dest, url, b)


def dv_year(y: int) -> list[dict] | None:
    """National Assembly laws published in State Gazette issues of year y (None if the listing failed)."""
    U = f"{DV}/broeveList.faces"
    s = session()
    out: list[dict] = []
    try:
        lst = s.post(U, data=_broi_form(s.get(U, timeout=60).text,
                                        {"broi_form:from_date": f"01.01.{y}", "broi_form:to_date": f"31.12.{y}",
                                         "broi_form:btnFind11": "Търси"}), timeout=90).text
        n_issues = int(re.search(r"Намерени резултати:\s*(\d+)", lst).group(1))
    except Exception as e:  # noqa: BLE001
        log.warning("bg dv %d: issue list failed: %s", y, e)
        return None
    pages = (n_issues + 9) // 10
    seen = set()
    for pg in range(1, pages + 1):
        if pg > 1:
            try:
                lst = s.post(U, data=_broi_form(lst, {"broi_form:selectPage": str(pg), "broi_form:selectPageTop": str(pg),
                                                      "broi_form:_idcl": "broi_form:chP",
                                                      "broi_form:from_date": f"01.01.{y}",
                                                      "broi_form:to_date": f"31.12.{y}"}), timeout=90).text
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                log.warning("bg dv %d: list page %d failed: %s", y, pg, e)
                continue
        links = re.findall(r"oamSubmitForm\('broi_form','(broi_form:dataTable1:\d+:_idJsp\d+)',null,\[\['broi_','(\d+)'\],"
                           r"\['idObj','(\d+)'\],\['date_izd_','([\d-]+)'\],\['razdel_','1'\]\]", lst)
        for cid, broi, obj, date in links:
            if obj in seen or not date.startswith(str(y)):
                continue
            seen.add(obj)
            dest = D / "dv" / f"{date}_{broi}_{obj}.html"
            if dest.exists():
                pages_html = dest.read_text(encoding="utf-8").split("<!--PAGEBREAK-->")
            else:
                pages_html = []
                try:
                    c = s.post(U, data=_broi_form(lst, {"broi_form:_idcl": cid, "broi_": broi, "idObj": obj,
                                                        "date_izd_": date, "razdel_": "1"}), timeout=90).text
                    pages_html.append(c)
                    time.sleep(0.5)
                    n_mat = int((re.search(r"Намерени резултати:\s*(\d+)", c) or [0, 0])[1])
                    for _ in range(1, (n_mat + 29) // 30):    # further pages of the contents (30 per page)
                        f = _form_inputs(c, "material_form")
                        f["material_form:_idcl"] = "material_form:next_"
                        c = s.post(f"{DV}/materiali.faces", data=f, timeout=90).text
                        pages_html.append(c)
                        time.sleep(0.5)
                except Exception as e:  # noqa: BLE001
                    log.warning("bg dv %s issue %s: contents failed: %s", date, broi, e)
                    continue
                _save(dest, f"{DV}/broeveList.faces#idObj={obj}", "<!--PAGEBREAK-->".join(pages_html))
            titles = []
            for ph in pages_html:
                titles += [t for t in _ns_laws(ph) if t not in titles]
            out += [{"date": date, "broi": broi, "title": t} for t in titles]
    log.info("bg dv %d: %d issues, %d National Assembly laws", y, len(seen), len(out))
    return out


def dv_counts() -> pd.DataFrame:
    rows = []
    for y in DV_YEARS:
        laws = dv_year(y)
        if laws is None:
            continue
        df = pd.DataFrame(laws, columns=["date", "broi", "title"])
        df["itype"] = [classify(t)[0] for t in df.title]
        for it, n in df.groupby("itype").size().items():
            rows.append({"country": "BG", "year": y, "instrument_type": it, "origin": "all", "n": int(n),
                         "source": "dv_parliament_bg_contents", "source_url": f"{DV}/broeveList.faces"})
    return pd.DataFrame(rows, columns=COUNTS_COLUMNS)


def post_year(endpoint: str, year: int, dest) -> list[dict]:
    cached = dest.exists()
    body = {"date1": f"{year}-01-01", "date2": f"{year}-12-31", "search": 1}
    raw = get(f"{API}/{endpoint}", dest, method="POST", json_body=body, headers=HDR, timeout=120)
    if not cached:
        time.sleep(1.0)
    return json.loads(raw.decode("utf-8"))


def bill_detail(bid: int) -> dict:
    dest = D / f"bill_{bid}.json"
    cached = dest.exists()
    raw = get(f"{API}/bill/{bid}", dest, headers={"Accept": "application/json"})
    if not cached:
        time.sleep(0.5)
    return json.loads(raw.decode("utf-8"))


def classify(title: str) -> tuple[str, bool, bool]:
    t = (title or "").lower()
    if "ратифициране" in t:
        return "ratification", False, True
    if "бюджет" in t:
        return "budget_law", True, False
    return "law", False, False


def main():
    D.mkdir(parents=True, exist_ok=True)
    # --- bills (submission years 2008..2026 so that every promulgated act can be joined) -------
    # Signatures are NOT unique: short assemblies (2021-24) reuse prefixes, so key bills by L_Act_id and
    # resolve an act's signature to the latest bill with that signature submitted on or before its gazette date.
    by_id: dict[int, dict] = {}
    by_sign: dict[str, list[dict]] = {}
    for y in range(2008, 2027):
        for b in post_year("fn-bills", y, D / f"bills_{y}.json"):
            if b["L_Act_id"] not in by_id:
                by_id[b["L_Act_id"]] = b
                by_sign.setdefault(b["L_Act_sign"], []).append(b)

    def resolve(sign: str, gazette_date: str) -> dict | None:
        cands = sorted(by_sign.get(sign, []), key=lambda b: b.get("L_Act_date") or "")
        ok = [b for b in cands if (b.get("L_Act_date") or "")[:10] <= (gazette_date or "9999")]
        return (ok or cands or [None])[-1]

    def base_origin(b: dict) -> str | None:
        if b.get("imp_list_min"):
            return "government"
        if b.get("imp_list"):
            return "parliament"
        return None   # consolidated bill

    # --- acts ---------------------------------------------------------------------------------
    acts = []
    for y in YEARS:
        acts += post_year("fn-acts/1", y, D / f"acts_{y}.json")
    acts = list({a["L_Act_id"]: a for a in acts}.values())
    enacted_ids: set[int] = set()

    def origin_of(b: dict | None) -> str:
        if b is None:
            return "unknown"
        enacted_ids.add(b["L_Act_id"])
        o = base_origin(b)
        if o:
            return o
        det = bill_detail(b["L_Act_id"])
        mem = [m["L_Act_id"] for m in det.get("union_list") or []]
        enacted_ids.update(mem)
        mo = {base_origin(by_id[m]) if m in by_id else None for m in mem}
        mo.discard(None)
        if mo == {"government"}:
            return "government"
        if mo == {"parliament"}:
            return "parliament"
        return "other" if mo else "unknown"

    laws = []
    for a in acts:
        date = (a.get("L_Act_date2") or "")[:10]
        year = int(date[:4]) if date else a.get("L_Act_dv_year")
        if year not in YEARS:
            continue
        title = a.get("L_ActL_final") or ""
        itype, is_b, is_r = classify(title)
        laws.append({
            "country": "BG", "year": year, "date": date or None, "instrument_type": itype,
            "origin": origin_of(resolve(a["L_Act_sign"], date)), "title": title, "length_words": None, "cap_topic": None,
            "is_budget": is_b, "is_ratification": is_r, "source": "parliament_bg_acts",
            "source_id": a["L_Act_sign"], "source_url": f"https://www.parliament.bg/bg/bills/ID/{a['L_Act_id']}",
        })
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_bg.csv")
    log.info("bg laws per year: %s", laws_df.groupby("year").size().to_dict())
    log.info("bg law origins: %s", laws_df.origin.value_counts().to_dict())

    # --- bills_bg.csv ---------------------------------------------------------------------------
    rows = []
    for bid, b in by_id.items():
        sign = b["L_Act_sign"]
        o = base_origin(b)
        if o is None:
            continue
        date = (b.get("L_Act_date") or "")[:10]
        if not date or date < "2009-07-14":       # 41st NA first sitting; earlier rows are carry-overs
            continue
        if bid in enacted_ids:
            outcome = "enacted"
        elif date >= CURRENT_NA_START:
            outcome = "pending"
        else:
            outcome = "lapsed"
        title = b.get("L_ActL_title") or ""
        rows.append({"country": "BG", "bill_id": f"{sign}#{bid}", "title": title, "year_introduced": int(date[:4]),
                     "origin": o, "outcome": outcome, "date_introduced": date, "date_final": None,
                     "instrument_type": classify(title)[0], "source": "parliament_bg_bills"})
    bills_df = pd.DataFrame(rows, columns=BILLS_COLUMNS).sort_values(["date_introduced", "bill_id"])
    bills_df = bills_df[bills_df.year_introduced <= 2025]
    write_csv(bills_df, INTER / "bills_bg.csv")
    log.info("bg bills: %s", bills_df.groupby(["origin", "outcome"]).size().to_dict())

    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="BG", source="parliament_bg_acts", source_url=f"{API}/fn-acts/1"))
    try:
        back = dv_counts()
    except Exception as e:  # noqa: BLE001
        log.warning("bg: State Gazette back-extension failed: %s", e)
        back = pd.DataFrame(columns=COUNTS_COLUMNS)
    if len(back):
        log.info("bg back-extension laws per year: %s", back.groupby("year").n.sum().to_dict())
    write_csv(pd.concat([back, counts[COUNTS_COLUMNS]], ignore_index=True), INTER / "counts_bg.csv")


if __name__ == "__main__":
    main()
