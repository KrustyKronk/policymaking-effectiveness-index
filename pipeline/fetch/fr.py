"""France: enacted laws 2002-2025, row level, from DILA "DOLE" open data (dossiers législatifs).

Source: https://echanges.dila.gouv.fr/OPENDATA/DOLE/ (Licence Ouverte). The Freemium full dump
(~19 MB tar.gz, parsed in memory member by member) is overlaid with the daily DOLE_*.tar.gz deltas
published after it, up to DELTA_CUTOFF (to complete calendar 2025) plus the latest delta. A later
delta replaces an earlier copy of the same dossier ID.

Each dossier has META_DOSSIER_LEGISLATIF/TYPE in {LOI_PUBLIEE, ORDONNANCE_PUBLIEE, PROJET_LOI,
PROPOSITION_LOI, PROJET_ORDONNANCE}. Only LOI_PUBLIEE goes to laws_fr.csv.
- date: promulgation date parsed from the title ("LOI n° 2008-496 du 27 mai 2008 ..."), falling
  back to DATE_CREATION (JO publication, usually the next day).
- origin: "projet de loi" -> government, "proposition de loi" -> parliament, read from the
  LIBELLE_TEXTE_* labels, else the reading-link labels, else the pjl/ppl dossier URLs (origin_of).
- instrument_type from the title: loi constitutionnelle, loi organique, budget laws (loi de finances
  incl. rectificatives, loi de financement de la sécurité sociale, loi de règlement / approbation des
  comptes, loi spéciale), treaty laws ("autorisant la ratification/l'approbation/l'adhésion"), else law.
  Laws ratifying an ordonnance stay `law` with note=ratifies_ordonnance (extra trailing column).
- source_url: Légifrance JORF URL built from ID_TEXTE_1 (the promulgated text's JORFTEXT id).
- length_words: null (DOLE holds the bill as tabled, not the promulgated text).
counts_fr.csv: laws by year x instrument_type x origin, plus ORDONNANCE_PUBLIEE dossiers as
decree_law/government (ordonnances are France's delegated-legislation instrument; not in laws_fr).
Coverage caveat: DOLE starts in mid-2002 and appears to follow only laws DILA tracks with a
dossier, so treaty-ratification laws in particular may be under-counted versus the JO.

Back-extension (2026-10-18):
- laws_fr.csv 1979-2001: row level from the CAP France laws file (raw/cap/FR_laws__lois_79_13_short_7.csv;
  titre, year, date1 = promulgation date YYYYMMDD, official_id = law number), source = cap_fr, origin unknown,
  instrument_type from classify() on the title. CAP includes treaty laws ("autorisant la ratification ...").
  DOLE rows keep 2002-; CAP 2002-2013 is used only for the CAP-vs-DOLE check (raw/fr/cap_vs_dole.csv).
- counts_fr.csv 1959-2001: Sénat, "Statistiques pluriannuelles" (Partie II, table VII.E "Origine des lois
  promulguées depuis 1959": PJL / PPL AN / PPL Sénat hors conventions, conventions), source =
  senat_statistiques. 1959-1994 are calendar years; from 1995 the Sénat counts by session (Oct-Sep):
  "1995" = Jan-Sep 1995 only, and session "1995-1996" is stored as year 1996 (session end), and so on to
  2000-2001 -> 2001. Rows: law x {government (PJL), parliament (PPL AN + PPL Sénat), all} hors conventions,
  and ratification x all (conventions). Check values: 1959 = 51, 1980 = 49, 1988 = 23, 1994 = 71.
  The Sénat-vs-CAP comparison per year 1979-1994 is written to raw/fr/senat_vs_cap.csv.
"""
from __future__ import annotations

import collections
import io
import re
import tarfile
import time

import pandas as pd
from lxml import etree

from pipeline.common import COUNTS_COLUMNS, INTER, LAWS_COLUMNS, RAW, get, log, write_csv

BASE = "https://echanges.dila.gouv.fr/OPENDATA/DOLE/"
D = RAW / "fr"
YEARS = range(2002, 2026)
CAP_FILE = RAW / "cap" / "FR_laws__lois_79_13_short_7.csv"
CAP_YEARS = range(1979, 2002)
CAP_URL = "https://www.comparativeagendas.net/datasets_codebooks"
SENAT_URLS = ["https://www.senat.fr/fileadmin/cru-1759398938/Seance/Statistiques/Statistiques_pluriannuelles.pdf",
              "https://www.senat.fr/fileadmin/Seance/Statistiques/Statistiques_pluriannuelles.pdf",
              "https://m.senat.fr/fileadmin/Seance/Statistiques/Rapport_annuel/2021-2022/Statistiques_pluriannuelles.pdf"]
SENAT_LAST_YEAR = 2001
DELTA_CUTOFF = "20260131"  # deltas up to this date are applied so that 2025 is complete
SRC = "dila_dole"
PARSER = etree.XMLParser(huge_tree=True, recover=True)
MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
          "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
          "décembre": 12, "decembre": 12}


def list_dir() -> tuple[str | None, list[str]]:
    try:
        html = get(BASE, D / "dole_index.html", force=True).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        log.warning("fr: DOLE index fetch failed (%s); using cached copy if any", e)
        p = D / "dole_index.html"
        html = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    names = sorted(set(re.findall(r'href="([^"]+\.tar\.gz)"', html)))
    freemium = [n for n in names if n.startswith("Freemium_dole")]
    deltas = sorted(n for n in names if n.startswith("DOLE_"))
    return (freemium[-1] if freemium else None), deltas


def iter_dossiers(blob: bytes):
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf:
            if not (m.isfile() and m.name.endswith(".xml")):
                continue
            f = tf.extractfile(m)
            if f is None:
                continue
            try:
                yield etree.fromstring(f.read(), PARSER)
            except Exception as e:  # noqa: BLE001
                log.warning("fr: could not parse %s: %s", m.name, e)


def record(root) -> dict | None:
    if root is None:
        return None
    md = root.find(".//META_DOSSIER_LEGISLATIF")
    if md is None:
        return None
    t = lambda path, el=root: (el.findtext(path) or "").strip()  # noqa: E731
    return {
        "id": t(".//META_COMMUN/ID"), "type": t("TYPE", md), "titre": t("TITRE", md),
        "date_creation": t("DATE_CREATION", md), "id_texte_1": t("ID_TEXTE_1", md),
        "legislature": t("LEGISLATURE/NUMERO", md),
        "origin": origin_of(root),
    }


def origin_of(root) -> str:
    """projet de loi -> government, proposition de loi -> parliament. Signals in priority order:
    the LIBELLE_TEXTE_* labels, then the ARBORESCENCE link labels (readings: "Projet/Proposition de loi
    adopté(e) ..."), then the AN/Sénat dossier URLs (pjl / ppl)."""
    libs = " ".join(" ".join("".join(e.itertext()).split()) for e in root.iter()
                    if isinstance(e.tag, str) and e.tag.startswith("LIBELLE_TEXTE")).lower()
    if "projet de loi" in libs:
        return "government"
    if "proposition de loi" in libs:
        return "parliament"
    links = [(e.get("libelle") or "", e.get("lien") or "") for e in root.iter("LIEN")]
    lab = " ".join(a for a, _ in links).lower()
    urls = " ".join(u for _, u in links).lower()
    by_url = ("government" if re.search(r"pjl\d|/projets/", urls) else
              "parliament" if re.search(r"ppl\d|/propositions/|pion\d", urls) else "unknown")
    proj, prop = "projet de loi" in lab, "proposition de loi" in lab
    if proj and not prop:
        return "government"
    if prop and not proj:
        return "parliament"
    return by_url


def promulgation_date(title: str, fallback: str) -> str:
    m = re.search(r"\bdu\s+(\d{1,2})(?:er)?\s+([a-zéûè]+)\s+(\d{4})", title, re.I)
    if m and m.group(2).lower() in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return fallback[:10]


def classify(title: str) -> tuple[str, bool, bool, str]:
    s = title.lower().replace("’", "'")
    head = re.sub(r"^loi\s+(n°\s*[\d-]+\s+)?du\s+\d{1,2}(er)?\s+\w+\s+\d{4}\s*", "", s)
    note = "ratifies_ordonnance" if re.search(r"ratifiant\s+(l'|les\s+)ordonnance", s) else ""
    if s.startswith("loi constitutionnelle"):
        return "constitutional_law", False, False, note
    if re.search(r"^loi organique", s):
        return "organic_law", False, False, note
    if re.search(r"^loi (n°\s*[\d-]+\s+du[^,]*?)?\s*(de finances|de financement de la sécurité sociale|"
                 r"de financement rectificative|de règlement|spéciale|relative aux résultats de la gestion)", s) \
            or re.search(r"^(de finances|de financement de la sécurité sociale|de règlement|spéciale prévue|"
                         r"relative aux résultats de la gestion|portant règlement du budget|"
                         r"d'approbation des comptes)", head):
        return "budget_law", True, False, note
    if re.search(r"autorisant (la ratification|l'approbation|l'adhésion|l'acceptation)", s):
        return "ratification", False, True, note
    return "law", False, False, note


def senat_origin_table() -> tuple[dict[int, dict], str | None]:
    """Sénat table "Origine des lois promulguées depuis 1959" -> {year: {pjl, ppl_an, ppl_senat, hors_conv,
    conventions, total}}. Session rows "1995-1996" map to their end year; "1995" (footnote 1: Jan-Sep) to 1995."""
    import pdfplumber
    dest = D / "senat" / "Statistiques_pluriannuelles.pdf"
    url_ok = None
    for url in SENAT_URLS:
        try:
            get(url, dest, timeout=180)
            url_ok = url
            break
        except Exception as e:  # noqa: BLE001
            log.warning("fr: Sénat statistics %s failed: %s", url, e)
    if not dest.exists():
        return {}, None
    with pdfplumber.open(dest) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    start = text.find("ORIGINE DES LOIS PROMULGU")
    if start < 0:
        log.warning("fr: Sénat origin table not found")
        return {}, url_ok
    num = r"(\d+|-)(?:\s*\(\s*\d+\s*%\s*\))?"
    rx = re.compile(rf"^(\d{{4}})(?:-(\d{{4}}))?(1)?\s+{num}\s+{num}\s+{num}\s+(\d[\d ]*?)\s+(\d+|-)\s+(\d[\d ]*)$")
    out: dict[int, dict] = {}
    for ln in text[start:].splitlines():
        ln = ln.strip()
        if ln.startswith("Total"):
            break
        m = rx.match(ln)
        if not m:
            continue
        y0, y1 = int(m.group(1)), m.group(2)
        year = int(y1) if y1 else y0
        v = [0 if x == "-" else int(x.replace(" ", "")) for x in m.groups()[3:]]
        rec = dict(zip(["pjl", "ppl_an", "ppl_senat", "hors_conv", "conventions", "total"], v))
        if rec["pjl"] + rec["ppl_an"] + rec["ppl_senat"] != rec["hors_conv"]:
            log.warning("fr: Sénat %s: PJL+PPL %d != hors conventions %d", ln[:9],
                        rec["pjl"] + rec["ppl_an"] + rec["ppl_senat"], rec["hors_conv"])
        rec["session"] = f"{y0}-{y1}" if y1 else (f"{y0} (Jan-Sep)" if y0 == 1995 else str(y0))
        out.setdefault(year, rec)
    log.info("fr: Sénat origin table: %d years %s-%s", len(out), min(out, default=None), max(out, default=None))
    return out, url_ok


def cap_laws() -> list[dict]:
    if not CAP_FILE.exists():
        log.warning("fr: CAP file missing (%s); no 1979-2001 rows", CAP_FILE.name)
        return []
    cap = pd.read_csv(CAP_FILE, encoding_errors="replace", sep=None, engine="python")
    rows = []
    for _, r in cap.iterrows():
        d = str(r.get("date1") or "")
        date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d) else f"{int(r.year)}-01-01"
        title = " ".join(str(r.get("titre") or "").split())
        itype, is_budget, is_rat, note = classify(title)
        rows.append({
            "country": "FR", "year": int(date[:4]), "date": date, "instrument_type": itype, "origin": "unknown",
            "title": title, "length_words": None,
            "cap_topic": int(r.majortopic) if pd.notna(r.get("majortopic")) else None,
            "is_budget": is_budget, "is_ratification": is_rat, "source": "cap_fr",
            "source_id": str(r.get("official_id") or r.get("id")), "source_url": CAP_URL, "note": note,
        })
    return rows


def main():
    freemium, deltas = list_dir()
    dossiers: dict[str, dict] = {}
    if freemium is None:
        log.warning("fr: no Freemium dump listed; trying the known 2025-07-13 file")
        freemium = "Freemium_dole_global_20250713-140000.tar.gz"
    try:
        blob = get(BASE + freemium, D / freemium, timeout=600)
        for root in iter_dossiers(blob):
            r = record(root)
            if r and r["id"]:
                dossiers[r["id"]] = r
        log.info("fr: %d dossiers from %s", len(dossiers), freemium)
    except Exception as e:  # noqa: BLE001
        log.warning("fr: Freemium dump unusable: %s", e)

    stamp = re.search(r"(\d{8}-\d{6})", freemium).group(1)
    wanted = [n for n in deltas if n[5:20] > stamp and n[5:13] <= DELTA_CUTOFF]
    if deltas and deltas[-1] not in wanted:
        wanted.append(deltas[-1])
    n_ok = 0
    for i, name in enumerate(wanted):
        dest = D / "deltas" / name
        try:
            cached = dest.exists()
            blob = get(BASE + name, dest)
            if not cached:
                time.sleep(0.3)
            for root in iter_dossiers(blob):
                r = record(root)
                if r and r["id"]:
                    dossiers[r["id"]] = r
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            log.warning("fr: delta %s failed: %s", name, e)
        if i % 40 == 39:
            log.info("fr: %d/%d deltas applied", i + 1, len(wanted))
    log.info("fr: applied %d/%d deltas; %d dossiers total", n_ok, len(wanted), len(dossiers))
    if not dossiers:
        log.warning("fr: nothing parsed; no outputs written")
        return
    pd.DataFrame(dossiers.values()).to_csv(D / "dole_dossiers.csv", index=False)

    laws, ords = [], collections.Counter()
    for r in dossiers.values():
        if r["type"] == "ORDONNANCE_PUBLIEE":
            y = int(promulgation_date(r["titre"], r["date_creation"])[:4] or 0)
            if y in YEARS:
                ords[y] += 1
            continue
        if r["type"] != "LOI_PUBLIEE":
            continue
        date = promulgation_date(r["titre"], r["date_creation"])
        try:
            year = int(date[:4])
        except ValueError:
            continue
        if year not in YEARS:
            continue
        itype, is_budget, is_rat, note = classify(r["titre"])
        origin = r["origin"]
        laws.append({
            "country": "FR", "year": year, "date": date, "instrument_type": itype, "origin": origin,
            "title": r["titre"], "length_words": None, "cap_topic": None, "is_budget": is_budget,
            "is_ratification": is_rat, "source": SRC, "source_id": r["id"],
            "source_url": (f"https://www.legifrance.gouv.fr/jorf/id/{r['id_texte_1']}" if r["id_texte_1"]
                           else f"https://www.legifrance.gouv.fr/dossierlegislatif/{r['id']}/"),
            "note": note,
        })
    dole_df = pd.DataFrame(laws, columns=LAWS_COLUMNS + ["note"])
    try:
        cap_all = pd.DataFrame(cap_laws(), columns=LAWS_COLUMNS + ["note"])
    except Exception as e:  # noqa: BLE001
        log.warning("fr: CAP rows failed: %s", e)
        cap_all = pd.DataFrame(columns=LAWS_COLUMNS + ["note"])
    cap_keep = cap_all[cap_all.year.isin(CAP_YEARS) & ~cap_all.year.isin(set(dole_df.year))]
    laws_df = pd.concat([cap_keep, dole_df], ignore_index=True).sort_values(["date", "source_id"])
    write_csv(laws_df, INTER / "laws_fr.csv")
    log.info("fr: %d CAP rows %s-%s + %d DOLE rows", len(cap_keep), cap_keep.year.min(), cap_keep.year.max(),
             len(dole_df))

    # CAP vs DOLE, 2002-2013 (overlap of the two row-level sources)
    if not cap_all.empty:
        cmp_ = []
        for y in range(2002, 2014):
            c, d_ = cap_all[cap_all.year == y], dole_df[dole_df.year == y]
            cmp_.append({"year": y, "cap": len(c), "dole": len(d_),
                         "cap_excl_ratification": int((c.instrument_type != "ratification").sum()),
                         "dole_excl_ratification": int((d_.instrument_type != "ratification").sum()),
                         "pct_diff_dole_vs_cap": round(100 * (len(d_) - len(c)) / len(c), 1) if len(c) else None})
        pd.DataFrame(cmp_).to_csv(D / "cap_vs_dole.csv", index=False)
        log.info("fr: wrote raw/fr/cap_vs_dole.csv")

    counts = []
    src_url = {SRC: BASE, "cap_fr": CAP_URL}
    for (y, it, og, sc), n in laws_df.groupby(["year", "instrument_type", "origin", "source"]).size().items():
        counts.append({"country": "FR", "year": y, "instrument_type": it, "origin": og, "n": n,
                       "source": sc, "source_url": src_url.get(sc, BASE)})
    for (y, it, sc), n in laws_df.groupby(["year", "instrument_type", "source"]).size().items():
        counts.append({"country": "FR", "year": y, "instrument_type": it, "origin": "all", "n": n,
                       "source": sc, "source_url": src_url.get(sc, BASE)})
    url = BASE

    # Sénat totals 1959-2001 (aggregate only; hors conventions = law, conventions = ratification)
    try:
        sen, sen_url = senat_origin_table()
    except Exception as e:  # noqa: BLE001
        log.warning("fr: Sénat statistics failed: %s", e)
        sen, sen_url = {}, None
    for y, r in sorted(sen.items()):
        if y > SENAT_LAST_YEAR:
            continue
        for it, og, n in (("law", "government", r["pjl"]), ("law", "parliament", r["ppl_an"] + r["ppl_senat"]),
                          ("law", "all", r["hors_conv"]), ("ratification", "all", r["conventions"])):
            counts.append({"country": "FR", "year": y, "instrument_type": it, "origin": og, "n": n,
                           "source": "senat_statistiques", "source_url": sen_url})
    if sen and not cap_all.empty:
        cmp_ = []
        for y in range(1979, 1995):
            c = cap_all[cap_all.year == y]
            r = sen.get(y, {})
            n_ex = int((c.instrument_type != "ratification").sum())
            cmp_.append({"year": y, "senat_hors_conventions": r.get("hors_conv"), "senat_total": r.get("total"),
                         "cap_total": len(c), "cap_excl_ratification": n_ex,
                         "pct_cap_vs_senat_total": round(100 * (len(c) - r["total"]) / r["total"], 1)
                         if r.get("total") else None,
                         "pct_cap_excl_rat_vs_senat_hors_conv": round(100 * (n_ex - r["hors_conv"]) / r["hors_conv"], 1)
                         if r.get("hors_conv") else None})
        pd.DataFrame(cmp_).to_csv(D / "senat_vs_cap.csv", index=False)
        log.info("fr: wrote raw/fr/senat_vs_cap.csv")
    for y in YEARS:
        counts.append({"country": "FR", "year": y, "instrument_type": "decree_law", "origin": "government",
                       "n": ords.get(y, 0), "source": SRC, "source_url": url})
    write_csv(pd.DataFrame(counts, columns=COUNTS_COLUMNS).sort_values(["year", "instrument_type", "origin"]),
              INTER / "counts_fr.csv")
    log.info("fr: %d laws %s-%s (origin known for %d); %d ordonnances 2002-",
             len(laws_df), laws_df.year.min(), laws_df.year.max(), (laws_df.origin != "unknown").sum(),
             sum(ords.values()))


if __name__ == "__main__":
    main()
