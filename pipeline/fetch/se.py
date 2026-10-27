"""Sweden.
- doktyp=prop per riksmöte 1999/2000-2026/27: government bills (and skrivelser, which the listing mixes in).
  Outcome from the listing's statusrad ("Riksdagsbeslut (N förslag): N bifall / N avslag"), which saves a
  per-prop rskr join.
- THROUGHPUT SERIES (laws_se.csv, rebuilt 2026-10-17): adopted government bills that contain at least one law,
  classified exactly from each prop's dokumentstatus (https://data.riksdagen.se/dokumentstatus/{dok_id}.json,
  fetched serially with a 0.3 s gap and back-off on HTTP 429, cached under raw/se/dokumentstatus/).
  Candidates: every prop (not skrivelse, not a budget annex such as GQ031d12) from riksmöte 2002/03 on that the
  listing marks adopted or leaves without a decision line (main budget props, a few others); earlier riksmöten
  lack decision lines in the listing and are not covered. Adopted = at least one dokforslag row whose chamber
  decision (kammaren, or utskottet when kammaren is "=utskottet") is bifall / delvis bifall / antagen. Law = an
  adopted row whose lydelse (+ lydelse2) contains "förslag till lag", "lag om ändring", or ends "antar regeringens
  förslag till" (older rows cut the object off; the Riksdag "antar" only statutes, it "godkänner" agreements and
  budgets). One row per adopted prop with >= 1 law, source = riksdagen_prop_dokumentstatus, origin government,
  n_law_proposals = distinct adopted law proposals. Adopted budget props ("Budgetpropositionen" / "statens
  budget" / "ändringsbudget") are kept as budget_law whatever their proposals; "godkännande av ... (avtal |
  konvention | överenskommelse | protokoll)" titles -> ratification (they usually carry an implementing law).
  Date (date_source column): a beslut activity in dokaktivitet if any (none seen: prop dokaktivitet lists only
  Inlämnad / Bordlagd / Hänvisad / Motionstid), else the systemdatum of dokuppgift statustext "Ärendet är
  avslutat" (stamped when the case closes after the chamber vote) when it falls between introduction and the end
  of the following year (older props carry 2014/2017/2019 migration stamps instead, see MIGRATION_STAMPS), else the riksmöte start
  YYYY-10-01 for riksmöte YYYY/YY+1. year = year of that date.
  Why: title/summary "lag" matching had no false positives in a 45-prop sample but missed ~14 of 15 law props;
  the earlier SFS listing (doktyp=sfs) mostly holds statutes still in force and undercounts older years. Those
  rows are kept in laws_se_sfs.csv for reference (not read by the normaliser): statutes in SFS as listed by the
  Riksdag per calendar year, laws = titles starting "Lag".
- counts_se.csv is aggregated from the laws_se rows (source riksdagen_prop_dokumentstatus)."""
from __future__ import annotations

import json
import re
import time

import pandas as pd

from pipeline.common import (BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get_json, log, manifest_add,
                             session, write_csv)

LIST = "https://data.riksdagen.se/dokumentlista/"
YEARS = range(2000, 2026)
D = RAW / "se"
PAUSE = 0.3
PAGE = 200  # the API caps sz at 200 whatever is requested


def riksmoten() -> list[str]:
    return ["1999/2000"] + [f"{y}/{(y + 1) % 100:02d}" for y in range(2000, 2027)]


def rm_start(rm: str) -> str:
    """Riksmöte YYYY/YY+1 starts in September; the series date is pinned to YYYY-10-01."""
    return f"{rm[:4]}-10-01"


def listing(doktyp: str, rm: str) -> list[dict]:
    docs, p, pages, total = [], 1, 1, None
    while p <= pages:
        dest = D / doktyp / f"{rm.replace('/', '-')}_p{p}.json"
        cached = dest.exists()
        try:
            j = get_json(LIST, dest, params={"doktyp": doktyp, "rm": rm, "utformat": "json", "sz": PAGE,
                                              "p": p, "sort": "datum", "sortorder": "asc"})
        except Exception as e:  # noqa: BLE001
            log.warning("se %s %s p%d failed: %s", doktyp, rm, p, e)
            break
        if not cached:
            time.sleep(PAUSE)
        dl = j.get("dokumentlista") or {}
        total = int(dl.get("@traffar") or 0)
        pages = int(dl.get("@sidor") or 1)
        d = dl.get("dokument") or []
        docs.extend([d] if isinstance(d, dict) else d)
        p += 1
    if total is not None and len(docs) != total:
        log.warning("se %s %s: %s hits announced, %d parsed", doktyp, rm, total, len(docs))
    return docs


def _status(d: dict) -> str:
    s = ((d.get("sokdata") or {}).get("statusrad")) or ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


CURRENT_RM = ("2026/27",)


def prop_outcome(d: dict, rm: str) -> str | None:
    """enacted / defeated from the listing's decision line; no decision line -> 'pending' for the current
    riksmöte, else None (unknown: the listing has no decision lines before 2002/03, and some props are
    reports/budget area props without a proposal-level decision)."""
    m = re.search(r"Riksdagsbeslut(.*?)(Sista motionsdag|$)", _status(d))
    if not m:
        return "pending" if rm in CURRENT_RM else None
    seg = m.group(1)
    bifall = sum(int(x) for x in re.findall(r"(\d+)\s*bifall", seg))
    avslag = sum(int(x) for x in re.findall(r"(\d+)\s*avslag", seg))
    if bifall:
        return "enacted"
    if avslag:
        return "defeated"
    return "pending" if rm in CURRENT_RM else None


def is_law(title: str) -> bool:
    t = title.strip()
    return (t.startswith("Lag") or "lag (" in t.lower()) and not t.startswith("Förordning")


# tokens ending in -lag that are not about statutes
LAG_STOP = {"förslag", "anslag", "beslag", "underlag", "uppslag", "tillslag", "avslag", "bakslag", "omslag", "utslag",
            "genomslag", "inslag", "påslag", "nedslag", "överslag", "slag", "anlag", "upplag", "belag", "förlag",
            "dagslag", "tidslag"}
TOKEN_RX = re.compile(r"[a-zåäöé]+", re.I)


def title_has_lag(title: str) -> bool:
    """True when a title token is a 'lag' word: lag/lagen/lagar/lagarna/lags, a compound ending in one
    (skollagen, plan- och bygglagen), or a token starting with lag- (lagändringar, lagstiftning, lagrådet);
    lager/lagring and the LAG_STOP words are not."""
    for tok in TOKEN_RX.findall(title.lower()):
        if tok.startswith("lag") and not re.match(r"lag(er|ret|ra|rad|rat|ras|ring|rin)", tok):
            return True
        m = re.match(r"(.*?lag)(en|ar|arna|s|ens|ars|arnas)?$", tok)
        if m and m.group(1) not in LAG_STOP:  # genitive compounds (delgivningslag, socialavgiftslagen) stay in
            return True
    return False


def prop_instrument(title: str) -> str:
    if re.search(r"budgetpropositionen|statens budget|ändringsbudget", title, re.I):
        return "budget_law"
    if re.search(r"godkännande av .*(avtal|konvention|överenskommelse|protokoll|stadga)", title, re.I):
        return "ratification"
    return "law"


DS = D / "dokumentstatus"
DS_PAUSE = 0.3
_DS_SESSION = None
_last_ds = 0.0


def dokumentstatus(dok: str) -> dict:
    """Per-prop dokumentstatus JSON, cached under raw/se/dokumentstatus/{dok}.json. Serial, DS_PAUSE between
    live calls; on HTTP 429 waits Retry-After (or an exponential back-off) and retries."""
    global _DS_SESSION, _last_ds
    dest = DS / f"{dok}.json"
    if not dest.exists():
        if _DS_SESSION is None:
            _DS_SESSION = session()
        url = f"https://data.riksdagen.se/dokumentstatus/{dok}.json"
        r, err = None, None
        for attempt in range(8):
            wait = DS_PAUSE - (time.monotonic() - _last_ds)
            if wait > 0:
                time.sleep(wait)
            try:
                r = _DS_SESSION.get(url, timeout=60)
                _last_ds = time.monotonic()
                if r.status_code == 200 and r.content.strip():
                    break
                err = f"HTTP {r.status_code}"
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    pause = float(ra) if ra and ra.isdigit() else min(5 * 2 ** attempt, 300)
                    log.warning("se dokumentstatus 429 for %s, sleeping %.0fs", dok, pause)
                    time.sleep(pause)
                    continue
                if r.status_code == 404:
                    break
            except Exception as e:  # noqa: BLE001
                err = str(e)
                _last_ds = time.monotonic()
            time.sleep(min(2 ** attempt, 60))
        if r is None or r.status_code != 200 or not r.content.strip():
            raise RuntimeError(f"dokumentstatus {dok} failed: {err}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        manifest_add(dest, url, r.content)
    return json.loads(dest.read_text(encoding="utf-8")).get("dokumentstatus") or {}


def _aslist(x) -> list:
    return [x] if isinstance(x, dict) else (x or [])


# "förslag till lag ..." (incl. "lag om ändring i"); older rows cut the object off after "förslag till"
LAW_RX = re.compile(r"förslag till (lag\b|lagar\b)|lag om ändring|antar regeringens förslag till[\s.]*$", re.I)


def chamber_decision(f: dict) -> str:
    """The chamber's decision on one proposal; '=utskottet' / '= utskottet' means it followed the committee."""
    k = (f.get("kammaren") or "").strip().lower()
    if k.replace(" ", "").startswith("=utskott"):
        k = (f.get("utskottet") or "").strip().lower()
    return k


# database-wide re-stamps of the closed-case status (not decision days); found by frequency over all props
MIGRATION_STAMPS = {"2017-10-17", "2017-10-18", "2017-10-19", "2017-10-20", "2019-05-22"}


def classify(ds: dict, date_introduced: str | None, rm: str) -> dict:
    """-> {adopted, n_law, n_adopted, decision_date, date_source} from dokforslag / dokaktivitet / dokuppgift.
    Adopted = chamber decision bifall / delvis bifall / antagen. Decision date: a beslut activity in dokaktivitet,
    else the systemdatum of the 'Ärendet är avslutat' status (set when the case is closed after the vote), kept
    only when it falls between introduction and the end of the following calendar year and is not a migration stamp (older props carry
    2014/2019 database-migration stamps instead)."""
    fs = _aslist((ds.get("dokforslag") or {}).get("forslag"))
    adopted = [f for f in fs if re.search(r"bifall|antag", chamber_decision(f))]
    laws = {(f.get("nummer"), f.get("lydelse")) for f in adopted
            if LAW_RX.search(" ".join(filter(None, [(f.get("lydelse") or "").strip(),
                                                     (f.get("lydelse2") or "").strip()])))}
    dd, src = None, None
    for a in _aslist((ds.get("dokaktivitet") or {}).get("aktivitet")):
        if re.search(r"beslut", a.get("namn") or "", re.I) and a.get("status") != "planerat":
            dd, src = (a.get("datum") or "")[:10] or dd, "dokaktivitet_beslut"
    if not dd:
        for u in _aslist((ds.get("dokuppgift") or {}).get("uppgift")):
            if u.get("kod") == "statustext" and "avslutat" in (u.get("text") or "").lower():
                d = (u.get("systemdatum") or "")[:10]
                lo, hi = date_introduced or rm_start(rm), f"{int(rm[:4]) + 2}-01-01"
                if d and lo <= d < hi and d not in MIGRATION_STAMPS and not d.startswith("2014-11"):
                    dd, src = d, "dokuppgift_avslutat"
    return {"adopted": bool(adopted), "n_law": len(laws), "n_adopted": len(adopted), "decision_date": dd,
            "date_source": src}


FIRST_RM = "2002/03"  # the listing has decision lines from 2002/03 on (2001/02 only partly)


def is_annex(dok: str) -> bool:
    """Budget-prop annexes (utgiftsområden, bilagor) are separate documents GQ031d12 etc. sharing the main
    prop's beteckning; their proposals sit in the main prop's dokforslag."""
    return bool(re.fullmatch(r"[A-Za-z0-9]{2}\d+[dD]\d+", dok or ""))


def main():
    D.mkdir(parents=True, exist_ok=True)
    # 1. SFS listing -> laws_se_sfs.csv (reference only; the listing mostly holds statutes still in force)
    sfs_laws, sfs_tot = [], {}
    for y in YEARS:
        docs = listing("sfs", str(y))
        sfs_tot[y] = len(docs)
        for d in docs:
            title = (d.get("titel") or "").strip()
            if not is_law(title):
                continue
            amending = bool(re.search(r"om ändring i|om ändring av", title, re.I))
            is_budget = bool(re.search(r"statens budget|budgetpropositionen", title, re.I))
            is_rat = bool(re.search(r"godkännande av|med anledning av .*(konvention|avtal|överenskommelse)",
                                    title, re.I))
            dok = d.get("dok_id") or d.get("id")
            sfs_laws.append({
                "country": "SE", "year": y, "date": (d.get("datum") or "")[:10] or None,
                "instrument_type": "budget_law" if is_budget else ("ratification" if is_rat else "law"),
                "origin": "government", "title": title, "length_words": None, "cap_topic": None,
                "is_budget": is_budget, "is_ratification": is_rat, "source": "riksdagen_sfs",
                "source_id": f"{dok}#amend" if amending else dok,
                "source_url": f"https://data.riksdagen.se/dokument/{dok}.html",
            })
    sfs_df = pd.DataFrame(sfs_laws, columns=LAWS_COLUMNS)
    write_csv(sfs_df, INTER / "laws_se_sfs.csv")
    pd.DataFrame(sorted(sfs_tot.items()), columns=["year", "sfs_listed"]).to_csv(D / "sfs_listing_totals.csv",
                                                                                  index=False)

    # 2. props -> bills, and adopted props with legislative content -> laws_se.csv
    bills, laws, cands = [], [], []
    for rm in riksmoten():
        for d in listing("prop", rm):
            title = (d.get("titel") or "").strip()
            itype = prop_instrument(title)
            dok = d.get("dok_id")
            outcome = prop_outcome(d, rm)
            bills.append({
                "country": "SE", "bill_id": f"prop {rm}:{d.get('beteckning')}", "title": title,
                "year_introduced": int((d.get("datum") or rm)[:4]), "origin": "government",
                "outcome": outcome, "date_introduced": (d.get("datum") or "")[:10] or None,
                "date_final": None, "instrument_type": itype if itype == "budget_law" else "law",
                "source": "riksdagen_prop", "rm": rm, "dok_id": dok, "organ": d.get("organ"),
                "subtyp": d.get("subtyp"),
            })
            # candidates: every prop (not skrivelse, not a budget annex) from FIRST_RM on that the listing
            # marks adopted or leaves without a decision line (main budget props, some others); the per-prop
            # dokumentstatus decides adoption and law content
            if (rm >= FIRST_RM and rm not in CURRENT_RM and (d.get("subtyp") or "prop") != "skr"
                    and not is_annex(dok) and outcome in ("enacted", None)):
                cands.append((rm, d, itype, outcome))
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS + ["rm", "dok_id", "organ", "subtyp"]).drop_duplicates("dok_id")
    write_csv(bills_df, INTER / "bills_se.csv")
    # classify candidates from per-prop dokumentstatus (serial, cached)
    seen, todo = set(), []
    for c in cands:
        if c[1].get("dok_id") and c[1]["dok_id"] not in seen:
            seen.add(c[1]["dok_id"])
            todo.append(c)
    log.info("se: classifying %d props from dokumentstatus (%d cached)", len(todo),
             sum((DS / f"{c[1]['dok_id']}.json").exists() for c in todo))
    n_fail, n_adopted = 0, 0
    for i, (rm, d, itype, outcome) in enumerate(todo, 1):
        dok = d.get("dok_id")
        intro = (d.get("datum") or "")[:10] or None
        if i % 250 == 0:
            log.info("se: dokumentstatus %d/%d", i, len(todo))
        try:
            k = classify(dokumentstatus(dok), intro, rm)
        except Exception as e:  # noqa: BLE001
            n_fail += 1
            log.warning("se: %s", e)
            continue
        adopted = k["adopted"] or outcome == "enacted"
        n_adopted += adopted
        if not adopted or not (k["n_law"] or itype == "budget_law"):
            continue
        date = k["decision_date"] or rm_start(rm)
        laws.append({
            "country": "SE", "year": int(date[:4]), "date": date, "instrument_type": itype, "origin": "government",
            "title": (d.get("titel") or "").strip(), "length_words": None, "cap_topic": None,
            "is_budget": itype == "budget_law", "is_ratification": itype == "ratification",
            "source": "riksdagen_prop_dokumentstatus", "source_id": dok,
            "source_url": f"https://data.riksdagen.se/dokumentstatus/{dok}.json", "rm": rm,
            "beteckning": d.get("beteckning"), "date_introduced": intro, "listing_outcome": outcome,
            "n_law_proposals": k["n_law"], "n_adopted_proposals": k["n_adopted"],
            "date_source": k["date_source"] or "rm_start",
        })
    if n_fail:
        log.warning("se: %d dokumentstatus fetches failed (props skipped)", n_fail)
    log.info("se: %d candidate props, %d adopted, %d with >=1 adopted law (or budget)", len(todo), n_adopted,
             len(laws))
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["rm", "beteckning", "date_introduced", "listing_outcome",
                                                      "n_law_proposals", "n_adopted_proposals", "date_source"]
                           ).drop_duplicates("source_id")
    write_csv(laws_df, INTER / "laws_se.csv")

    # 3. counts aggregated from the adopted-prop rows
    if len(laws_df):
        c = laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
        c["country"], c["source"], c["source_url"] = ("SE", "riksdagen_prop_dokumentstatus",
                                                     "https://data.riksdagen.se/dokumentstatus/")
    else:
        c = pd.DataFrame(columns=COUNTS_COLUMNS)
    write_csv(c[COUNTS_COLUMNS], INTER / "counts_se.csv")

    # 4. per-riksmöte comparison: adopted props with lag vs SFS-listed laws of the same start year
    sfs_by_year = sfs_df.groupby("year").size() if len(sfs_df) else pd.Series(dtype=int)
    enacted = bills_df[bills_df.outcome == "enacted"].groupby("rm").size()
    for rm in riksmoten():
        n_laws = int((laws_df.rm == rm).sum())
        log.info("se %s: %d props adopted (listing), %d law props -> laws_se; SFS-listed laws %s: %s", rm,
                 int(enacted.get(rm, 0)), n_laws, rm[:4], int(sfs_by_year.get(int(rm[:4]), 0)))
    log.info("se: %d laws (adopted props with a law), %d SFS reference rows, %d props/skr", len(laws_df),
             len(sfs_df), len(bills_df))


if __name__ == "__main__":
    main()
