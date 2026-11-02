"""Where the canopy's water could come from: tap water saved by shorter watering hours, rain and AC water.

Run from the repo folder:  python tools/water_sources.py

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

Our own assumptions (not from a source; change them below)
- Canopy 20 m² on a 100 m² roof, a 1,000 L tank and one AC.
- AC water from July to September: 25 L a day (the 68 L figure is for an AC running all day; ours runs
  about 9 hours). From April to June: 1 L a day.
- Rain comes in a few big storms: half the listed rainy days, with the month's rain shared between them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import season as ss  # noqa: E402

CITY = "Faisalabad"
CANOPY_M2 = 20.0
ROOF_M2 = 100.0
TANK_L = 1000.0
RUNOFF = 0.7                    # middle of 0.6-0.8 for a concrete roof
N_AC = 1
AC_DRY_L_DAY = 1.0              # April-June
AC_HUMID_L_DAY = 25.0           # July-September
STORM_SHARE = 0.5               # storms = this share of the listed rainy days

RAIN_AVG = {m: ss.WEATHER[CITY]["months"][m]["rain_mm"] for m in ss.MONTHS}
RAIN_DRY_SPRING = {4: 14, 5: 14, 6: 24, 7: 108, 8: 92, 9: 33}
RAIN_DAYS = {4: 6, 5: 5, 6: 5, 7: 10, 8: 10, 9: 4}


def canopy_water_per_day(grid, schedule):
    """Litres per m² of canopy per day, by month, from the season model."""
    m = ss.monthly_results(grid, ss.Options(city=CITY, schedule=schedule))
    m = m[m.option == "wet_canopy"].set_index("month")
    return {mo: float(m.loc[mo, "water_L_m2_day"]) for mo in ss.MONTHS}


def heat_cut(grid, schedule):
    opt = ss.Options(city=CITY, schedule=schedule)
    s = ss.season_summary(ss.monthly_results(grid, opt), opt, ss.MONEY_DEFAULTS[CITY]).set_index("option")
    return float(s.loc["wet_canopy", "heat_cut_pct"])


def simulate(demand, rain, use_rain=True, use_ac=True, canopy=CANOPY_M2, roof=ROOF_M2, tank=TANK_L,
             runoff=RUNOFF, ac_humid=AC_HUMID_L_DAY):
    """Day-by-day tank balance. Returns (litres the canopy needs, litres from the tap, tap litres by month)."""
    store = need = tap = 0.0
    tap_by_month = {}
    for mo in ss.MONTHS:
        days = ss.DAYS[mo]
        storms = max(1, round(RAIN_DAYS[mo] * STORM_SHARE))
        storm_days = {int((k + 0.5) * days / storms) for k in range(storms)}
        month_tap = 0.0
        for d in range(days):
            rain_in = rain[mo] / storms * roof * runoff if (use_rain and d in storm_days) else 0.0
            ac_in = (AC_DRY_L_DAY if mo <= 6 else ac_humid) * N_AC if use_ac else 0.0
            store = min(tank, store + rain_in + ac_in)       # anything above the tank's size overflows
            want = demand[mo] * canopy
            got = min(want, store)
            store -= got
            need += want
            month_tap += want - got
        tap += month_tap
        tap_by_month[ss.MONTH_NAMES[mo]] = month_tap
    return need, tap, tap_by_month


def main():
    grid = ss.Grid(ss.load_grid())
    all_day = canopy_water_per_day(grid, "08:00-19:00")
    peak = canopy_water_per_day(grid, "11:00-17:00")
    cut_all, cut_peak = heat_cut(grid, "08:00-19:00"), heat_cut(grid, "11:00-17:00")

    base, _, _ = simulate(all_day, RAIN_AVG, use_rain=False, use_ac=False)
    short, _, _ = simulate(peak, RAIN_AVG, use_rain=False, use_ac=False)
    print(f"{CITY}, April-September: {CANOPY_M2:.0f} m² canopy, {ROOF_M2:.0f} m² roof, {TANK_L:.0f} L tank, "
          f"{N_AC} AC, roof catches {RUNOFF:.0%} of rain\n")
    print(f"{'Plan':58s} {'Tap water':>16s} {'Cut':>9s} {'Heat cut':>9s}")
    print(f"{'Water 08:00-19:00, tap water only':58s} {base:13,.0f} L {'-':>9s} {cut_all:8.0f}%")
    print(f"{'Water 11:00-17:00 only':58s} {short:13,.0f} L {100 * (1 - short / base):8.0f}% {cut_peak:8.0f}%")
    for label, use_ac in (("11:00-17:00 + rain from the whole roof", False), ("... + AC water", True)):
        taps = [simulate(peak, rain, use_ac=use_ac)[1] for rain in (RAIN_AVG, RAIN_DRY_SPRING)]
        lo, hi = min(taps), max(taps)
        print(f"{label:58s} {lo:6,.0f}-{hi:6,.0f} L {100 * (1 - hi / base):3.0f}-{100 * (1 - lo / base):.0f}% "
              f"{cut_peak:8.0f}%")
    print("(ranges: average year to dry-spring year)\n")

    print("Per m² of canopy (litres per summer):")
    tap_avg = simulate(peak, RAIN_AVG)[1] / CANOPY_M2
    tap_dry = simulate(peak, RAIN_DRY_SPRING)[1] / CANOPY_M2
    print(f"  {base / CANOPY_M2:.0f} -> {short / CANOPY_M2:.0f} -> {tap_avg:.0f}-{tap_dry:.0f} with rain and AC water\n")

    print("Tap water still needed, by month (average year, with rain and AC water):")
    for name, litres in simulate(peak, RAIN_AVG)[2].items():
        print(f"  {name}: {litres:,.0f} L")

    print("\nHow much the answer depends on our assumptions (tap water, average year):")
    for runoff in (0.6, 0.7, 0.8):
        print(f"  roof catches {runoff:.0%} of rain: {simulate(peak, RAIN_AVG, runoff=runoff)[1]:,.0f} L")
    for tank in (500, 1000, 2000):
        print(f"  {tank:,} L tank: {simulate(peak, RAIN_AVG, tank=tank)[1]:,.0f} L")
    for ac in (10, 25, 40):
        print(f"  AC gives {ac} L a day in Jul-Sep: {simulate(peak, RAIN_AVG, ac_humid=ac)[1]:,.0f} L")
    for canopy in (20, 50, 100):
        b, _, _ = simulate(all_day, RAIN_AVG, use_rain=False, use_ac=False, canopy=canopy)
        n, t, _ = simulate(peak, RAIN_AVG, canopy=canopy)
        print(f"  {canopy} m² canopy: {t:,.0f} L from the tap, {100 * (1 - t / b):.0f}% less than now, "
              f"rain and AC cover {100 * (1 - t / n):.0f}% of what it needs")


if __name__ == "__main__":
    main()
