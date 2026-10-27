"""Portugal: Diário da República, 1.ª série (diariodarepublica.pt), enacted laws and decree-laws 1976-2025,
with law origin from the Assembleia da República open data (Iniciativas) where it can be joined.

- DR: the site is an OutSystems app over Elasticsearch. Its search screen-service
  POST /dr/screenservices/dr/Pesquisas/PesquisaResultado/DataActionGetPesquisas accepts the screen variables
  (FiltrosDePesquisa: tipoConteudo AtosSerie1, serie I, tipo ["\"Lei\""], dataPublicacaoDe/Ate) with the anonymous
  OutSystems CSRF token and no cookies; it returns the raw Elastic response (hits.total + _source per act, up to
  1000 per page). moduleVersion comes from /dr/moduleservices/moduleinfo and the action's apiVersion from the
  PesquisaResultado JS bundle (both looked up at run time, with the 2026-10 values as fallback).
  One query per (act type, publication year), paged by StartIndex; cached raw/pt/dr/<type>_<year>_<start>.json.
- Types kept: Lei -> law (budget_law when the summary approves the Orçamento do Estado; ratification when it
  approves/ratifies an Acordo/Convenção/Tratado/Protocolo), Lei Orgânica -> organic_law, Lei Constitucional ->
  constitutional_law, Decreto-Lei -> decree_law (origin government). Year = DR publication year.
- AR origin: per legislatura folder on https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx the
  app.parlamento.pt/webutils JSON (Iniciativas<LEG>_json.txt, up to ~120 MB each) is downloaded to
  raw/pt/ar/. Initiatives with a "Lei (Publicação DR)" event are joined to DR laws on the publication date
  (the event's DataFase), then on title similarity when several laws appear the same day. Origin = government if
  all joined initiatives are Propostas de Lei from the Governo, parliament if all are Projetos de Lei (or
  Apreciação Parlamentar), other if mixed or from the regional assemblies (Propostas from ALRAA/ALRAM);
  unknown when no initiative joins.
- Cross-check: DILP "Produção Legislativa Parlamentar: I à XIV Legislatura" (laws approved per legislatura,
  table p.5) is downloaded to raw/pt/ and compared, by legislatura date range, with the DR count.
Outputs: laws_pt.csv, counts_pt.csv (year x instrument_type x origin).
"""
from __future__ import annotations

import difflib
import json
import re
import time
from html import unescape

import pandas as pd

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, UA, get, log, write_csv

D = RAW / "pt"
DR = "https://diariodarepublica.pt/dr"
SEARCH = f"{DR}/screenservices/dr/Pesquisas/PesquisaResultado/DataActionGetPesquisas"
MODULE_VERSION_FALLBACK = "ULK92PJiq9zb1gisWorTxw"
API_VERSION_FALLBACK = "PRsQKjEXDVBC3ZSqkS8k6A"
CSRF_ANON = "T6C+9iB49TLra4jEsMeSckDMNhQ="      # OutSystems anonymous-session CSRF token
YEARS = range(1976, 2026)
TYPES = {"Lei": "law", "Lei Orgânica": "organic_law", "Lei Constitucional": "constitutional_law",
         "Decreto-Lei": "decree_law"}
PAGE = 1000
DILP_URL = "https://ficheiros.parlamento.pt/DILP/Publicacoes/folhas/23.ProducaoLegislativa/23.pdf"
AR_PAGE = "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx"
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII"]
# Legislatura start dates (first sitting); a legislatura runs to the day before the next one starts.
LEG_START = {"I": "1976-06-03", "II": "1980-11-13", "III": "1983-05-31", "IV": "1985-11-04", "V": "1987-08-13",
             "VI": "1991-11-04", "VII": "1995-10-27", "VIII": "1999-10-25", "IX": "2002-04-05", "X": "2005-03-10",
             "XI": "2009-10-15", "XII": "2011-06-20", "XIII": "2015-10-23", "XIV": "2019-10-25", "XV": "2022-03-29",
             "XVI": "2024-03-26", "XVII": "2025-06-03"}
BUDGET_RE = re.compile(r"aprova o or[çc]amento (geral )?do estado|or[çc]amento (geral )?do estado (para|de) \d{4}|"
                       r"aprova as grandes op[çc][õo]es do plano e o or[çc]amento", re.I)
BUDGET_EXTRA = re.compile(r"or[çc]amento (suplementar|rectificativo|retificativo)|altera[çc][ãa]o ao or[çc]amento do estado|"
                          r"altera a lei do or[çc]amento do estado|altera o or[çc]amento do estado", re.I)
RAT_RE = re.compile(r"^(aprova|ratifica)[^.]{0,80}\b(acordo|conven[çc][ãa]o|tratado|protocolo)", re.I)


def _versions() -> tuple[str, str]:
    """moduleVersion (moduleinfo) and the search action's apiVersion (JS bundle); fallback to the known values."""
    try:
        mi = json.loads(get(f"{DR}/moduleservices/moduleinfo", timeout=60).decode("utf-8"))
        mv = mi["manifest"]["versionToken"]
        js_key = "/dr/scripts/dr.Pesquisas.PesquisaResultado.mvc.js"
        js = get(f"https://diariodarepublica.pt{js_key}{mi['manifest']['urlVersions'].get(js_key, '')}",
                 timeout=60).decode("utf-8", "replace")
        m = re.search(r'screenservices/dr/Pesquisas/PesquisaResultado/DataActionGetPesquisas", "([^"]+)"', js)
        return mv, (m.group(1) if m else API_VERSION_FALLBACK)
    except Exception as e:  # noqa: BLE001
        log.warning("pt: version lookup failed (%s); using fallback tokens", e)
        return MODULE_VERSION_FALLBACK, API_VERSION_FALLBACK


def _body(tipo: str, year: int, start: int, mv: str, av: str) -> dict:
    def E():
        return {"List": [], "EmptyListItem": ""}
    f = {"tipoConteudo": {"List": ["AtosSerie1"]}, "serie": {"List": ["I"]}, "numero": "", "ano": "0",
         "suplemento": "0", "dataPublicacao": "", "dataPublicacaoDe": f"{year}-01-01",
         "dataPublicacaoAte": f"{year}-12-31", "parte": "", "apendice": "", "fasciculo": "",
         "tipo": {"List": [f'"{tipo}"']}, "emissor": E(), "texto": "", "sumario": "", "entidadeProponente": E(),
         "numeroDR": "", "paginaInicial": "0", "paginaFinal": "0", "dataAssinatura": "", "dataDistribuicao": "",
         "entidadePrincipal": E(), "entidadeEmitente": E(), "docType": "", "proferido": "", "processo": "",
         "assunto": "", "recorrente": "", "recorrido": "", "relator": "", "empresa": "", "concelho": "", "nif": "",
         "anuncio": "", "numeroDoc": "", "DataAssinaturaDe": "1900-01-01", "DataAssinaturaAte": "1900-01-01",
         "DataDistribuicaoDe": "1900-01-01", "DataDistribuicaoAte": "1900-01-01", "semestre": "",
         "IsLegConsolidadaSelected": False, "IsFromData": False, "DescritorList": E()}
    v = {"FiltrosDePesquisa": f, "ResultadosPorPaginaId": 4, "StartIndex": start, "OcultarRevogados": False,
         "DestaqueExcertos": False, "TipoOrdenacaoId": 8,
         "Ordenacoes": {"List": [{"Field": "dataPublicacao", "Order": "asc"}, {"Field": "dbId", "Order": "asc"}]},
         "PesquisaAvancadaBools": '{"Atos1":true}', "MaxRecordsPerPage": PAGE, "ResultsPerPageDropdownVar": "100",
         "GetCookiePesquisasAndApplicationSettings": {
             "Pesquisas": {"Avancada": "", "EmissoresJurisprudencia": "", "Simples": "", "Sort": ""},
             "TipoOrdenacaoIDAux": "8", "DocTypeAux": "LEGISLACAO", "ResultadosPorPaginaIdAux": 4, "DataFetchStatus": 1}}
    return {"versionInfo": {"moduleVersion": mv, "apiVersion": av}, "viewName": "Pesquisas.PesquisaResultado",
            "screenData": {"variables": v}, "clientVariables": {}}


HDR = {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json", "X-CSRFToken": CSRF_ANON,
       "OutSystems-locale": "pt-PT"}


def dr_year(tipo: str, year: int, mv: str, av: str) -> list[dict] | None:
    """All Series I acts of one type published in one year (None on failure)."""
    hits, start, total = [], 0, None
    slug = re.sub(r"[^a-z]+", "_", tipo.lower().replace("ó", "o")).strip("_")
    while total is None or start < total:
        dest = D / "dr" / f"{slug}_{year}_{start}.json"
        cached = dest.exists()
        try:
            raw = get(SEARCH, dest, method="POST", json_body=_body(tipo, year, start, mv, av), headers=HDR, timeout=120)
            res = json.loads(json.loads(raw.decode("utf-8"))["data"]["Resultado"])
        except Exception as e:  # noqa: BLE001
            log.warning("pt: DR %s %d (start %d) failed: %s", tipo, year, start, e)
            if dest.exists():
                dest.unlink()
            return None
        if not cached:
            time.sleep(1.0)
        total = int(res["hits"]["total"]["value"])
        page = res["hits"]["hits"]
        hits += [h["_source"] for h in page]
        if not page:
            break
        start += len(page)
    return hits


def clean(html: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()


def detail_url(tipo: str, num: str, date: str, db_id) -> str | None:
    if not db_id:
        return None
    slug = {"Lei": "lei", "Lei Orgânica": "lei-organica", "Lei Constitucional": "lei-constitucional",
            "Decreto-Lei": "decreto-lei"}[tipo]
    return f"{DR}/detalhe/{slug}/{num.split('/')[0]}-{(date or '')[:4]}-{db_id}"


def legislatura(date: str) -> str | None:
    cur = None
    for leg in ROMAN:
        if date >= LEG_START[leg]:
            cur = leg
    return cur


# --- Assembleia da República initiatives (origin) ----------------------------------------------------------
def ar_initiatives() -> list[dict]:
    """[{leg, tipo, autor, titulo, pub_date}] for initiatives with a 'Lei (Publicação DR)' event."""
    out = []
    cache = D / "ar" / "DAIniciativas.html"
    try:
        page = get(AR_PAGE, cache, force=True).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        if not cache.exists():
            log.warning("pt: AR open-data page failed: %s", e)
            return out
        log.warning("pt: AR open-data page failed (%s); using the cached copy", e)
        page = cache.read_text(encoding="utf-8", errors="replace")
    folders = {}
    for href in re.findall(r'href="(/Cidadania/Paginas/DAIniciativas\.aspx\?t=[0-9a-f]+&amp;Path=[^"]+)"', page):
        t = re.search(r"t=([0-9a-f]+)", href).group(1)
        try:
            import base64
            name = base64.b64decode(bytes.fromhex(t)).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        m = re.match(r"([IVXL]+) Legislatura", name)
        if m and m.group(1) in LEG_START:
            folders[m.group(1)] = "https://www.parlamento.pt" + href.replace("&amp;", "&")
    log.info("pt: AR folders found for %s", sorted(folders, key=ROMAN.index))
    for leg in sorted(folders, key=ROMAN.index):
        dest = D / "ar" / f"Iniciativas{leg}_json.txt"
        try:
            if not dest.exists():
                # www.parlamento.pt answers 403 after a few quick requests: pace the folder pages, retry once
                for attempt in range(2):
                    try:
                        fp = get(folders[leg], timeout=60).decode("utf-8", "replace")
                        break
                    except RuntimeError as e:
                        if attempt:
                            raise
                        log.warning("pt: AR %s folder refused (%s); waiting 120 s", leg, str(e)[-40:])
                        time.sleep(120)
                m = re.search(r'href="(https://app\.parlamento\.pt/webutils/docs/doc\.txt\?[^"]+_json\.txt[^"]*)"', fp)
                if not m:
                    log.warning("pt: AR %s: no JSON link", leg)
                    continue
                time.sleep(5.0)
                get(unescape(m.group(1)), dest, timeout=900, headers={"User-Agent": UA})
                time.sleep(20.0)
            data = json.loads(dest.read_bytes().decode("utf-8-sig"))
        except Exception as e:  # noqa: BLE001
            log.warning("pt: AR %s failed: %s", leg, e)
            continue
        n = 0
        for ini in data:
            evs = [e for e in ini.get("IniEventos") or [] if (e.get("Fase") or "").startswith("Lei (Publicação DR)")]
            if not evs:
                continue
            autor = ((ini.get("IniAutorOutros") or {}).get("nome") or "").strip()
            for e in evs[:1]:
                out.append({"leg": leg, "tipo": ini.get("IniDescTipo") or "", "autor": autor,
                            "titulo": ini.get("IniTitulo") or "", "pub_date": (e.get("DataFase") or "")[:10]})
                n += 1
        log.info("pt: AR %s: %d initiatives with a law-publication event", leg, n)
        del data
    return out


def ini_origin(i: dict) -> str:
    t = i["tipo"].lower()
    if t.startswith("proposta de lei"):
        return "government" if i["autor"].lower().startswith("govern") or not i["autor"] else "other"
    if t.startswith("projeto de lei") or t.startswith("apreciação parlamentar"):
        return "parliament"
    return "other"


def join_origin(laws: pd.DataFrame, inis: list[dict]) -> pd.Series:
    """Origin per DR law row (index-aligned); laws are the non-decree rows."""
    origin = pd.Series("unknown", index=laws.index, dtype=object)
    if not inis:
        return origin
    by_date: dict[str, list[dict]] = {}
    for i in inis:
        by_date.setdefault(i["pub_date"], []).append(i)
    for date, g in laws.groupby("date"):
        cands = by_date.get(date, [])
        if not cands:
            continue
        if len(g) == 1:
            assign = {g.index[0]: cands}
        else:   # several laws that day: each initiative goes to its most similar law title
            assign = {}
            for i in cands:
                ti = i["titulo"].lower()
                best = max(g.index, key=lambda ix: difflib.SequenceMatcher(None, ti, laws.at[ix, "title"].lower()).ratio())
                assign.setdefault(best, []).append(i)
        for ix, lst in assign.items():
            os_ = {ini_origin(i) for i in lst}
            origin.at[ix] = os_.pop() if len(os_) == 1 else "other"
    return origin


def dilp_check(laws: pd.DataFrame) -> None:
    dest = D / "dilp_producao_legislativa_I_XIV.pdf"
    try:
        get(DILP_URL, dest, timeout=120)
        import pdfplumber
        with pdfplumber.open(dest) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[3:6])
    except Exception as e:  # noqa: BLE001
        log.warning("pt: DILP cross-check unavailable: %s", e)
        return
    dilp = {}
    sect = text.split("Leis Aprovadas", 1)[-1]
    for leg, pjl, ppl, rat, const, tot in re.findall(r"^([IVX]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$",
                                                      sect, re.M):
        if leg in LEG_START and leg not in dilp:
            dilp[leg] = {"pjl": int(pjl), "ppl": int(ppl), "rat_ap": int(rat), "const": int(const), "total": int(tot)}
    pl = laws[laws.instrument_type != "decree_law"].copy()
    pl["leg"] = pl.date.map(legislatura)
    dr = pl.groupby("leg").size()
    org = pl.groupby(["leg", "origin"]).size().unstack(fill_value=0)
    rows = []
    for leg in ROMAN[:14]:
        d = dilp.get(leg, {})
        o = org.loc[leg] if leg in org.index else {}
        rows.append({"leg": leg, "dilp_total": d.get("total"), "dr_laws": int(dr.get(leg, 0)),
                     "dilp_ppl": d.get("ppl"), "dr_gov": int(o.get("government", 0)),
                     "dilp_pjl": d.get("pjl"), "dr_parl": int(o.get("parliament", 0)), "dr_unknown": int(o.get("unknown", 0))})
    chk = pd.DataFrame(rows)
    log.info("pt: DILP vs DR (DR by publication date within legislatura dates):\n%s", chk.to_string(index=False))
    chk.to_csv(D / "dilp_vs_dr.csv", index=False)


def main():
    D.mkdir(parents=True, exist_ok=True)
    mv, av = _versions()
    log.info("pt: DR moduleVersion %s apiVersion %s", mv, av)
    rows, failed = [], []
    for tipo, itype in TYPES.items():
        for y in YEARS:
            hits = dr_year(tipo, y, mv, av)
            if hits is None:
                failed.append((tipo, y))
                continue
            for s in hits:
                if (s.get("tipo") or "") != tipo:
                    continue
                date = (s.get("dataPublicacao") or "")[:10]
                summ = clean(s.get("sumario"))
                it, is_b, is_r = itype, False, False
                if itype == "law":
                    if BUDGET_RE.search(summ) and not BUDGET_EXTRA.search(summ):
                        it, is_b = "budget_law", True
                    elif BUDGET_EXTRA.search(summ):
                        is_b = True
                    elif RAT_RE.search(summ):
                        it, is_r = "ratification", True
                num = s.get("numero") or ""
                rows.append({
                    "country": "PT", "year": int(date[:4]) if date else y, "date": date or None, "instrument_type": it,
                    "origin": "government" if itype == "decree_law" else "unknown",
                    "title": f"{tipo} n.º {num}: {summ}" if summ else f"{tipo} n.º {num}", "length_words": None,
                    "cap_topic": None, "is_budget": is_b, "is_ratification": is_r, "source": "dre_serie1",
                    "source_id": f"{tipo} {num}", "source_url": detail_url(tipo, num, date, s.get("dbId")),
                })
    if failed:
        log.warning("pt: DR queries failed for %d (type, year): %s", len(failed), failed[:20])
    if not rows:
        log.error("pt: no DR rows; nothing written")
        return
    laws = pd.DataFrame(rows, columns=LAWS_COLUMNS).drop_duplicates("source_id")
    laws = laws.sort_values(["date", "source_id"]).reset_index(drop=True)

    # --- origin of parliament laws from the AR open data ---------------------------------------------
    try:
        inis = ar_initiatives()
        mask = laws.instrument_type != "decree_law"
        sub = laws[mask].copy()
        sub["title"] = sub.title.str.split(": ", n=1).str[-1]
        laws.loc[mask, "origin"] = join_origin(sub, inis)
    except Exception as e:  # noqa: BLE001
        log.warning("pt: AR origin join failed, origins left unknown: %s", e)

    write_csv(laws, INTER / "laws_pt.csv")
    counts = (laws.groupby(["year", "instrument_type", "origin"]).size().reset_index(name="n")
              .assign(country="PT", source="dre_serie1", source_url=SEARCH))
    write_csv(counts[COUNTS_COLUMNS], INTER / "counts_pt.csv")
    per = laws.assign(k=laws.instrument_type.eq("decree_law").map({True: "decree_law", False: "parl_law"})) \
        .groupby(["year", "k"]).size().unstack(fill_value=0)
    log.info("pt per year (parliament laws / decree-laws):\n%s", per.to_string())
    log.info("pt origins of parliament laws: %s",
             laws[laws.instrument_type != "decree_law"].origin.value_counts().to_dict())
    dilp_check(laws)


if __name__ == "__main__":
    main()
