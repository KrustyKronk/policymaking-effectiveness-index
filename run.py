"""Orchestrator for the Policymaking Effectiveness Index pipeline.

    uv run python run.py --fetch            # all fetchers (ready-made + national)
    uv run python run.py --fetch uk es      # selected fetchers
    uv run python run.py --normalise        # laws, cabinets, context -> data/*.csv
    uv run python run.py --score            # params.yaml -> data/pei_country_year.csv, data/pei_cabinet.csv
    uv run python run.py --build            # pei.duckdb
    uv run python run.py --artifact         # artifact/pei-explorer.html (interactive page)
    uv run python run.py --all
"""
from __future__ import annotations

import argparse
import importlib
import sys
import traceback

GROUPS = {
    "v0": ["readymade", "uk", "es", "ie", "dk", "pl", "at", "nl", "se", "fr", "de", "it"],
    "easy": ["si", "cz", "ee", "hu", "fi", "no", "is_"],
    "medium": ["lu", "ch", "cy", "mt", "ro", "sk", "hr"],
    "hard": ["bg", "lt", "gr", "lv"],
}
FETCHERS = [m for g in GROUPS.values() for m in g]
NORMALISERS = ["normalise_cabinets", "normalise_context", "normalise_laws", "normalise_budgets"]


def run_module(name: str) -> bool:
    try:
        mod = importlib.import_module(name)
        mod.main()
        return True
    except Exception:  # noqa: BLE001
        print(f"\n!!! {name} failed:\n{traceback.format_exc()}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", nargs="*", metavar="SOURCE")
    ap.add_argument("--fetch-group", choices=list(GROUPS))
    ap.add_argument("--normalise", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--artifact", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    failed: list[str] = []
    if a.fetch_group:
        a.fetch = GROUPS[a.fetch_group]
    if a.all or a.fetch is not None:
        names = a.fetch if a.fetch else FETCHERS
        for n in names:
            if not run_module(f"pipeline.fetch.{n}"):
                failed.append(f"fetch:{n}")
    if a.all or a.normalise:
        for n in NORMALISERS:
            if not run_module(f"pipeline.{n}"):
                failed.append(n)
    if a.all or a.score:
        if not run_module("pipeline.score"):
            failed.append("score")
    if a.all or a.build:
        if not run_module("pipeline.build_duckdb"):
            failed.append("build")
    if a.all or a.artifact:
        if not run_module("pipeline.export_artifact"):
            failed.append("artifact")
    if failed:
        print("FAILED:", ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
