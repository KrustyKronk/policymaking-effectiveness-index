"""Spain.
- Laws 1979-1982 and 2025- : BOE daily summaries (datosabiertos/api/boe/sumario/YYYYMMDD, answers from
  1978-12-29), section I, Jefatura del Estado (laws, organic laws, decree-laws) plus Reales Decretos
  Legislativos from any department. 1983-2024: Spanish Laws and Legislative Decrees dataset (Dataverse
  10.7910/DVN/1VKJXZ, file Laws_1982_2024.xlsx). The dataset starts with the II legislature (Dec 1982): it holds
  only 6 laws dated 1982, so 1982 is taken from the BOE too. 1985 and 2024 are also read from the BOE for
  validation only (raw/es/validation_1985.txt, validation_2024.txt; 1985 also against CAP Spain laws).
- BOE 'legislación consolidada' API: every state-level norm with rank of law by year (Ley, Ley Orgánica,
  Real Decreto-ley, Real Decreto Legislativo), 2000-2025 -> laws_es.csv.
- Congreso open data (current legislature only): approved legislative initiatives, bills by author
  -> bills_es.csv for the XV legislature. Origin for earlier years comes from the CAP bills files (normalise step)."""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import time

import pandas as pd

from pipeline.common import BILLS_COLUMNS, COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, get_json, log, write_csv

D = RAW / "es"
BOE = "https://www.boe.es/datosabiertos/api/legislacion-consolidada"
RANGO_MAP = {"Ley": "law", "Ley Orgánica": "organic_law", "Real Decreto-ley": "decree_law",
             "Real Decreto Legislativo": "legislative_decree"}
QUERIES = ["rango:Ley", 'rango:"Real Decreto-ley"', 'rango:"Real Decreto Legislativo"']
YEARS = range(1979, 2026)
DV_FROM = 1983                      # first year taken from the Dataverse file
BOE_EARLY = (dt.date(1979, 1, 1), dt.date(1982, 12, 31))
BOE_CHECK = (dt.date(1985, 1, 1), dt.date(1985, 12, 31))
PAUSE = 0.3


def boe_year(q: str, year: int) -> list[dict]:
    query = {"query": {"query_string": {"query": q},
                       "range": {"fecha_publicacion": {"gte": f"{year}0101", "lte": f"{year}1231"}}}}
    safe = re.sub(r"[^a-z]", "", q.lower())
    j = get_json(BOE, D / "boe" / f"{safe}_{year}.json", params={"query": json.dumps(query), "limit": -1})
    return j.get("data", []) or []


def congreso_bills() -> pd.DataFrame | None:
    try:
        page = get("https://www.congreso.es/es/opendata/iniciativas", D / "congreso" / "opendata_page.html",
                   force=True).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        log.warning("congreso opendata page failed: %s", e)
        return None
    links = sorted(set(re.findall(r'href="([^"]*webpublica/opendata/iniciativas/[^"]+\.csv)"', page)))
    (D / "congreso").mkdir(parents=True, exist_ok=True)
    (D / "congreso" / "links.txt").write_text("\n".join(links), encoding="utf-8")
    frames = []
    for l in links:
        url = l if l.startswith("http") else "https://www.congreso.es" + l
        name = url.rsplit("/", 1)[-1]
        kind = name.split("__")[0]
        if kind not in ("ProyectosDeLey", "ProposicionesDeLey", "IniciativasLegislativasAprobadas"):
            continue
        try:
            raw = get(url, D / "congreso" / name)
            df = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding="utf-8-sig")
            df["__kind"] = kind
            frames.append(df)
        except Exception as e:  # noqa: BLE001
            log.warning("congreso file %s failed: %s", name, e)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


TYPE_MAP = {"Ordinary Law": "law", "Law": "law", "Organic Law": "organic_law", "Decree Law": "decree_law",
            "Legislative Decree": "legislative_decree"}
TITLE_RX = re.compile(r"^(Ley Orgánica|Ley|Real Decreto-ley|Real Decreto Legislativo)\s+\d+/(\d{4})")


def sumario_items(day: dt.date) -> list[dict]:
    """All items of BOE section I for one day, tagged with their department."""
    dest = D / "sumario" / f"{day:%Y%m%d}.json"
    none = D / "sumario" / f"{day:%Y%m%d}.none"   # marker: no BOE that day (404), past dates only
    if none.exists():
        return []
    live = not dest.exists()
    j = None
    for attempt in range(4):
        try:
            j = get_json(f"https://www.boe.es/datosabiertos/api/boe/sumario/{day:%Y%m%d}", dest, retries=2,
                         ok_statuses=(200,))
            break
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "HTTP 404" in msg:          # no BOE that day
                if day < dt.date.today():
                    none.parent.mkdir(parents=True, exist_ok=True)
                    none.write_text("404\n")
                return []
            if "HTTP 429" in msg and attempt < 3:
                log.warning("es: 429 on sumario %s, sleeping %ds", day, 30 * 2 ** attempt)
                time.sleep(30 * 2 ** attempt)
                continue
            log.warning("es: sumario %s failed: %s", day, e)
            return []
        finally:
            if live:
                time.sleep(PAUSE)
    if j is None:
        return []
    out = []

    def walk(x, dep=None, sec=None):
        if isinstance(x, dict):
            if "seccion" in x or ("codigo" in x and "departamento" in x):
                sec = x.get("codigo", sec)
            if "nombre" in x and ("epigrafe" in x or ("item" in x and "codigo" in x)):
                dep = x["nombre"]
            if "identificador" in x and "titulo" in x:
                out.append({**x, "_dep": dep, "_sec": sec})
            for v in x.values():
                walk(v, dep, sec)
        elif isinstance(x, list):
            for v in x:
                walk(v, dep, sec)
    walk(j.get("data", {}))
    return out


def classify(title: str) -> str | None:
    m = TITLE_RX.match(title or "")
    if not m:
        return None
    return {"Ley Orgánica": "organic_law", "Ley": "law", "Real Decreto-ley": "decree_law",
            "Real Decreto Legislativo": "legislative_decree"}[m.group(1)]


def main():
    # 1. 1983-2024 from the Spanish Laws and Legislative Decrees dataset (Dataverse 10.7910/DVN/1VKJXZ)
    dv = pd.read_excel(RAW / "spain_dataverse" / "Laws_1982_2024.xlsx")
    dv_1985 = int((dv.year == 1985).sum())
    dv = dv[dv.year.between(DV_FROM, 2024)]
    rows = []
    for _, r in dv.iterrows():
        itype = TYPE_MAP.get(str(r.TypeLaw).strip(), "law")
        title = str(r.TITLE)
        is_budget = bool(re.search(r"Presupuestos Generales del Estado", title, re.I)) and itype == "law"
        rows.append({"country": "ES", "year": int(r.year), "date": f"{int(r.year)}-{int(r.month):02d}-01" if pd.notna(r.month) else f"{int(r.year)}-01-01",
                     "instrument_type": "budget_law" if is_budget else itype,
                     "origin": "government" if itype in ("decree_law", "legislative_decree") else "unknown",
                     "title": title, "length_words": None, "cap_topic": r.CAP_Code, "is_budget": is_budget,
                     "is_ratification": False, "source": "es_dataverse_1VKJXZ", "source_id": str(r.ID),
                     "source_url": "https://doi.org/10.7910/DVN/1VKJXZ"})
    # 2. BOE daily summaries: 1979-1982 and 2024-01-01 .. today (1985 and 2024 used only to validate)
    def boe_days():
        for a, b in (BOE_EARLY, BOE_CHECK, (dt.date(2024, 1, 1), dt.date.today())):
            d = a
            while d <= b:
                yield d
                d += dt.timedelta(days=1)

    boe = []
    for day in boe_days():
        if day.month == 1 and day.day == 1:
            log.info("es: BOE sumario %d", day.year)
        for it in sumario_items(day):
            if str(it.get("_sec")) != "1":
                continue
            itype = classify(it.get("titulo", ""))
            dep = (it.get("_dep") or "").upper()
            if not itype or "COMUNIDAD" in dep or "AUTÓNOMA" in dep:
                continue
            if itype != "legislative_decree" and "JEFATURA DEL ESTADO" not in dep:
                continue
            title = it["titulo"]
            is_budget = bool(re.search(r"Presupuestos Generales del Estado", title)) and itype == "law"
            boe.append({"country": "ES", "year": day.year, "date": day.isoformat(),
                        "instrument_type": "budget_law" if is_budget else itype,
                        "origin": "government" if itype in ("decree_law", "legislative_decree") else "unknown",
                        "title": title, "length_words": None, "cap_topic": None, "is_budget": is_budget,
                        "is_ratification": False, "source": "boe_sumario", "source_id": it["identificador"],
                        "source_url": f"https://www.boe.es/diario_boe/txt.php?id={it['identificador']}"})
    boe = pd.DataFrame(boe, columns=LAWS_COLUMNS).drop_duplicates("source_id")
    n24_boe, n24_dv = (boe.year == 2024).sum(), sum(1 for r in rows if r["year"] == 2024)
    log.info("es 2024 validation: BOE sumario %d vs dataset %d", n24_boe, n24_dv)
    (D / "validation_2024.txt").write_text(f"BOE sumario 2024: {n24_boe}\nDataverse 2024: {n24_dv}\n", encoding="utf-8")
    try:
        cap = pd.read_csv(RAW / "cap" / "ES_laws__Spain_Laws19802018_19.1.csv", encoding_errors="replace", sep=None,
                          engine="python")
        cap_n = cap.year.value_counts()
        b85 = boe[boe.year == 1985]
        msg = (f"BOE sumario 1985: {len(b85)} {b85.instrument_type.value_counts().to_dict()}\n"
               f"CAP Spain laws 1985: {int(cap_n.get(1985, 0))} {cap[cap.year == 1985].type_of_law.value_counts().to_dict()}\n"
               f"Dataverse 1985: {dv_1985}\n"
               + "".join(f"BOE {y}: {(boe.year == y).sum()} vs CAP {int(cap_n.get(y, 0))}\n" for y in (1980, 1981, 1982)))
        log.info("es validation:\n%s", msg)
        (D / "validation_1985.txt").write_text(msg, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("es 1985 validation skipped: %s", e)
    early = boe[boe.year.between(BOE_EARLY[0].year, BOE_EARLY[1].year)]
    laws = pd.concat([early, pd.DataFrame(rows, columns=LAWS_COLUMNS), boe[boe.year >= 2025]],
                     ignore_index=True).sort_values("date")
    write_csv(laws, INTER / "laws_es.csv")
    counts = (laws.groupby(["year", "instrument_type"]).size().reset_index(name="n")
              .assign(country="ES", origin="all", source="es_dataverse+boe_sumario", source_url="https://www.boe.es/datosabiertos/"))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_es.csv")

    df = congreso_bills()
    if df is not None:
        df.columns = [c.strip().upper() for c in df.columns]
        bills = []
        for _, r in df.iterrows():
            kind = r["__KIND"]
            if kind == "IniciativasLegislativasAprobadas":
                continue
            autor = str(r.get("AUTOR", "") or "")
            origin = "government" if kind == "ProyectosDeLey" or "Gobierno" in autor else "parliament"
            res = str(r.get("RESULTADOTRAMITACION", "") or "")
            sit = str(r.get("SITUACIONACTUAL", "") or "")
            if re.search(r"Aprobad", res, re.I):
                outcome = "enacted"
            elif re.search(r"Rechazad|No tomada en consideraci", res, re.I):
                outcome = "defeated"
            elif re.search(r"Retirad", res, re.I):
                outcome = "withdrawn"
            elif re.search(r"Caducad|Decaíd|Disoluci", res + sit, re.I):
                outcome = "lapsed"
            else:
                outcome = "pending"
            fecha = str(r.get("FECHAPRESENTACION", "") or "")
            d_intro = pd.to_datetime(fecha, dayfirst=True, errors="coerce")
            bills.append({
                "country": "ES", "bill_id": str(r.get("NUMEXPEDIENTE", r.get("EXPEDIENTE", ""))),
                "title": r.get("OBJETO", r.get("TITULO", "")), "year_introduced": d_intro.year if pd.notna(d_intro) else None,
                "origin": origin, "outcome": outcome, "date_introduced": d_intro.date().isoformat() if pd.notna(d_intro) else None,
                "date_final": None, "instrument_type": "organic_law" if "orgánica" in str(r.get("OBJETO", "")).lower() else "law",
                "source": "congreso_opendata", "legislatura": r.get("LEGISLATURA"), "autor": autor, "resultado": res,
            })
        b = pd.DataFrame(bills)
        write_csv(b[BILLS_COLUMNS + ["legislatura", "autor", "resultado"]], INTER / "bills_es.csv")
    else:
        log.warning("es: no Congreso bills written")


if __name__ == "__main__":
    main()
