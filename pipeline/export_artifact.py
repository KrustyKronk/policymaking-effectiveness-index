"""Build the interactive explorer: data/*.csv + annotations -> artifact/pei-explorer.html.

The page re-scores the index in the browser (weights and penalties are sliders), so it gets the
inputs of each pillar rather than only the final scores. Default parameters must reproduce data/pei_country_year.csv.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re

import pandas as pd
import yaml

from pipeline.common import (COUNTRIES, DATA, ERAS, FY_START, LAWS_FROM, PANEL_A, ROOT, load_params, log,
                             scoring_from)

ART = ROOT / "artifact"


def num(v, nd=3):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), nd)


def sources_table() -> dict:
    """Per-country source notes: README v1 table, overridden where v2 extended a series back in time."""
    txt = (ROOT / "README.md").read_text()
    sec = txt.split("## Sources actually used", 1)[1].split("\n## ", 1)[0]
    out = {}
    for line in sec.splitlines():
        m = re.match(r"^\|\s*([A-Z]{2})\s*\|(.*)\|\s*$", line)
        if m:
            cells = [re.sub(r"\*\*|`", "", c).strip() for c in m.group(2).split("|")]
            out[m.group(1)] = {"laws": cells[0], "bills": cells[1], "budget": cells[2]}
    v2 = {
        "UK": "legislation.gov.uk Public General Acts, 1950–",
        "IE": "Oireachtas API, 1922–",
        "IT": "Camera dei deputati SPARQL 1948–97; Senato SPARQL 1998–",
        "DE": "Bundestag DIP API 1973– (row level); Datenhandbuch per-term totals spread pro rata 1949–72",
        "AT": "RIS BGBl federal-law counts 1945–95; parlament.gv.at filter API 1996–",
        "DK": "Comparative Agendas Project enacted bills 1953–2003; Folketing ODA 2004–",
        "FR": "Senate multi-year statistics 1959– (counts); CAP laws 1979–2001; DILA DOLE 2002–",
        "ES": "BOE daily summaries 1979–81 and 2025–; Spanish Laws dataset (Dataverse) 1982–2024",
        "PT": "Diário da República API, 1976– (laws and decree-laws)",
        "NL": "CAP adopted bills 1981–94; Staatsblad SRU 1995–",
        "CH": "CAP 1978–99; Fedlex SPARQL 2000–",
        "BG": "parliament.bg JSON 2009–; State Gazette counts 2003–08",
        "LV": "Saeima annual reports 2000–16; Saeima open data 2017–",
    }
    for cc, laws in v2.items():
        out.setdefault(cc, {"laws": "", "bills": "", "budget": ""})["laws"] = laws
    return out


def main():
    p = load_params()
    df = pd.read_csv(DATA / "pei_country_year.csv")
    df = df[df.year <= 2025]
    cols = ["c", "y", "era", "p1b", "dec", "inf", "reg", "delay", "care", "early", "pm", "laws", "pei", "pre"]
    rows = []
    for r in df.itertuples():
        p1b = pd.Series([r.s_laws, r.s_pass_rate]).mean(skipna=True)
        inf = None if pd.isna(r.in_force_day1) else (1 if str(r.in_force_day1) == "True" else 0)
        rows.append([r.country, int(r.year), int(r.era), num(p1b), num(r.decree_share), inf,
                     None if pd.isna(r.budget_regime) else r.budget_regime, num(r.delay_days, 0), num(r.caretaker_share),
                     num(r.early_elections, 0), num(r.pm_changes, 0), num(r.laws_substantive, 0), num(r.pei),
                     1 if r.year < scoring_from(r.country) else 0])

    cab = pd.read_csv(DATA / "cabinets.csv")
    cab = cab[(cab.end.isna()) | (cab.end >= "1950-01-01")]
    cabinets = [[c.country, c.cabinet_name, c.pm if isinstance(c.pm, str) else "", c.start,
                 c.end if isinstance(c.end, str) else None, int(c.caretaker) if not pd.isna(c.caretaker) else 0,
                 c.cabinet_type if isinstance(c.cabinet_type, str) else ""] for c in cab.itertuples()]

    meta = {cc: {"name": v["name"], "panelA": cc in PANEL_A, "panelB": bool(v["panel_b"]), "from": scoring_from(cc),
                 "eras": ERAS.get(cc, [scoring_from(cc)]), "lawsFrom": LAWS_FROM.get(cc),
                 "fy": FY_START.get(cc, {1900: "01-01"})} for cc, v in COUNTRIES.items()}

    ann_path = ART / "annotations.yaml"
    ann = yaml.safe_load(ann_path.read_text()) if ann_path.exists() else []
    ann = [{k: a.get(k) for k in ("country", "year", "label", "text", "source")} for a in ann or []]

    payload = {
        "built": dt.date.today().isoformat(),
        "cols": cols, "rows": rows,
        "cabCols": ["c", "name", "pm", "start", "end", "caretaker", "type"], "cabinets": cabinets,
        "countries": meta, "sources": sources_table(), "annotations": ann,
        "pipelineW": {k: p["weights"][k] for k in ("p1_throughput", "p2_fiscal", "p3_stability", "p4_implementation")},
        "defaults": {"w": {k: p.get("artifact", {}).get("default_weights", p["weights"])[k]
                           for k in ("p1_throughput", "p2_fiscal", "p3_stability", "p4_implementation")},
                     "snap": p["stability"]["snap_penalty"], "pm": p["stability"]["pm_change_penalty"],
                     "grace": p["fiscal"]["late_grace_days"], "decree": p["throughput"]["decree_penalty"]},
    }
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    (ART / "pei-data.json").write_text(data)
    tpl = (ART / "template.html").read_text()
    html = (tpl.replace("/*__PEI_DATA__*/null", data.replace("</", "<\\/"))
            .replace("/*__PEI_SCORE__*/", (ART / "pei-score.js").read_text())
            .replace("/*__PEI_APP__*/", (ART / "app.js").read_text()))
    out = ART / "pei-explorer.html"
    out.write_text(html)
    log.info("wrote %s (%d KB; %d country-years, %d cabinets, %d notes)", out.name, len(html) // 1024, len(rows),
             len(cabinets), len(ann))


if __name__ == "__main__":
    main()
