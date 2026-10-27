"""Estonia: Riigikogu open API (api.riigikogu.ee, OpenAPI at /v3/api-docs). No key, but HTTP 429 after a few
rapid calls: 5 s between uncached calls, every response cached under raw/ee/.
/api/volumes/drafts?membership=N&draftTypeCode=SE (law drafts, memberships IX 1999- to XV 2023-), paged 1000 at
a time. The list has no initiator, so origin comes from a second pass filtered by initiatorUuid (Vabariigi
Valitsus -> government; the few other classifier initiators -> other; everything else -> parliament).
activeDraftStage/Status -> outcome; enacted drafts -> laws_ee.csv, all drafts -> bills_ee.csv.
Law date = activeDraftStatusDate (usually publication in Riigi Teataja, 2007 onward); where the list has no status
date (all pre-2007 drafts) the draft detail is fetched (2 s gap, cached) and its 'accepted' adoption date used.
Memberships VII (Oct 1992-95) and VIII (1995-99) list no status dates at all, so every enacted VII/VIII draft needs a
detail call; laws_ee.csv starts in FIRST_YEAR = 1992. 1992 is partial by construction: the VII Riigikogu first sat on
5 Oct 1992 and the Supreme Council's (Ülemnõukogu) Jan-Sep 1992 laws are not in the API.
VII and VIII are paged 25 at a time because a record the API answers 404 for kills every page containing it; a failed
page is re-read as five pages of 5 so only the bad record(s) are lost (logged)."""
from __future__ import annotations

import time

import pandas as pd

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get_json, log, write_csv

API = "https://api.riigikogu.ee/api"
D = RAW / "ee"
MEMBERSHIPS = range(7, 17)          # VII (1992-95) .. XV (2023-); XVI tried, skipped if empty
SMALL_PAGE = {7, 8}                 # memberships read 25 per page (bad records, see above)
FIRST_YEAR = 1992                   # laws adopted before this year are dropped
PAGE = 1000
SLEEP = 5.0
GOV_UUID = "65e1db80-49f1-4c5b-b1b6-539b7efd199f"           # Vabariigi Valitsus
OTHER_INITIATORS = {                                         # non-parliament, non-government classifiers
    "cdde124d-27c4-4398-b268-5c9e20d34d7f": "Riigikohtu esimees",
    "271f9655-536c-4ef8-ba5d-db45b5ec4dab": "Riigikantselei",
    "4940c075-0351-bd62-0370-ac85391ef1f8": "Finantsinspektsioon",
}
STAGE_OUTCOME = {
    "VASTU_VOETUD": "enacted",
    "TAGASI_LYKATUD": "defeated",
    "TAGASI_VOETUD": "withdrawn",
    "TAGASI_VOETUD_TAISKOGUL_MENETLEMATA": "withdrawn",
    "VALJA_LANGENUD_KOOSEISU_LOPPEMISEGA": "lapsed",      # dropped when the membership ended
    "YHENDATUD": "lapsed",                                 # merged into another draft
    "MENETLUSEST_VALJA_ARVATUD": "lapsed",
    "VALJA_LANGENUD": "lapsed",                            # dropped from proceedings
    "TAGASTATUD": "withdrawn",                             # returned to the initiator
}
DETAIL_SLEEP = 2.0                  # detail calls tolerated at 2 s (tested 17 Oct 2026); list calls stay at 5 s
_last_call = 0.0


def api(path: str, dest, gap: float = SLEEP, **params):
    """get_json with a gap between live calls (cached files return immediately)."""
    global _last_call
    if not dest.exists():
        wait = gap - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
    try:
        return get_json(f"{API}{path}", dest, params=params, retries=6, backoff=3.0)
    finally:
        _last_call = time.monotonic()


def drafts(tag: str, size: int = PAGE, skip_bad: bool = False, **filters) -> list[dict]:
    """All SE drafts matching filters, paged. skip_bad: a page that fails (membership VIII has a record the API
    answers 404 for, which kills every page containing it) is logged and skipped, so use a small size there."""
    out, page, pages = [], 0, None
    while True:
        try:
            j = api("/volumes/drafts", D / "drafts" / f"{tag}_p{page}.json", draftTypeCode="SE", lang="et",
                    page=page, size=size, **filters)
        except Exception as e:  # noqa: BLE001
            if not skip_bad or pages is None or page + 1 >= pages:
                raise
            log.warning("ee: %s page %d (size %d) failed (%s); re-reading it in pages of 5", tag, page, size, e)
            sub = size // 5 if size % 5 == 0 and size > 5 else None
            for k in range(5 if sub else 0):
                sp = page * 5 + k
                try:
                    jj = api("/volumes/drafts", D / "drafts" / f"{tag}_s5_p{sp}.json", draftTypeCode="SE", lang="et",
                             page=sp, size=5, **filters)
                    out.extend((jj.get("_embedded") or {}).get("content") or [])
                except Exception as e2:  # noqa: BLE001
                    log.warning("ee: %s records %d-%d skipped: %s", tag, sp * 5, sp * 5 + 4, e2)
            page += 1
            continue
        items = (j.get("_embedded") or {}).get("content") or []
        out.extend(items)
        pages = int((j.get("page") or {}).get("totalPages") or 1)
        if not items or page + 1 >= pages:
            break
        page += 1
    return out


def adoption_date(uuid: str) -> str | None:
    """Draft detail -> 'accepted' (adoption date). Only used where the list gives no status date (pre-2007)."""
    j = api(f"/volumes/drafts/{uuid}", D / "detail" / f"{uuid}.json", gap=DETAIL_SLEEP, lang="et")
    return (j.get("accepted") or "")[:10] or None


def main():
    gov, other, allrows = set(), {}, []
    for uuid, name in OTHER_INITIATORS.items():
        try:
            other.update({d["uuid"]: name for d in drafts(f"init_{uuid[:8]}", initiatorUuid=uuid)})
        except Exception as e:  # noqa: BLE001
            log.error("ee: initiator %s failed: %s", name, e)
    for m in MEMBERSHIPS:
        try:
            rows = (drafts(f"m{m:02d}s25", size=25, skip_bad=True, membership=m) if m in SMALL_PAGE
                    else drafts(f"m{m:02d}", membership=m))
        except Exception as e:  # noqa: BLE001
            log.error("ee: membership %d failed: %s", m, e)
            continue
        if not rows:
            log.info("ee: membership %d empty, stopping", m)
            break
        try:
            gov.update(d["uuid"] for d in (
                drafts(f"m{m:02d}s25_gov", size=25, skip_bad=True, membership=m, initiatorUuid=GOV_UUID) if m in SMALL_PAGE
                else drafts(f"m{m:02d}_gov", membership=m, initiatorUuid=GOV_UUID)))
        except Exception as e:  # noqa: BLE001
            log.error("ee: government filter for membership %d failed (origin -> unknown): %s", m, e)
            for d in rows:
                d["_origin_unknown"] = True
        allrows.extend(rows)
        log.info("ee: membership %d: %d SE drafts (%d government)", m, len(rows), sum(d["uuid"] in gov for d in rows))

    current = max((d.get("membership") or 0) for d in allrows) if allrows else None
    bills, laws, unmapped, n_detail, no_date = [], [], {}, 0, 0
    for d in allrows:
        if d.get("draftTypeCode") != "SE":
            continue
        u = d["uuid"]
        origin = ("unknown" if d.get("_origin_unknown") else "government" if u in gov
                  else "other" if u in other else "parliament")
        stage, status = d.get("activeDraftStage") or "", d.get("activeDraftStatus") or ""
        sdate = (d.get("activeDraftStatusDate") or "")[:10] or None
        outcome = STAGE_OUTCOME.get(stage)
        if outcome == "enacted" and not sdate:
            try:
                sdate = adoption_date(u)
                n_detail += 1
                if n_detail % 100 == 0:
                    log.info("ee: %d adoption dates fetched from draft details", n_detail)
            except Exception as e:  # noqa: BLE001
                log.warning("ee: detail for %s failed: %s", u, e)
        if outcome is None:
            if status in ("AVALDATUD_RIIGITEATAJAS", "VASTU_VOETUD"):
                outcome = "enacted"
            elif d.get("proceedingStatus") != "PROCESSED" and d.get("membership") == current:
                outcome = "pending"
            else:
                unmapped[(stage, status)] = unmapped.get((stage, status), 0) + 1
                outcome = "lapsed"
        title = d.get("title") or ""
        tl = title.lower()
        is_rat = "ratifitseerimise" in tl or "ratifitseerimis" in tl
        is_budget = "riigieelarve" in tl and not is_rat
        itype = "ratification" if is_rat else "budget_law" if is_budget else "law"
        intro = (d.get("initiated") or "")[:10] or None
        year_intro = int(intro[:4]) if intro else (int(sdate[:4]) if sdate else None)
        url = f"https://www.riigikogu.ee/tegevus/eelnoud/eelnou/{u}"
        bills.append({
            "country": "EE", "bill_id": u, "title": title, "year_introduced": year_intro, "origin": origin,
            "outcome": outcome, "date_introduced": intro, "date_final": sdate if outcome != "pending" else None,
            "instrument_type": itype, "source": "riigikogu_api", "membership": d.get("membership"),
            "mark": f"{d.get('mark')} SE", "stage": stage, "status": status,
        })
        if outcome == "enacted" and not sdate:
            no_date += 1
        if outcome == "enacted" and sdate and int(sdate[:4]) >= FIRST_YEAR:
            laws.append({
                "country": "EE", "year": int(sdate[:4]), "date": sdate, "instrument_type": itype, "origin": origin,
                "title": title, "length_words": None, "cap_topic": None, "is_budget": is_budget,
                "is_ratification": is_rat, "source": "riigikogu_api", "source_id": f"{d.get('mark')} SE (RK {d.get('membership')})",
                "source_url": url,
            })
    if no_date:
        log.warning("ee: %d enacted drafts without any adoption date (not in laws_ee.csv)", no_date)
    if unmapped:
        log.warning("ee: unmapped stage/status combinations (-> lapsed): %s", unmapped)
    if not bills:
        log.error("ee: nothing fetched, no files written")
        return
    bills_df = pd.DataFrame(bills).drop_duplicates("bill_id").sort_values(["date_introduced", "mark"])
    write_csv(bills_df[BILLS_COLUMNS + ["membership", "mark", "stage", "status"]], INTER / "bills_ee.csv")
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).drop_duplicates("source_url").sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_ee.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="EE", source="riigikogu_api", source_url=f"{API}/volumes/drafts"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_ee.csv")
    log.info("ee: %d laws, %d bills; outcomes %s", len(laws_df), len(bills_df), bills_df.outcome.value_counts().to_dict())


if __name__ == "__main__":
    main()
