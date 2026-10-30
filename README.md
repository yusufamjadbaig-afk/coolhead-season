# CoolHead summer season app

A web app that compares a bare concrete roof, white roof paint, a dry shade canopy and the
CoolHead wet canopy over a whole cooling season (April to September) in Faisalabad and Hong Kong,
with white paint getting dirtier and the canopy wearing over time.

> These are **computer-model results**, not measurements.

## Built on Sofia's model

The roof physics and the one-day page (`app.py`, `coolhead_model.py`) are by **Sofia R.**, from
[github.com/maska007/coolhead](https://github.com/maska007/coolhead) (MIT License, see `LICENSE`).
They are copied here unchanged. The **Summer season** page is new: see `SEASON.md` for what it does,
its sources and its limits.

## Run it

```bash
pip install -r requirements-dev.txt
streamlit run app.py          # opens http://localhost:8501; pick "Summer season" in the menu
pytest                        # tests
python season_grid.py         # rebuild season_grid.csv after changing the weather or the model
```

## Deploy

Streamlit Community Cloud → **Create app** → this repository → branch `main` → main file `app.py`.
