"""Luxembourg: Legilux SPARQL (JOLux ontology) -> laws_lu.csv, counts_lu.csv, 1950-2025.

Source: https://data.legilux.public.lu/sparqlendpoint, one query per year for documents with
jolux:typeDocument = resource-type/LOI that are jolux:Act (consolidations are typed LOI too and are
excluded) and jolux:dateDocument (date of the law) in the year. Titles are the French expression title.

Origin: Legilux links every law to its parliamentary file via jolux:draft; the draft URI encodes the
kind of file: .../pl/... = projet de loi (government), .../ppl/... = proposition de loi (parliament),
.../pc/... and .../ppc/... = projet / proposition de révision constitutionnelle (government / parliament,
instrument_type constitutional_law). Laws without a draft link get origin unknown. The Chamber open-data
dataset "112" (chd.lu/en/open-data) was not needed and its page lists no such download.

Instrument types: a title starting "Loi du <date> concernant le budget des recettes et des dépenses de l'État" -> budget_law
(laws merely amending a budget law and the provisional-twelfths laws of late-budget years stay plain law); "portant approbation ..." -> ratification;
constitutional revisions -> constitutional_law; everything else -> law."""
from __future__ import annotations

import json
import re
import time

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

D = RAW / "lu"
EP = "https://data.legilux.public.lu/sparqlendpoint"
YEARS = range(1950, 2026)
PREFIX = "PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>\n"
LOI = "<http://data.legilux.public.lu/resource/authority/resource-type/LOI>"

QUERY = PREFIX + """SELECT ?d ?date ?pub ?draft ?title WHERE {
  ?d jolux:typeDocument %s ; a jolux:Act ; jolux:dateDocument ?date .
  FILTER(YEAR(?date) = %d)
  OPTIONAL { ?d jolux:publicationDate ?pub }
  OPTIONAL { ?d jolux:draft ?draft }
  OPTIONAL { ?d jolux:isRealizedBy ?e . ?e jolux:title ?title .
             ?e jolux:language <http://publications.europa.eu/resource/authority/language/FRA> }
}"""

RE_BUDGET = re.compile(r"^loi du \d{1,2}(er)? \w+ \d{4} concernant le budget des recettes et des d[ée]penses de l.[ée]tat", re.I)
RE_RATIF = re.compile(r"portant approbation", re.I)
RE_CONST = re.compile(r"r[ée]vision de (l.article|la constitution)|portant modification de la constitution", re.I)


def sparql(year: int) -> list[dict]:
    dest = D / f"loi_{year}.json"
    cached = dest.exists()
    raw = get(EP, dest, params={"query": QUERY % (LOI, year)}, headers={"Accept": "application/sparql-results+json"},
              timeout=180)
    if not cached:
        time.sleep(0.3)
    return json.loads(raw.decode("utf-8"))["results"]["bindings"]


def origin_from_draft(uri: str | None) -> tuple[str, bool]:
    """-> (origin, is_constitutional) from the draft URI kind segment (pl / ppl / pc / ppc)."""
    if not uri:
        return "unknown", False
    kinds = [s.lower() for s in uri.split("/") if s.lower() in ("pl", "ppl", "pc", "ppc")]
    if not kinds:
        return "unknown", False
    k = kinds[-1]
    return ("government" if k in ("pl", "pc") else "parliament"), k in ("pc", "ppc")


def main():
    laws = []
    for year in YEARS:
        try:
            rows = sparql(year)
        except Exception as e:  # noqa: BLE001
            log.warning("lu %d: query failed: %s", year, e)
            continue
        seen = {}
        for b in rows:
            uri = b["d"]["value"]
            if uri in seen:
                continue
            title = re.sub(r"\s+", " ", b.get("title", {}).get("value", "").replace("\\n", " ")).strip()
            origin, is_const = origin_from_draft(b.get("draft", {}).get("value"))
            if RE_BUDGET.search(title):
                itype = "budget_law"
            elif RE_RATIF.search(title):
                itype = "ratification"
            elif is_const or RE_CONST.search(title):
                itype = "constitutional_law"
            else:
                itype = "law"
            date = b["date"]["value"][:10]
            seen[uri] = {
                "country": "LU", "year": int(date[:4]), "date": date, "instrument_type": itype, "origin": origin,
                "title": title, "length_words": None, "cap_topic": None, "is_budget": itype == "budget_law",
                "is_ratification": itype == "ratification", "source": "legilux_sparql", "source_id": uri,
                "source_url": uri,
            }
        laws.extend(seen.values())
        log.info("lu %d: %d laws (origin known %d)", year, len(seen),
                 sum(r["origin"] != "unknown" for r in seen.values()))
    laws_df = pd.DataFrame(laws, columns=LAWS_COLUMNS).sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_lu.csv")
    counts = (laws_df.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="LU", source="legilux_sparql", source_url=EP))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_lu.csv")


if __name__ == "__main__":
    main()
