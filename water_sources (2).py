"""Where the canopy's water could come from: shorter watering hours, rain off the roof and AC water.

Run it with:  python water_sources.py   (it sits next to season.py; the app's Water sources page uses it too)

Example home in Faisalabad, April to September: a canopy over the hottest rooms on a flat roof. Each day the
tank gets any rain caught on the roof and any AC water, then the canopy takes what it needs. If the tank
runs dry, the rest comes from the tap. Water that runs off the canopy goes back to the tank, so the canopy
only uses up what evaporates (the water figure from the season model).

Sources for the inputs
- Water the canopy evaporates each day, by month: season.py (the Summer season app), built on Sofia's
  CoolHead model v2 with FAO-56 evaporation equations and Faisalabad's monthly weather.
- Monthly rain, average year: the Wikipedia Faisalabad climate table (1980-2015) used in season.py.
- Monthly rain, dry-spring year, and the number of days with rain each month: weather2travel.com,
  "Faisalabad weather by month".
- Share of roof rain that reaches the tank: 0.6-0.8 for concrete (Rainwater Harvesting Trainers' Manual,
  Karnataka Urban Infrastructure Development and Finance Corporation, via India Water Portal).
- AC water: about 1 L a day for a home AC in dry weather and about 68 L a day in humid weather
  (Brad Lancaster, "Harvesting Air-Conditioning Condensate in Jeddah, Saudi Arabia, and Beyond", 2010).

Our own assumptions (not from a source; all are settings below)
- Canopy 20 m² on a 100 m² roof and a 1,000 L tank. Rain is the main water source; AC water is an optional
  extra (no ACs in the main plan, one AC in the optional row).
- AC water from July to September: 25 L a day (the 68 L figure is for an AC running all day; ours runs
  about 9 hours). From April to June: 1 L a day.
- Rain comes in a few big storms: half the listed rainy days, with the month's rain shared between them.
"""
from dataclasses import dataclass, replace

import pandas as pd

import season as ss

CITY = "Faisalabad"
DRY_MONTHS = (4, 5, 6)          # April to June: dry air, so an AC makes very little water
RAIN_YEARS = {
    "Average year": {m: ss.WEATHER[CITY]["months"][m]["rain_mm"] for m in ss.MONTHS},
    "Dry spring": {4: 14.0, 5: 14.0, 6: 24.0, 7: 108.0, 8: 92.0, 9: 33.0},
}
RAIN_DAYS = {4: 6, 5: 5, 6: 5, 7: 10, 8: 10, 9: 4}
SCHEDULE_NAMES = {"08:00-19:00": "08:00 to 19:00", "11:00-17:00": "11:00 to 17:00"}

SOURCES = [
    ("Water the canopy uses up", "season.py (Summer season app), built on Sofia's CoolHead model v2 with "
     "FAO-56 evaporation equations"),
    ("Rain, average year", "Wikipedia, Faisalabad climate table (1980-2015), as used in season.py"),
    ("Rain, dry-spring year, and days with rain", "weather2travel.com, Faisalabad weather by month"),
    ("Share of roof rain that reaches the tank (0.6-0.8 for concrete)",
     "Rainwater Harvesting Trainers' Manual (KUIDFC), via India Water Portal"),
    ("AC water: about 1 L a day in dry weather, about 68 L a day in humid weather",
     "Brad Lancaster, Harvesting Air-Conditioning Condensate in Jeddah, Saudi Arabia, and Beyond (2010)"),
]


@dataclass(frozen=True)
class WaterSettings:
    canopy_m2: float = 20.0         # canopy over the hottest rooms
    roof_m2: float = 100.0          # roof that drains into the tank (the canopy sits on it)
    tank_l: float = 1000.0
    runoff: float = 0.7             # share of the rain on the roof that reaches the tank
    n_ac: int = 0                   # AC water is optional: 0 in the main plan
    ac_dry_l_day: float = 1.0       # April to June
    ac_humid_l_day: float = 25.0    # July to September
    storm_share: float = 0.5        # storms = this share of the listed rainy days
    rain_year: str = "Average year"
    schedule: str = "11:00-17:00"
    use_rain: bool = True
    use_ac: bool = True


def canopy_water_per_day(grid, schedule):
    """Litres the wet canopy uses up per m² per day, by month, from the season model."""
    m = ss.monthly_results(grid, ss.Options(city=CITY, schedule=schedule))
    m = m[m.option == "wet_canopy"].set_index("month")
    return {mo: float(m.loc[mo, "water_L_m2_day"]) for mo in ss.MONTHS}


def heat_cut(grid, schedule):
    """Share of the bare roof's heat the wet canopy keeps out over the season (%)."""
    opt = ss.Options(city=CITY, schedule=schedule)
    s = ss.season_summary(ss.monthly_results(grid, opt), opt, ss.MONEY_DEFAULTS[CITY]).set_index("option")
    return float(s.loc["wet_canopy", "heat_cut_pct"])


def monthly_balance(grid, s: WaterSettings) -> pd.DataFrame:
    """Day-by-day tank balance, added up by month. Litres for the whole canopy."""
    per_day = canopy_water_per_day(grid, s.schedule)
    rain = RAIN_YEARS[s.rain_year]
    store = 0.0
    rows = []
    for mo in ss.MONTHS:
        days = ss.DAYS[mo]
        storms = max(1, round(RAIN_DAYS[mo] * s.storm_share))
        storm_days = {int((k + 0.5) * days / storms) for k in range(storms)}
        tot = dict(need=0.0, rain_in=0.0, ac_in=0.0, overflow=0.0, tap=0.0)
        for d in range(days):
            rain_in = rain[mo] / storms * s.roof_m2 * s.runoff if (s.use_rain and d in storm_days) else 0.0
            ac_in = (s.ac_dry_l_day if mo in DRY_MONTHS else s.ac_humid_l_day) * s.n_ac if s.use_ac else 0.0
            store += rain_in + ac_in
            overflow = max(0.0, store - s.tank_l)       # anything above the tank's size overflows
            store -= overflow
            want = per_day[mo] * s.canopy_m2
            got = min(want, store)
            store -= got
            for k, v in (("need", want), ("rain_in", rain_in), ("ac_in", ac_in), ("overflow", overflow),
                         ("tap", want - got)):
                tot[k] += v
        rows.append(dict(month=mo, month_name=ss.MONTH_NAMES[mo], rain_mm=rain[mo], **tot,
                         from_tank=tot["need"] - tot["tap"], tank_end=store))
    return pd.DataFrame(rows)


def season_total(grid, s: WaterSettings):
    """(litres the canopy uses up, litres from the tap) over April to September."""
    m = monthly_balance(grid, s)
    return float(m.need.sum()), float(m.tap.sum())


def plans(grid, s: WaterSettings) -> pd.DataFrame:
    """Tap water for the four plans, for both rain years, with the cut from watering 08:00-19:00 on tap water."""
    tap_only = dict(use_rain=False, use_ac=False)
    n_ac = max(1, s.n_ac)                       # the optional row always shows at least one AC
    now = season_total(grid, replace(s, schedule="08:00-19:00", **tap_only))[0]
    rows = [("Water 08:00 to 19:00, tap water only", "08:00-19:00", tap_only),
            (f"Water {SCHEDULE_NAMES[s.schedule]} only", s.schedule, tap_only),
            (f"Water {SCHEDULE_NAMES[s.schedule]} + rain from the roof (main plan)", s.schedule,
             dict(use_rain=True, use_ac=False)),
            (f"Water {SCHEDULE_NAMES[s.schedule]} + rain + water from {n_ac} AC{'s' if n_ac > 1 else ''} (optional)",
             s.schedule, dict(use_rain=True, use_ac=True, n_ac=n_ac))]
    out = []
    for name, sched, flags in rows:
        taps = {year: season_total(grid, replace(s, schedule=sched, rain_year=year, **flags))[1]
                for year in RAIN_YEARS}
        out.append(dict(plan=name, tap_average=taps["Average year"], tap_dry_spring=taps["Dry spring"],
                        cut_average=1 - taps["Average year"] / now, cut_dry_spring=1 - taps["Dry spring"] / now,
                        heat_cut_pct=heat_cut(grid, sched)))
    return pd.DataFrame(out)


def sensitivity(grid, s: WaterSettings) -> pd.DataFrame:
    """Tap water (average year) when one setting changes at a time."""
    tests = [("Roof catches this share of the rain", "runoff", (0.6, 0.7, 0.8), "{:.0%}"),
             ("Tank size", "tank_l", (500.0, 1000.0, 2000.0), "{:,.0f} L"),
             ("ACs with their drain pipe into the tank", "n_ac", (0, 1, 2), "{:.0f}"),
             ("Canopy size", "canopy_m2", (20.0, 50.0, 100.0), "{:.0f} m²")]
    rows = []
    for label, field, values, fmt in tests:
        for v in values:
            t = replace(s, **{field: v}, rain_year="Average year")
            need, tap = season_total(grid, t)
            now = season_total(grid, replace(t, schedule="08:00-19:00", use_rain=False, use_ac=False))[0]
            rows.append(dict(setting=label, value=fmt.format(v), tap=tap, cut=1 - tap / now,
                             rain_ac_share=1 - tap / need))
    return pd.DataFrame(rows)


def main():
    grid = ss.Grid(ss.load_grid())
    s = WaterSettings()
    print(f"{CITY}, April-September: {s.canopy_m2:.0f} m² canopy, {s.roof_m2:.0f} m² roof, {s.tank_l:,.0f} L tank, "
          f"roof catches {s.runoff:.0%} of rain, " + (f"{s.n_ac} AC(s)" if s.n_ac else "no AC water (optional extra)") + "\n")
    p = plans(grid, s)
    print(f"{'Plan':60s} {'Tap, average year':>18s} {'Tap, dry spring':>16s} {'Cut':>9s} {'Heat cut':>9s}")
    for r in p.itertuples():
        cut = "-" if r.Index == 0 else f"{100 * r.cut_dry_spring:.0f}-{100 * r.cut_average:.0f}%"
        print(f"{r.plan:60s} {r.tap_average:16,.0f} L {r.tap_dry_spring:14,.0f} L {cut:>9s} {r.heat_cut_pct:8.0f}%")
    print("\nPer m² of canopy (litres per summer):",
          " -> ".join(f"{r.tap_average / s.canopy_m2:.0f}" for r in p.itertuples()),
          f"(dry spring {p.tap_dry_spring.iloc[-1] / s.canopy_m2:.0f})")
    print("\nTap water still needed by month, average year:")
    for r in monthly_balance(grid, s).itertuples():
        print(f"  {r.month_name}: need {r.need:6,.0f} L  rain in {r.rain_in:6,.0f} L  AC in {r.ac_in:4,.0f} L  "
              f"tap {r.tap:6,.0f} L")
    print("\nHow much the answer depends on our assumptions (tap water, average year):")
    for r in sensitivity(grid, s).itertuples():
        print(f"  {r.setting}: {r.value:>14s} -> {r.tap:7,.0f} L from the tap, {100 * r.cut:.0f}% less than now, "
              f"rain and AC cover {100 * r.rain_ac_share:.0f}%")


if __name__ == "__main__":
    main()
