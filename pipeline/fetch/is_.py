"""Iceland: Althingi XML (www.althingi.is/altext/xml, no key). Module is is_.py because `is` is a keyword.
- Sessions: /loggjafarthing/ -> session number, period, opening and closing dates (115 = 1991-92 onward: the
  first unicameral session; 113-114 list each bill once per chamber and carry no staðamáls, so are not used).
  Laws are kept for calendar years 1992-2025 (1992 is the first full year; session 115 opened 1 Oct 1991).
- Items: /thingmalalisti/?lthing=N, keep málstegund 'l' (frumvarp til laga = bill).
- Per bill: /thingmalalisti/thingmal/?lthing=N&malnr=M -> staðamáls (outcome) and the documents
  (first skjalategund: stjórnarfrumvarp = government; þingmannafrumvarp / nefndarfrumvarp = parliament);
  the útbýting date of the final "lög ..." document is used as the enactment date, else the session close.
Fetched strictly serially (0.2 s pause after each fresh call) with 429-aware backoff (Retry-After if sent,
else 2, 4, 8 ... s); every response is cached under raw/is/ and reused, except the current sessions.
Origin: any stjórnarfrumvarp document -> government; other bill documents (þingmannafrumvarp,
nefndarfrumvarp, ...) -> parliament; no bill document -> unknown. fjárlög / fjáraukalög -> budget_law."""
from __future__ import annotations

import datetime as dt
import email.utils
import re
import time

import pandas as pd
import requests
from lxml import etree

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, log, manifest_add, session, write_csv

D = RAW / "is"
BASE = "https://www.althingi.is/altext/xml"
FIRST_SESSION = 115
LAW_YEARS = (1992, 2025)
SLEEP = 0.2
_SESS: requests.Session | None = None
MIN_INTERVAL = 0.0   # s between requests (pacing; the API throttles bursts)
_LAST = [0.0]


def polite_get(url: str, dest=None, *, params: dict | None = None, retries: int = 8, timeout: int = 60,
               record: bool = True, force: bool = False) -> bytes:
    """Serial, 429-aware GET: cached at dest if given; on 429/5xx/network error waits Retry-After when the
    server sends it, else 2, 4, 8, ... s. 400/401/403/404 are not retried."""
    if dest is not None and dest.exists() and not force:
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


def _xml(url: str, dest, **kw) -> etree._Element | None:
    fetched = kw.get("force") or not dest.exists()
    try:
        raw = polite_get(url, dest, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("is: %s failed: %s", url, e)
        return None
    if fetched:
        time.sleep(SLEEP)
    try:
        return etree.fromstring(raw)
    except etree.XMLSyntaxError:
        log.warning("is: %s not XML (%d bytes)", url, len(raw))
        dest.unlink(missing_ok=True)
        return None


def _d(s: str | None) -> str | None:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def sessions() -> list[dict]:
    root = _xml(f"{BASE}/loggjafarthing/", D / "loggjafarthing.xml", force=True)
    out = []
    if root is None:
        return out
    for th in root.iter("þing"):
        n = int(th.get("númer"))
        if n < FIRST_SESSION:
            continue
        out.append({"lthing": n, "period": th.findtext("tímabil"), "start": _d(th.findtext("þingsetning")),
                    "end": _d(th.findtext("þinglok"))})
    return out


def bills_in_session(lthing: int, refetch: bool) -> list[dict]:
    root = _xml(f"{BASE}/thingmalalisti/", D / "lists" / f"thingmalalisti_{lthing}.xml", params={"lthing": lthing},
                force=refetch)
    out = []
    if root is None:
        return out
    for m in root.iter("mál"):
        mt = m.find("málstegund")
        if mt is None or mt.get("málstegund") != "l":
            continue
        out.append({"lthing": lthing, "malnr": int(m.get("málsnúmer")), "title": (m.findtext("málsheiti") or "").strip(),
                    "subtitle": (m.findtext("efnisgreining") or "").strip()})
    return out


def bill_detail(lthing: int, malnr: int, refetch: bool) -> dict:
    dest = D / "thingmal" / str(lthing) / f"{malnr}.xml"
    root = _xml(f"{BASE}/thingmalalisti/thingmal/", dest, params={"lthing": lthing, "malnr": malnr},
                force=refetch)
    out = {"status": None, "first_doc_type": None, "bill_doc_types": [], "law_date": None, "first_date": None, "n_docs": 0}
    if root is None:
        return out
    out["status"] = (root.findtext(".//staðamáls") or "").strip()
    docs = []
    for sk in root.iter("þingskjal"):
        docs.append({"n": int(sk.get("skjalsnúmer") or 0), "type": (sk.findtext("skjalategund") or "").strip().lower(),
                     "date": (sk.findtext("útbýting") or "")[:10]})
    docs.sort(key=lambda d: d["n"])
    out["n_docs"] = len(docs)
    out["bill_doc_types"] = [d["type"] for d in docs if "frumvarp" in d["type"]]
    if docs:
        out["first_doc_type"] = docs[0]["type"]
        out["first_date"] = docs[0]["date"] or None
        law_docs = [d for d in docs if d["type"].startswith("lög")]
        if law_docs:
            out["law_date"] = law_docs[-1]["date"] or None
    return out


def map_outcome(status: str, current: bool) -> str:
    s = (status or "").lower()
    if s.startswith("samþykkt sem lög"):
        return "enacted"
    if s.startswith("ekki útrætt"):
        return "lapsed"
    if s.startswith("fellt") or s.startswith("felld"):
        return "defeated"
    if "kallað aftur" in s or "tekið aftur" in s:
        return "withdrawn"
    if "vísað til ríkisstjórnar" in s:
        return "lapsed"
    if not s or "í nefnd" in s or "bíður" in s or "umræð" in s:
        return "pending" if current else "lapsed"
    return "pending" if current else "lapsed"


def map_origin(bill_doc_types: list[str], first_doc_type: str | None) -> str:
    types = bill_doc_types or ([first_doc_type] if first_doc_type else [])
    if not types:
        return "unknown"
    if any(t.startswith("stjórnarfrumvarp") for t in types):
        return "government"
    return "parliament"


def main():
    sess = sessions()
    if not sess:
        log.error("is: session list unavailable, nothing to do")
        return
    latest = max(s["lthing"] for s in sess)
    recent = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    bills, laws, unknown_status = [], [], {}
    for s in sess:
        lthing = s["lthing"]
        current = lthing >= latest - 1 and (s["end"] is None or s["end"] >= recent)
        items = bills_in_session(lthing, refetch=current)
        n_en = 0
        for it in items:
            try:
                det = bill_detail(lthing, it["malnr"], refetch=current)
            except Exception as e:  # noqa: BLE001
                log.warning("is: %d/%d detail failed: %s", lthing, it["malnr"], e)
                det = {"status": None, "first_doc_type": None, "bill_doc_types": [], "law_date": None,
                       "first_date": None, "n_docs": 0}
            outcome = map_outcome(det["status"], current)
            origin = map_origin(det["bill_doc_types"], det["first_doc_type"])
            if outcome not in ("enacted", "lapsed", "defeated", "withdrawn", "pending"):
                outcome = "pending"
            key = f'{(det["status"] or "<none>")[:50]} -> {outcome}'
            unknown_status[key] = unknown_status.get(key, 0) + 1
            title = it["title"]
            is_budget = bool(re.match(r"^fjárlög\b", title, re.I)) or bool(re.match(r"^fjáraukalög\b", title, re.I))
            is_rat = bool(re.search(r"fullgild|samning[sa]? (milli|við)|alþjóðasamning|fríverslunarsamning", title, re.I))
            itype = "budget_law" if is_budget else "constitutional_law" if re.match(r"^stjórnarskipunarlög|^stjórnarskrá", title, re.I) else "law"
            year_intro = (int(det["first_date"][:4]) if det["first_date"] else
                          int(s["start"][:4]) if s["start"] else int(re.findall(r"\d{4}", s["period"] or "0000")[0]))
            date_final = det["law_date"] if outcome == "enacted" else None
            if outcome == "enacted" and not date_final:
                date_final = s["end"] or f"{(s['period'] or str(year_intro))[-4:]}-06-30"
            bills.append({
                "country": "IS", "bill_id": f"{lthing}/{it['malnr']}", "title": title, "year_introduced": year_intro,
                "origin": origin, "outcome": outcome, "date_introduced": det["first_date"], "date_final": date_final,
                "instrument_type": itype, "source": "althingi_xml",
            })
            if outcome == "enacted":
                n_en += 1
                laws.append({
                    "country": "IS", "year": int(date_final[:4]), "date": date_final,
                    "instrument_type": "ratification" if (is_rat and not is_budget) else itype, "origin": origin,
                    "title": title + (f" ({it['subtitle']})" if it["subtitle"] else ""), "length_words": None,
                    "cap_topic": None, "is_budget": is_budget, "is_ratification": is_rat, "source": "althingi_xml",
                    "source_id": f"{lthing}/{it['malnr']}",
                    "source_url": f"https://www.althingi.is/thingstorf/thingmalalistar-eftir-thingum/ferill/{lthing}/{it['malnr']}/",
                })
        log.info("is session %d (%s): %d bills, %d enacted", lthing, s["period"], len(items), n_en)
    if unknown_status:
        log.info("is: status -> outcome map: %s", dict(sorted(unknown_status.items(), key=lambda x: -x[1])[:15]))
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS)
    write_csv(bills_df, INTER / "bills_is.csv")
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS)
    laws_df = laws_df[laws_df.year.between(*LAW_YEARS)].sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_is.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="IS", source="althingi_xml", source_url=f"{BASE}/thingmalalisti/"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_is.csv")
    log.info("is: %d bills, %d enacted laws; outcomes %s; origin %s", len(bills_df), len(laws_df),
             bills_df.outcome.value_counts().to_dict(), laws_df.origin.value_counts().to_dict())


if __name__ == "__main__":
    main()
