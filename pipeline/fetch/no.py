"""Norway: Stortinget open data (data.stortinget.no, no key).
- /eksport/saker?sesjonid=... (XML) for sessions 1986-87 .. 2025-2026 (ids before 1999 are 'YYYY-YY'): every case with type
  (lovsak / budsjett / alminneligsak), dokumentgruppe (proposisjon = government, representantforslag = member,
  innstillingssaker = committee) and status (behandlet / trukket / bortfalt / mottatt / til_behandling).
  A case is listed in every session it was active in; it is kept once, under its first session.
- /eksport/sak?sakid=N (XML) per lovsak for the saksgang timeline -> FREMMET (introduced) and LOVVEDT (law
  decision) dates. Fetched strictly serially (Stortinget returns 429 under parallel load), 429-aware backoff.
- Outcome: lovsak 'behandlet' is only an approximation of passage, so it is refined: behandlet AND (a LOVVEDT
  event or a law-decision reference 'Lovvedtak' / 'Besl. O.' in henvisning) -> enacted; behandlet without
  either -> defeated (mostly rejected member bills). trukket -> withdrawn; bortfalt -> lapsed; else pending.
- Backfill sessions (1986-87 .. 1998-99): the detail endpoint is rate-limited, so status and outcome come from
  the case list alone (henvisning 'besl. O.' = enacted) and the per-case detail is fetched only for enacted
  lovsak (to date the law decision); other old cases have no introduced/final dates.
- Laws are kept for calendar years 1987-2025: 1987 is the first full year covered (session 1986-87 opens Oct 1986).
  A sample of cases is cross-checked against /eksport/voteringer (votes only exist from ~2011-12).
- Budget cases (type budsjett) go only into bills_no.csv, as budget_law.
Outputs: bills_no.csv (lovsak + budsjett), laws_no.csv (enacted lovsak), counts_no.csv."""
from __future__ import annotations

import datetime as dt
import email.utils
import re
import time

import pandas as pd
import requests
from lxml import etree

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, log, manifest_add, session, write_csv

D = RAW / "no"
BASE = "https://data.stortinget.no/eksport"
NS = {"s": "http://data.stortinget.no"}
FIRST_SESSION_YEAR = 1986
DETAIL_ALL_FROM = 1999   # sessions from this year onward: detail for every lovsak; earlier: enacted only
SESSIONS = [f"{y}-{y + 1}" if y >= 1999 else f"{y}-{str(y + 1)[2:]}" for y in range(FIRST_SESSION_YEAR, 2026)]
LAW_YEARS = (FIRST_SESSION_YEAR + 1, 2025)
DETAIL_CAP = 8000       # max fresh per-case detail requests per run
TIME_BUDGET_S = 3 * 3600
VOTE_SAMPLE = 10        # lovsak cases checked against the voteringer endpoint (logged only)
DECISION_RE = re.compile(r"Lovvedtak|Besl\.\s*O\.|beslutning\.\s*O\.", re.I)
ORIGIN = {"proposisjon": "government", "representantforslag": "parliament", "innstillingssaker": "parliament"}
_SESS: requests.Session | None = None
MIN_INTERVAL = 0.25   # s between requests (pacing; the API throttles bursts)
_LAST = [0.0]


def polite_get(url: str, dest=None, *, params: dict | None = None, retries: int = 8, timeout: int = 60,
               record: bool = True, max_5xx: int | None = None) -> bytes:
    """Serial, 429-aware GET: cached at dest if given; on 429/5xx/network error waits Retry-After when the
    server sends it, else 2, 4, 8, ... s. 400/401/403/404 are not retried; with max_5xx, gives up after that
    many 5xx answers (some old cases return a persistent HTTP 500)."""
    n5xx = 0
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
            if r.status_code >= 500:
                n5xx += 1
                if max_5xx is not None and n5xx >= max_5xx:
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


def _t(e, name):
    return (e.findtext(f"s:{name}", namespaces=NS) or "").strip()


def cases_for_session(sid: str) -> list[dict]:
    xml = polite_get(f"{BASE}/saker", D / "saker" / f"saker_{sid}.xml", params={"sesjonid": sid})
    root = etree.fromstring(xml)
    out = []
    for sak in root.iterfind(".//s:saker_liste/s:sak", NS):
        out.append({
            "id": _t(sak, "id"), "type": _t(sak, "type"), "dokumentgruppe": _t(sak, "dokumentgruppe"),
            "status": _t(sak, "status"), "tittel": _t(sak, "tittel") or _t(sak, "korttittel"),
            "henvisning": _t(sak, "henvisning"), "behandlet_sesjon": _t(sak, "behandlet_sesjon_id"),
            "session": sid,
        })
    return out


def _parse_date(s: str) -> str | None:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    if not m or m.group(3) == "0001":
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def case_events(sak_id: str, state: dict, old: bool = False) -> dict | None:
    """{event id: first date} from the saksgang timeline; None if not available (cap reached or failure)."""
    dest = D / "sak" / f"sak_{sak_id}.xml"
    if not dest.exists():
        if state["left"] <= 0 or time.time() - state["t0"] > TIME_BUDGET_S:
            return None
        state["left"] -= 1
    try:
        root = etree.fromstring(polite_get(f"{BASE}/sak", dest, params={"sakid": sak_id},
                                             max_5xx=2 if old else None))
    except Exception as e:  # noqa: BLE001
        log.warning("no: detail %s failed: %s", sak_id, e)
        return None
    ev: dict[str, str] = {}
    for h in root.iterfind(".//s:saksgang_hendelse", NS):
        d = _parse_date(_t(h, "dato"))
        if d:
            ev.setdefault(_t(h, "id"), d)
    return ev


def sample_votes(cases: list[tuple[str, str]]) -> None:
    """Log whether the voteringer endpoint agrees with the enacted/defeated mapping for a few cases."""
    agree = checked = 0
    for sid, outcome in cases:
        try:
            xml = polite_get(f"{BASE}/voteringer", D / "voteringer" / f"vot_{sid}.xml", params={"sakid": sid})
            votes = etree.fromstring(xml).findall(".//s:sak_votering", NS)
        except Exception as e:  # noqa: BLE001
            log.warning("no: voteringer %s failed: %s", sid, e)
            continue
        if not votes:
            log.info("no: vote check sak %s (%s): no recorded votes", sid, outcome)
            continue
        vedtatt = [_t(v, "vedtatt") for v in votes]
        any_passed = "true" in vedtatt
        ok = any_passed == (outcome == "enacted")
        checked += 1
        agree += ok
        log.info("no: vote check sak %s mapped %s: %d votes, vedtatt=%s -> %s", sid, outcome, len(votes),
                 vedtatt[-4:], "agree" if ok else "DISAGREE")
    log.info("no: voteringer check: %d/%d cases with votes agree with the mapping", agree, checked)


def main():
    cases = []
    for sid in SESSIONS:
        try:
            rows = cases_for_session(sid)
        except Exception as e:  # noqa: BLE001
            log.warning("no: session %s failed: %s", sid, e)
            continue
        lov = [r for r in rows if r["type"] == "lovsak"]
        log.info("no %s: %d cases, %d lovsak (%d proposisjon, %d representantforslag), %d budsjett", sid, len(rows),
                 len(lov), sum(r["dokumentgruppe"] == "proposisjon" for r in lov),
                 sum(r["dokumentgruppe"] == "representantforslag" for r in lov),
                 sum(r["type"] == "budsjett" for r in rows))
        cases.extend(rows)
    if not cases:
        log.error("no: no sessions fetched, nothing written")
        return
    df = pd.DataFrame(cases).drop_duplicates("id", keep="first")
    df = df[df.type.isin(["lovsak", "budsjett"])].copy()
    df.to_csv(D / "cases_lov_budsjett.csv", index=False)

    state = {"left": DETAIL_CAP, "t0": time.time()}
    lov = df[df.type == "lovsak"]
    old = lov.session.str[:4].astype(int) < DETAIL_ALL_FROM
    old_enacted = old & (lov.status == "behandlet") & lov.henvisning.fillna("").str.contains(DECISION_RE)
    cached = lov.id.map(lambda i: (D / "sak" / f"sak_{i}.xml").exists())   # cached details are always used
    lov_ids = lov.loc[~old | old_enacted | cached, "id"].tolist()
    log.info("no: detail for %d lovsak (%d old-session cases skipped: status from the case list)", len(lov_ids),
             int((old & ~old_enacted & ~cached).sum()))
    events: dict[str, dict | None] = {}
    old_ids = set(lov.loc[old, "id"])
    for i, sak_id in enumerate(lov_ids, 1):
        events[sak_id] = case_events(sak_id, state, old=sak_id in old_ids)
        if i % 250 == 0:
            log.info("no: details %d/%d (%.0fs)", i, len(lov_ids), time.time() - state["t0"])
    log.info("no: timelines for %d/%d lovsak cases", sum(v is not None for v in events.values()), len(lov_ids))

    bills, laws = [], []
    for r in df.itertuples(index=False):
        sess_start = int(r.session.split("-")[0])
        origin = ORIGIN.get(r.dokumentgruppe, "other")
        ev = events.get(r.id) or {}
        if r.status == "behandlet":
            if r.type == "budsjett":
                outcome = "enacted"
            else:
                outcome = "enacted" if ("LOVVEDT" in ev or DECISION_RE.search(r.henvisning)) else "defeated"
        elif r.status == "trukket":
            outcome = "withdrawn"
        elif r.status == "bortfalt":
            outcome = "lapsed"
        else:
            outcome = "pending"
        itype = "budget_law" if r.type == "budsjett" else "law"
        d_intro = ev.get("FREMMET") or ev.get("FREMSATT") or ev.get("REFO")
        d_final = ev.get("LOVVEDT") or ev.get("BEHL") or ev.get("BEHO") or ev.get("BEH") or None
        if outcome == "defeated" and not d_final:
            d_final = max((d for k, d in ev.items() if k not in ("LOVIKRAFT",)), default=None)
        bills.append({
            "country": "NO", "bill_id": r.id, "title": r.tittel, "year_introduced": int(d_intro[:4]) if d_intro else sess_start,
            "origin": origin, "outcome": outcome, "date_introduced": d_intro, "date_final": d_final,
            "instrument_type": itype, "source": "stortinget_api",
        })
        if r.type == "lovsak" and outcome == "enacted":
            date = d_final
            if not date:   # no timeline: mid-point of the session in which it was treated
                treated = r.behandlet_sesjon if re.match(r"\d{4}-\d{4}", r.behandlet_sesjon or "") else r.session
                date = f"{int(treated[:4]) + 1}-06-30"
                log.warning("no: sak %s has no decision date, using %s", r.id, date)
            is_rat = bool(re.search(r"samtykke til (ratifikasjon|godkjenn|inngåelse|tiltredelse)|ratifikasjon", r.tittel, re.I))
            laws.append({
                "country": "NO", "year": int(date[:4]), "date": date,
                "instrument_type": "ratification" if is_rat else "law", "origin": origin, "title": r.tittel,
                "length_words": None, "cap_topic": None, "is_budget": False, "is_ratification": is_rat,
                "source": "stortinget_api", "source_id": r.id,
                "source_url": f"https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/Sak/?p={r.id}",
            })
    bills_df = pd.DataFrame(bills, columns=BILLS_COLUMNS)
    write_csv(bills_df, INTER / "bills_no.csv")
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS)
    laws_df = laws_df[laws_df.year.between(*LAW_YEARS)].sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_no.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="NO", source="stortinget_api", source_url=f"{BASE}/saker"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_no.csv")
    log.info("no: %d bills, %d enacted law rows; outcomes %s", len(bills_df), len(laws_df),
             bills_df[bills_df.instrument_type == "law"].outcome.value_counts().to_dict())
    try:
        lb = bills_df[(bills_df.instrument_type == "law") & (bills_df.year_introduced >= 2012)]
        sample = (list(lb[lb.outcome == "enacted"].bill_id[:VOTE_SAMPLE // 2])
                  + list(lb[lb.outcome == "defeated"].bill_id[:VOTE_SAMPLE // 2]))
        outc = dict(zip(lb.bill_id, lb.outcome))
        sample_votes([(s, outc[s]) for s in sample])
    except Exception as e:  # noqa: BLE001
        log.warning("no: vote check skipped: %s", e)


if __name__ == "__main__":
    main()
