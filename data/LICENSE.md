# Data licence

The code in this repository is MIT-licensed (see `LICENSE` at the root). The data files in `data/`, the explorer data in `artifact/`, and the findings documents are licensed under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0** ([CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)).

The data uses that licence because part of the law series comes from the [Comparative Agendas Project](https://www.comparativeagendas.net/pages/Copyright-and-Legal), whose datasets are CC BY-NC-SA 4.0. Anything built from them must carry the same terms.

## What is included

- `pei_country_year.csv`: index and pillar scores per country and year.
- `pei_cabinet.csv`: the same, averaged per government.
- `budgets.csv`: budget adoption dates, compiled by hand with one source per row.
- `laws_coverage.csv`: which law source covers each country and year.
- `cabinets.csv`, `context.csv` and `intermediate/*_country_year.csv`: inputs to the scoring step.

Row-level law records (`laws.csv`, `intermediate/laws_*.csv`) and raw downloads are not included. `run.py --fetch` and `--normalise` rebuild them from the original sources.

## Sources to cite

If you use these data, please also cite the underlying sources:

- **Governments and caretaker periods:** REPDEM Basic dataset (v2026.07), repdem.org; ParlGov (Döring and Manow), parlgov.org.
- **Laws:** each country's parliament or official gazette (listed in `README.md`); the Comparative Agendas Project (comparativeagendas.net, see its How to cite page).
- **Context:** World Bank Worldwide Governance Indicators (CC BY 4.0); POLCON (Henisz, Wharton); Database of Political Institutions (Inter-American Development Bank); Sustainable Governance Indicators (Bertelsmann Stiftung); OECD Indicators of Regulatory Policy and Governance; Open Budget Survey (International Budget Partnership).
