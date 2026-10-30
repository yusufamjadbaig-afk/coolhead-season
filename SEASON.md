# Summer season page

The main page compares roofs on one hot day with fresh white paint. The **Summer season** page
runs the same model (v2) from April to September, one typical day per month, and lets both
options age: white paint gets dirty and can peel, and the CoolHead canopy gets dusty, wicks less
well and sometimes stops working.

## Files

| File | What it is |
|---|---|
| `pages/2_Summer_season.py` | The app page. Streamlit adds every file in `pages/` to the menu. |
| `season.py` | Monthly weather, ageing scenarios, interpolation and season totals. |
| `season_grid.py` | Runs the model for every month, city and setting the page needs (about 10 minutes). |
| `season_grid.csv` | The saved results of `season_grid.py`. The page reads this, so it answers instantly. |
| `tests/test_season.py` | Tests for the season maths and the page. |

Re-run `python season_grid.py` whenever the weather in `season.py` or the physics in
`coolhead_model.py` changes, then upload the new `season_grid.csv`.

## Inputs and sources

- **Faisalabad weather:** temperature, humidity and rain from the Wikipedia climate table for
  Faisalabad (1980–2015), the same table the main page uses. Sunshine hours are Lahore's
  (Wikipedia, Climate of Lahore; NOAA 1961–1990), because no Faisalabad sunshine normals were found.
- **Hong Kong weather:** Hong Kong Observatory monthly normals, 1991–2020.
- **Sun strength:** monthly sunshine hours → share of clear-sky sunlight with the FAO-56 Angstrom
  formula (Allen et al., 1998, equations 24, 25, 34, 35, 37).
- **White paint ageing:** reflectance falls towards a dirty level. "Slow" matches a US study where a
  bright white roof fell from 0.85 to about 0.65 in three years (Levinson, LBNL, 2009); "Fast" is
  close to the whitewash in Pakistan that needed redoing about every three months (UN-Habitat
  Pakistan, 2010). "Medium" sits between them. These are scenarios, not measurements.
- **Canopy upkeep:** the cloth starts clean and gets dustier and wicks less well by September;
  "days not working" act like a dry canopy. Also scenarios.
- **Money:** heat kept out ÷ AC efficiency (3, an assumption) × electricity price (Pakistan: NEPRA
  FY2025-26 base rate plus about 18% tax ≈ Rs 45 per kWh; Hong Kong: CLP 2026 average net tariff
  HK$1.41 per kWh). Part prices from the CoolHead cost sheet (29 Oct 2026). Cotton weakens after one
  to two summers in sun (VDL Hapro); sealed lead-acid batteries last about 2–5 years in heat.

## Limits

- One average day per month: heatwaves, dust storms and cloudy spells are averaged out.
- Winter is not modelled; the room is held at 26 °C as in the main page.
- Ageing speeds and canopy wear are scenarios chosen to cover a range, not measured.
- The controller, pump and tank are priced for a 1 m² test panel; a whole roof needs bigger ones.

The season code was written with Claude (Anthropic, 2026) and checked by the CoolHeads team.
