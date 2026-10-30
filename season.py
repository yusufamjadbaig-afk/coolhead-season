"""CoolHead over a whole cooling season, built on coolhead_model (model v2).

The one-day model compares roofs on a single day with fresh white paint. Over a summer, white
paint gets dirty and starts to peel, while the canopy gets dusty and its parts wear. This module
runs April to September for Faisalabad or Hong Kong, one typical day per month, and lets both
options age.

How it works
------------
1. Weather: one typical day per month from long-term averages (WEATHER, with sources). Sunshine
   hours turn into a "sun strength" with the FAO-56 Angstrom formula, so cloudy months get less sun.
2. Model runs: coolhead_model v2 is run in advance for every month and a grid of settings
   (season_grid.py writes season_grid.csv). The app then interpolates in that grid, so it answers
   instantly instead of re-running the model.
3. Ageing: white paint reflectance falls towards a dirty "floor" month by month, heavy-rain months
   wash some dirt off, and part of the roof can peel back to bare concrete. The canopy fabric gets
   dustier, wicks less well, and is sometimes not working (pump, battery or water problems).
   All ageing speeds are scenarios, not measurements; see PAINT_AGEING and CANOPY_UPKEEP.
4. Season totals: each month's typical day is multiplied by the days in the month.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

import coolhead_model as cm

MONTHS = (4, 5, 6, 7, 8, 9)
MONTH_NAMES = {4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep"}
DAYS = {4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30}
WIND = 2.0                 # m/s at roof level, the one-day model's default, used for every month
RAINY_MM = 100.0           # a month with at least this much rain counts as a "heavy rain" month

HONG_KONG = cm.Site("Hong Kong", lat=22.30, lon=114.17, alt=32, tz="Asia/Hong_Kong")

# ---------------- monthly weather ----------------
# Faisalabad: temperatures and humidity from the Wikipedia climate table for Faisalabad, 1980-2015
# (the same table the one-day model uses for June and July). Faisalabad has no published sunshine
# normals we could find, so sunshine hours are Lahore's (about 130 km away) from the Wikipedia
# "Climate of Lahore" table (NOAA, 1961-1990).
# Hong Kong: Hong Kong Observatory monthly normals 1991-2020 (sunshine measured at King's Park).
WEATHER = {
    "Faisalabad": dict(
        site=cm.FAISALABAD,
        months={4: dict(tmax=34.1, tmin=18.3, rh=26, rain_mm=24.8, sun_hours=256.1),
                5: dict(tmax=39.2, tmin=23.7, rh=21, rain_mm=15.1, sun_hours=308.3),
                6: dict(tmax=40.3, tmin=26.7, rh=18, rain_mm=55.9, sun_hours=269.0),
                7: dict(tmax=37.3, tmin=27.3, rh=63, rain_mm=92.0, sun_hours=227.5),
                8: dict(tmax=36.4, tmin=26.7, rh=55, rain_mm=83.7, sun_hours=234.9),
                9: dict(tmax=35.6, tmin=24.0, rh=57, rain_mm=58.1, sun_hours=265.6)},
        source="Temperature, humidity and rain: Wikipedia, Faisalabad climate table (1980-2015). "
               "Sunshine: Wikipedia, Climate of Lahore (NOAA 1961-1990), used because no Faisalabad "
               "sunshine normals were found."),
    "Hong Kong": dict(
        site=HONG_KONG,
        months={4: dict(tmax=25.6, tmin=21.1, dewpoint=19.7, rain_mm=153.0, sun_hours=113.2),
                5: dict(tmax=28.8, tmin=24.5, dewpoint=23.0, rain_mm=290.6, sun_hours=138.8),
                6: dict(tmax=30.7, tmin=26.5, dewpoint=24.9, rain_mm=491.5, sun_hours=144.3),
                7: dict(tmax=31.6, tmin=26.9, dewpoint=25.2, rain_mm=385.8, sun_hours=197.3),
                8: dict(tmax=31.3, tmin=26.7, dewpoint=25.1, rain_mm=453.2, sun_hours=182.1),
                9: dict(tmax=30.5, tmin=26.1, dewpoint=23.6, rain_mm=321.4, sun_hours=174.4)},
        source="Hong Kong Observatory, monthly meteorological normals 1991-2020."),
}
CITIES = tuple(WEATHER)


def dewpoint_from_rh(t, rh):
    """Dew point (C) from air temperature (C) and relative humidity (%), inverting cm.esat."""
    g = math.log(rh / 100.0) + 17.625 * t / (t + 243.04)
    return 243.04 * g / (17.625 - g)


def daylight_hours(lat, day_of_year):
    """Maximum possible sunshine hours N (FAO-56 equations 24, 25 and 34)."""
    phi = math.radians(lat)
    delta = 0.409 * math.sin(2 * math.pi / 365 * day_of_year - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    return 24 / math.pi * ws


def sun_factor(sun_hours_month, days, lat, alt, day_of_year):
    """Share of clear-sky sunlight on a typical day, from monthly sunshine hours.

    FAO-56 equation 35 (Angstrom, default a=0.25, b=0.50) gives Rs/Ra = 0.25 + 0.50 n/N, and
    equation 37 gives clear-sky Rso/Ra = 0.75 + 2e-5 z, so Rs/Rso is their ratio (at most 1).
    """
    n = sun_hours_month / days
    N = daylight_hours(lat, day_of_year)
    return min(1.0, (0.25 + 0.50 * n / N) / (0.75 + 2e-5 * alt))


def month_scenario(city, month) -> cm.Scenario:
    """The typical day for one month, as a coolhead_model Scenario."""
    w = WEATHER[city]
    site, m = w["site"], w["months"][month]
    tmean = (m["tmax"] + m["tmin"]) / 2
    dew = m["dewpoint"] if "dewpoint" in m else dewpoint_from_rh(tmean, m["rh"])
    doy = pd.Timestamp(f"2026-{month:02d}-15").dayofyear
    sf = sun_factor(m["sun_hours"], DAYS[month], site.lat, site.alt, doy)
    return cm.Scenario(date=f"2026-{month:02d}-15", tmax=m["tmax"], tmin=m["tmin"],
                       dewpoint=round(dew, 1), wind=WIND, sun_factor=round(sf, 3), site=site)


def weather_table(city):
    """The monthly typical-day inputs, for showing in the app."""
    rows = []
    for mo in MONTHS:
        sc = month_scenario(city, mo)
        rows.append(dict(month=MONTH_NAMES[mo], max_C=sc.tmax, min_C=sc.tmin, dewpoint_C=sc.dewpoint,
                         sun_strength=sc.sun_factor, rain_mm=WEATHER[city]["months"][mo]["rain_mm"]))
    return pd.DataFrame(rows)


# ---------------- the precomputed grid ----------------
WHITE_ABS = tuple(round(0.15 + 0.05 * i, 2) for i in range(12))      # 0.15 .. 0.70 (bare concrete)
DRY_ABS = (0.35, 0.45, 0.55)
WET_ABS = (0.45, 0.55, 0.65)
WET_FRACTION = (0.6, 0.8, 1.0)
WET_TRANS = (0.10, 0.20, 0.30)
SCHEDULES = {"08:00-19:00": "wet_canopy", "11:00-17:00": "wet_canopy_peak"}
METRICS = ("heat_in_Wh_m2_day", "water_L_m2_day", "peak_roof_C", "peak_ceiling_C")
GRID_FILE = Path(__file__).with_name("season_grid.csv")


def grid_jobs():
    """Every model run the season grid needs: (city, month, case, settings overrides)."""
    for city, month in itertools.product(CITIES, MONTHS):
        yield city, month, "bare", {}
        for a in WHITE_ABS:
            yield city, month, "white", dict(white_absorptance=a)
        for a in DRY_ABS:
            yield city, month, "dry_canopy", dict(dry_fabric_absorptance=a)
        for case in SCHEDULES.values():
            for a, f, t in itertools.product(WET_ABS, WET_FRACTION, WET_TRANS):
                yield city, month, case, dict(wet_fabric_absorptance=a, wet_fraction=f,
                                              wet_fabric_transmittance=t)


def run_job(job):
    """Run one grid job with model v2 and return a result row."""
    city, month, case, overrides = job
    _, s = cm.create_model("v2", **overrides).run(case, month_scenario(city, month))
    return dict(city=city, month=month, case=case, **overrides, **{k: float(s[k]) for k in METRICS})


def load_grid(path=GRID_FILE):
    return pd.read_csv(path)


class Grid:
    """Look-ups in the precomputed grid, with linear interpolation between grid points."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._white, self._dry, self._wet, self._bare = {}, {}, {}, {}
        for (city, month), g in df.groupby(["city", "month"]):
            self._bare[city, month] = g[g.case == "bare"][list(METRICS)].iloc[0].to_numpy()
            w = g[g.case == "white"].sort_values("white_absorptance")
            self._white[city, month] = (w.white_absorptance.to_numpy(), w[list(METRICS)].to_numpy())
            d = g[g.case == "dry_canopy"].sort_values("dry_fabric_absorptance")
            self._dry[city, month] = (d.dry_fabric_absorptance.to_numpy(), d[list(METRICS)].to_numpy())
            for sched, case in SCHEDULES.items():
                c = g[g.case == case]
                cube = np.full((len(WET_ABS), len(WET_FRACTION), len(WET_TRANS), len(METRICS)), np.nan)
                for _, r in c.iterrows():
                    i = WET_ABS.index(round(r.wet_fabric_absorptance, 2))
                    j = WET_FRACTION.index(round(r.wet_fraction, 2))
                    k = WET_TRANS.index(round(r.wet_fabric_transmittance, 2))
                    cube[i, j, k] = r[list(METRICS)].to_numpy(dtype=float)
                self._wet[city, month, sched] = cube

    @staticmethod
    def _interp1(x, xs, table):
        x = min(max(x, xs[0]), xs[-1])
        return np.array([np.interp(x, xs, table[:, m]) for m in range(table.shape[1])])

    def bare(self, city, month):
        return dict(zip(METRICS, self._bare[city, month]))

    def white(self, city, month, absorptance):
        xs, table = self._white[city, month]
        return dict(zip(METRICS, self._interp1(absorptance, xs, table)))

    def dry(self, city, month, absorptance):
        xs, table = self._dry[city, month]
        return dict(zip(METRICS, self._interp1(absorptance, xs, table)))

    def wet(self, city, month, schedule, absorptance, wet_fraction, transmittance):
        cube = self._wet[city, month, schedule]
        axes = (WET_ABS, WET_FRACTION, WET_TRANS)
        point = (absorptance, wet_fraction, transmittance)
        # multilinear interpolation: collapse one axis at a time, from the last to the first
        arr = cube
        for ax in reversed(range(3)):
            xs = np.array(axes[ax])
            x = min(max(point[ax], xs[0]), xs[-1])
            arr = np.apply_along_axis(lambda v: np.interp(x, xs, v), ax, arr)
        return dict(zip(METRICS, arr))


# ---------------- ageing scenarios ----------------
@dataclass(frozen=True)
class PaintAgeing:
    """Reflectance falls from its current value towards `floor` with time constant `tau_months`;
    `peel_per_season` is the share of the roof back to bare concrete after six months."""
    floor: float
    tau_months: float
    peel_per_season: float
    description: str


PAINT_AGEING = {
    "Slow": PaintAgeing(0.65, 12.0, 0.00,
                        "Similar to a US study, where a bright white roof fell from 0.85 to about 0.65 "
                        "reflectance over three years (Levinson, LBNL, 2009)."),
    "Medium": PaintAgeing(0.55, 6.0, 0.05,
                          "Dustier than the US study: most of the loss happens within a year, and a "
                          "little peeling."),
    "Fast": PaintAgeing(0.45, 3.0, 0.10,
                        "Very dusty roof or cheap whitewash. In Pakistan, a whitewash treatment needed "
                        "redoing about every three months (UN-Habitat Pakistan, 2010)."),
}


@dataclass(frozen=True)
class CanopyUpkeep:
    """Canopy condition by the end of the season (it starts clean): wet and dry fabric solar
    absorptance, wetness factor, and the share of days it is not working."""
    wet_abs_end: float
    dry_abs_end: float
    wet_fraction_end: float
    days_not_working: float
    description: str


CANOPY_UPKEEP = {
    "Well kept": CanopyUpkeep(0.45, 0.35, 1.0, 0.02,
                              "Fabric rinsed often, tank topped up, faults fixed quickly."),
    "Some upkeep": CanopyUpkeep(0.55, 0.45, 0.8, 0.05,
                                "Some dust and salt build up on the cloth; it wicks a bit less well."),
    "Neglected": CanopyUpkeep(0.65, 0.55, 0.6, 0.15,
                              "Rarely cleaned; the cloth is dusty and patchy, and the pump or water "
                              "runs out on about 1 day in 7."),
}


@dataclass(frozen=True)
class Options:
    city: str = "Faisalabad"
    # white paint
    paint_reflectance_new: float = 0.80
    months_since_painting: int = 0
    paint_ageing: str = "Medium"
    repaint_every_months: int = 0          # 0 = not repainted during the season
    rain_wash: float = 0.3                 # share of the lost reflectance won back in a heavy-rain month
    # canopy
    canopy_upkeep: str = "Some upkeep"
    wet_transmittance: float = 0.20
    schedule: str = "08:00-19:00"


def _age(r, months, ageing: PaintAgeing):
    return ageing.floor + (r - ageing.floor) * math.exp(-months / ageing.tau_months)


def paint_path(opt: Options):
    """Month-by-month white paint reflectance and peeled share (mid-month values), plus how many
    times it is painted during the season (including at the start if it is new)."""
    ageing = PAINT_AGEING[opt.paint_ageing]
    r0 = opt.paint_reflectance_new
    peel_rate = ageing.peel_per_season / 6.0
    r = _age(r0, opt.months_since_painting, ageing) if opt.months_since_painting else r0
    peel = min(0.5, peel_rate * opt.months_since_painting)
    paintings = 0 if opt.months_since_painting else 1
    rows = []
    for i, month in enumerate(MONTHS):
        if opt.repaint_every_months and i > 0 and i % opt.repaint_every_months == 0:
            r, peel, paintings = r0, 0.0, paintings + 1
        rows.append(dict(month=month, reflectance=_age(r, 0.5, ageing),
                         peeled=min(0.5, peel + peel_rate * 0.5)))
        r, peel = _age(r, 1.0, ageing), min(0.5, peel + peel_rate)
        if WEATHER[opt.city]["months"][month]["rain_mm"] >= RAINY_MM:
            r = r + opt.rain_wash * (r0 - r)
    return pd.DataFrame(rows), paintings


def canopy_path(opt: Options):
    """Month-by-month canopy condition (mid-month values): it starts clean and reaches the
    upkeep scenario's end values by the end of the season."""
    up = CANOPY_UPKEEP[opt.canopy_upkeep]
    start = cm.default_settings("v2")
    rows = []
    for i, month in enumerate(MONTHS):
        f = (i + 0.5) / len(MONTHS)
        rows.append(dict(month=month,
                         wet_abs=start.wet_fabric_absorptance + f * (up.wet_abs_end - start.wet_fabric_absorptance),
                         dry_abs=start.dry_fabric_absorptance + f * (up.dry_abs_end - start.dry_fabric_absorptance),
                         wet_fraction=1.0 + f * (up.wet_fraction_end - 1.0),
                         days_not_working=up.days_not_working))
    return pd.DataFrame(rows)


OPTION_NAMES = {"bare": "Bare concrete", "white": "White paint", "dry_canopy": "Dry canopy",
                "wet_canopy": "CoolHead (wet canopy)"}


def monthly_results(grid: Grid, opt: Options) -> pd.DataFrame:
    """Typical-day results for each option and month, with the ageing applied."""
    paint, _ = paint_path(opt)
    canopy = canopy_path(opt)
    bare_abs = cm.default_settings("v2").bare_absorptance
    rows = []
    for (_, p), (_, c) in zip(paint.iterrows(), canopy.iterrows()):
        m = int(p.month)
        days = DAYS[m]
        bare = grid.bare(opt.city, m)
        white = grid.white(opt.city, m, min(bare_abs, 1 - p.reflectance))
        white = {k: (1 - p.peeled) * white[k] + p.peeled * bare[k] for k in METRICS}
        dry = grid.dry(opt.city, m, c.dry_abs)
        wet_on = grid.wet(opt.city, m, opt.schedule, c.wet_abs, c.wet_fraction, opt.wet_transmittance)
        d = c.days_not_working
        wet = {k: (1 - d) * wet_on[k] + d * dry[k] for k in METRICS}
        wet["water_L_m2_day"] = (1 - d) * wet_on["water_L_m2_day"]
        for name, res in (("bare", bare), ("white", white), ("dry_canopy", dry), ("wet_canopy", wet)):
            rows.append(dict(month=m, month_name=MONTH_NAMES[m], days=days, option=name, **res,
                             paint_reflectance=p.reflectance if name == "white" else np.nan))
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class Money:
    """Prices for the cost comparison, per m² of roof unless stated."""
    currency: str = "Rs"
    electricity_per_kwh: float = 45.0      # NEPRA FY2025-26 base rate (Rs 38 for 301-400 units) + ~18% tax
    ac_cop: float = 3.0                    # heat removed per unit of electricity, typical split AC (assumption)
    roof_area_m2: float = 100.0
    paint_per_m2: float = 340.0            # one painting; middle of Rs 273-409 (cost sheet, Berger price)
    wet_canopy_per_m2: float = 2952.0      # fabric, frame, sheet, drip line (cost sheet)
    dry_canopy_per_m2: float = 2462.0      # the same without the drip line
    shared_set: float = 13620.0            # Arduino, sensors, solar panel, battery, pump, tank (one per roof)
    fabric_per_m2: float = 880.0           # 2 m of canvas per m² of canopy (cost sheet)
    fabric_every_seasons: float = 1.0      # untreated cotton weakens after one to two summers
    battery: float = 4240.0
    battery_every_seasons: float = 3.0     # sealed lead-acid: about 2-5 years in heat
    water_per_1000L: float = 0.0


MONEY_DEFAULTS = {
    "Faisalabad": Money(),
    # Hong Kong: CLP 2026 average net tariff HK$1.406 per kWh. Parts are the Pakistani prices
    # converted at about Rs 35.7 per HK$ until Hong Kong prices are added to the cost sheet.
    "Hong Kong": Money(currency="HK$", electricity_per_kwh=1.41, paint_per_m2=9.5,
                       wet_canopy_per_m2=82.7, dry_canopy_per_m2=69.0, shared_set=381.5,
                       fabric_per_m2=24.6, battery=118.8),
}


def season_summary(monthly: pd.DataFrame, opt: Options, money: Money) -> pd.DataFrame:
    """Season totals and money for each option, per m² of roof."""
    _, paintings = paint_path(opt)
    tot = (monthly.assign(heat_kwh=monthly.heat_in_Wh_m2_day * monthly.days / 1000,
                          water_l=monthly.water_L_m2_day * monthly.days)
           .groupby("option", sort=False)[["heat_kwh", "water_l"]].sum())
    bare = tot.loc["bare", "heat_kwh"]
    a = money.roof_area_m2
    setup = {"bare": 0.0,
             "white": money.paint_per_m2 if paintings and not opt.months_since_painting else 0.0,
             "dry_canopy": money.dry_canopy_per_m2,
             "wet_canopy": money.wet_canopy_per_m2 + money.shared_set / a}
    repaints = paintings - (0 if opt.months_since_painting else 1)
    upkeep = {"bare": 0.0,
              "white": money.paint_per_m2 * repaints,
              "dry_canopy": money.fabric_per_m2 / money.fabric_every_seasons,
              "wet_canopy": (money.fabric_per_m2 / money.fabric_every_seasons
                             + money.battery / money.battery_every_seasons / a
                             + tot.loc["wet_canopy", "water_l"] / 1000 * money.water_per_1000L)}
    rows = []
    for opt_name, r in tot.iterrows():
        kept_out = bare - r.heat_kwh
        elec = kept_out / money.ac_cop
        saved = elec * money.electricity_per_kwh
        net = saved - upkeep[opt_name]
        payback = setup[opt_name] / net if net > 0 and setup[opt_name] > 0 else np.nan
        rows.append(dict(option=opt_name, name=OPTION_NAMES[opt_name], heat_in_kwh_m2=r.heat_kwh,
                         heat_cut_pct=100 * kept_out / bare, ac_kwh_saved_m2=elec, money_saved_m2=saved,
                         water_l_m2=r.water_l, setup_m2=setup[opt_name], upkeep_m2=upkeep[opt_name],
                         payback_seasons=payback))
    return pd.DataFrame(rows)
