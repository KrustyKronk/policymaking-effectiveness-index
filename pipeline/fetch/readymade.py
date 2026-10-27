"""Phase A: ready-made datasets (REPDEM, ParlGov, CAP, Dataverse files, OBS, WGI, POLCON, DPI, SGI, iREG).
Each item is independent; failures are logged and summarised, not fatal."""
from __future__ import annotations

import json
import re

from pipeline.common import RAW, dataverse_download, dataverse_files, get, get_json, log

CAP_BASE = "https://minio.la.utexas.edu/compagendas/datasetfiles/"
CAP_FILES = {  # (country, kind): filename on the CAP file server
    ("ES", "laws"): "Spain_Laws19802018_19.1.csv",
    ("ES", "bills_parl"): "Spain_ParliamentaryBills19822017_19.2.csv",
    ("ES", "bills_gov"): "ExecutiveBills19772018_19.2.csv",
    ("UK", "acts"): "uk_actsofparliament_v1_2_1.csv",
    ("UK", "sis"): "uk_statutoryinstruments_v2_2.csv",
    ("FR", "laws"): "lois_79_13_short_7.csv",
    ("FR", "bills_gov"): "bills_5.csv",
    ("DE", "laws"): "laws_1976-2005_website-release_2.5.csv",
    ("DE", "bills"): "bills_1976-2005_website-release_2.5.csv",
    ("IT", "laws"): "laws_italy_web.csv",
    ("IT", "dlgs"): "dlgs_italy_web_1.csv",
    ("NL", "bills"): "2LAW10062020.csv",
    ("BE", "bills"): "CAP_Belgium_Bills_1988-2022.csv",
    ("DK", "bills"): "Love_01092019_-_Sheet1.csv",
    ("IE", "bills"): "bills_for_cap.csv",
}
CAP_PAGES = {"ES": "spain", "UK": "united_kingdom", "FR": "france", "DE": "germany", "IT": "italy",
             "NL": "netherlands", "BE": "belgium", "DK": "denmark", "IE": "ireland"}

results: dict[str, str] = {}


def step(name):
    def deco(fn):
        def wrapper():
            try:
                fn()
                results[name] = "ok"
            except Exception as e:  # noqa: BLE001
                log.error("%s failed: %s", name, e)
                results[name] = f"FAILED: {e}"
        wrapper.__name__ = name
        return wrapper
    return deco


def links_in(html: str, pattern: str) -> list[str]:
    rx = re.compile(r'href="([^"]*(?:' + pattern + r')[^"]*)"', flags=re.I)
    return sorted({m.group(1) for m in rx.finditer(html)})


@step("repdem")
def fetch_repdem():
    d = RAW / "repdem"
    page = get("https://repdem.org/index.php/current-dataset/").decode("utf-8", "replace")
    links = links_in(page, r"download/")
    (d).mkdir(parents=True, exist_ok=True)
    (d / "links.txt").write_text("\n".join(links), encoding="utf-8")
    wanted = [l for l in links if re.search(r"(basic|paged).*\.(csv|pdf)$", l, re.I)]
    if not any("repdem-basic" in l and l.endswith(".csv") for l in wanted):
        wanted.append("https://repdem.org/index.php/download/113/governments-dataset-basic/5249/repdem-basic-3.csv")
    for url in wanted:
        if not url.startswith("http"):
            url = "https://repdem.org" + url
        get(url, d / url.rsplit("/", 1)[-1])
    log.info("repdem: %d files", len(wanted))


@step("parlgov")
def fetch_parlgov():
    d = RAW / "parlgov"
    for f in dataverse_files("10.7910/DVN/2VZ5ZC"):
        if f["filename"] in ("view_cabinet.tab", "view_election.tab", "view_party.tab", "codebook.md", "readme.txt"):
            dataverse_download(f["id"], d / f["filename"], original=False)


@step("cap")
def fetch_cap():
    d = RAW / "cap"
    missing = []
    for (cc, kind), fname in CAP_FILES.items():
        try:
            get(CAP_BASE + fname, d / f"{cc}_{kind}__{fname}")
        except Exception as e:  # noqa: BLE001
            log.warning("CAP %s %s not found (%s)", cc, kind, e)
            missing.append((cc, kind))
    # help future-me: record the links the country pages currently expose
    found = {}
    for cc, slug in CAP_PAGES.items():
        try:
            page = get(f"https://www.comparativeagendas.net/project/{slug}/datasets").decode("utf-8", "replace")
            found[cc] = links_in(page, r"minio\.la\.utexas\.edu")
        except Exception as e:  # noqa: BLE001
            found[cc] = [f"page fetch failed: {e}"]
    (d / "country_page_links.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    if missing:
        raise RuntimeError(f"missing CAP files: {missing}; see raw/cap/country_page_links.json")


@step("spain_dataverse")
def fetch_spain_dataverse():
    d = RAW / "spain_dataverse"
    for f in dataverse_files("10.7910/DVN/1VKJXZ"):
        dataverse_download(f["id"], d / f["filename"], original=True)


@step("parltext_pl")
def fetch_parltext():
    d = RAW / "parltext"
    files = dataverse_files("10.7910/DVN/6NQXHF")
    (d).mkdir(parents=True, exist_ok=True)
    (d / "files.json").write_text(json.dumps(files, indent=1), encoding="utf-8")
    for f in files:
        if re.search(r"(^|[_\-.])(pl|pol|poland)([_\-.]|$)", f["filename"], re.I) or "codebook" in f["filename"].lower():
            dataverse_download(f["id"], d / f["filename"], original=False)


@step("parllawspeech")
def fetch_pls():
    d = RAW / "pls"
    page = get("https://parllawspeech.org/data/").decode("utf-8", "replace")
    links = links_in(page, r"\.(rds|RDS|zip|csv)")
    d.mkdir(parents=True, exist_ok=True)
    (d / "links.txt").write_text("\n".join(links), encoding="utf-8")
    picked = [l for l in links if re.search(r"(austria|denmark|germany|spain|_at_|_dk_|_de_|_es_|AT|DK|DE|ES).*law", l, re.I)]
    for url in picked:
        get(url if url.startswith("http") else "https://parllawspeech.org" + url, d / url.rsplit("/", 1)[-1])
    log.info("pls: %d candidate links, %d picked", len(links), len(picked))


@step("obs")
def fetch_obs():
    get("https://internationalbudget.org/sites/default/files/2026-09/OBS_Full_Timeseries_2006_2025.xlsx",
        RAW / "obs" / "OBS_Full_Timeseries_2006_2025.xlsx")


@step("wgi")
def fetch_wgi():
    d = RAW / "wgi"
    for ind in ("GOV_WGI_GE.EST", "GOV_WGI_GE.SC"):
        get_json(f"https://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&per_page=20000&date=1996:2025&source=3",
                 d / f"{ind}.json")


@step("polcon")
def fetch_polcon():
    get("https://mgmt.wharton.upenn.edu/wp-content/uploads/2026/03/POLCON_2025_FINALPOSTED.xlsx",
        RAW / "polcon" / "POLCON_2025_FINALPOSTED.xlsx")


@step("dpi")
def fetch_dpi():
    d = RAW / "dpi"
    j = get_json("https://data.iadb.org/api/3/action/package_show?id=the-database-of-political-institutions-dpi-2023",
                 d / "package.json")
    res = j["result"].get("resources", [])
    picked = [r for r in res if re.search(r"(csv|xlsx|zip)", (r.get("format") or "") + (r.get("name") or "") + r.get("url", ""), re.I)] or res
    if not picked:
        raise RuntimeError(f"no downloadable resources among {[r.get('url') for r in res]}")
    for r in picked[:4]:
        name = (r.get("name") or r["url"].rsplit("/", 1)[-1]).replace("/", "_")
        ext = (r.get("format") or "").lower()
        if ext and not name.lower().endswith(ext):
            name += "." + ext
        get(r["url"], d / name)


@step("sgi")
def fetch_sgi():
    d = RAW / "sgi"
    page = get("https://www.sgi-network.org/2022/Downloads").decode("utf-8", "replace")
    links = links_in(page, r"\.(xlsx|xls|zip)")
    d.mkdir(parents=True, exist_ok=True)
    (d / "links.txt").write_text("\n".join(links), encoding="utf-8")
    picked = [l for l in links if re.search(r"(time|series|scores)", l, re.I)]
    if not picked:
        raise RuntimeError(f"no time-series/scores xlsx found among {len(links)} links")
    for url in picked:
        full = url if url.startswith("http") else "https://www.sgi-network.org/" + url.lstrip("/")
        get(full, d / url.rsplit("/", 1)[-1])


@step("ireg")
def fetch_ireg():
    get("https://sdmx.oecd.org/public/rest/data/OECD.GOV.GIP,DSD_GOV_REG@DF_GOV_REG_2025,/all?format=csvfilewithlabels",
        RAW / "ireg" / "ireg_2025.csv")


def main():
    for fn in (fetch_repdem, fetch_parlgov, fetch_cap, fetch_spain_dataverse, fetch_parltext, fetch_pls,
               fetch_obs, fetch_wgi, fetch_polcon, fetch_dpi, fetch_sgi, fetch_ireg):
        log.info("=== %s", fn.__name__)
        fn()
    log.info("readymade summary:\n" + "\n".join(f"  {k}: {v}" for k, v in results.items()))


if __name__ == "__main__":
    main()
