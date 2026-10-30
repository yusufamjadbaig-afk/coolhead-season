"""CoolHead over a whole summer: white paint and the canopy as they age.

A page of the CoolHead roof model app (Streamlit puts every file in pages/ in the menu).
It reads season_grid.csv, made by season_grid.py, and does the season maths in season.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))    # find season.py next to app.py

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import season as ss

st.set_page_config(page_title="CoolHead summer season", page_icon="🏠", layout="wide")

# same colours as the main page
LIGHT = dict(bare="#eb6834", white="#eda100", dry_canopy="#1baf7a", wet_canopy="#2a78d6",
             ink="#0b0b0b", ink2="#52514e", grid="#e1e0d9")
DARK = dict(bare="#d95926", white="#c98500", dry_canopy="#199e70", wet_canopy="#3987e5",
            ink="#f0efec", ink2="#c3c2b7", grid="#2c2c2a")
theme = getattr(getattr(st.context, "theme", None), "type", None)
COL = DARK if theme == "dark" else LIGHT
NAME = ss.OPTION_NAMES
ORDER = ["bare", "white", "dry_canopy", "wet_canopy"]


@st.cache_resource(show_spinner=False)
def load_grid():
    return ss.Grid(ss.load_grid()) if ss.GRID_FILE.exists() else None


def base_layout(fig, height=420, **kw):
    layout = dict(height=height, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), font=dict(color=COL["ink2"]))
    fig.update_layout(**{**layout, **kw})
    fig.update_xaxes(gridcolor=COL["grid"], zeroline=False)
    fig.update_yaxes(gridcolor=COL["grid"], zeroline=False)
    return fig


# ---------------- sidebar ----------------
with st.sidebar:
    st.header("Place")
    city = st.radio("City", ss.CITIES, horizontal=True)

    st.header("White paint")
    refl_new = st.slider("Reflectance when new", 0.60, 0.90, 0.80, 0.01,
                         help="Share of sunlight a fresh white roof reflects. New white roofs reflect "
                              "about 0.70 to 0.85.")
    since = st.slider("Months since it was painted, on 1 April", 0, 12, 0,
                      help="0 means it is freshly painted at the start of the season.")
    ageing = st.radio("How fast it gets dirty", list(ss.PAINT_AGEING), index=1,
                      captions=[a.description for a in ss.PAINT_AGEING.values()])
    repaint = st.selectbox("Repainted during the season", [0, 3, 2],
                           format_func={0: "No", 3: "Every 3 months", 2: "Every 2 months"}.get)
    rain = st.slider("Dirt washed off in a heavy-rain month (%)", 0, 60, 30, 5,
                     help=f"Only months with at least {ss.RAINY_MM:.0f} mm of rain. In the long-term "
                          "averages, Faisalabad has none and Hong Kong has all six. This share is a guess.")

    st.header("CoolHead canopy")
    upkeep = st.radio("Upkeep", list(ss.CANOPY_UPKEEP), index=1,
                      captions=[u.description for u in ss.CANOPY_UPKEEP.values()])
    trans = st.select_slider("Sunlight through the wet cloth", [0.10, 0.15, 0.20, 0.25, 0.30], 0.20,
                             format_func=lambda v: f"{v:.0%}",
                             help="The biggest unknown in the model. We will measure it with a light meter.")
    schedule = st.radio("Kept wet", list(ss.SCHEDULES), horizontal=True)

    md = ss.MONEY_DEFAULTS[city]
    cur = md.currency
    with st.expander("Prices and your home"):
        st.caption("Pakistan prices come from our cost sheet (29 Oct 2026). Hong Kong part prices are the "
                   "Pakistani ones converted until we have Hong Kong quotes.")
        k = city
        area = st.number_input("Roof area (m²)", 10.0, 1000.0, md.roof_area_m2, 10.0, key=f"{k}area")
        elec = st.number_input(f"Electricity price ({cur} per kWh)", 0.0, 500.0, md.electricity_per_kwh,
                               key=f"{k}elec")
        cop = st.number_input("Air conditioner efficiency (heat moved per unit of electricity)", 1.0, 6.0,
                              md.ac_cop, 0.1, key=f"{k}cop",
                              help="About 3 for a typical split AC, higher for an inverter AC. An assumption.")
        paint_cost = st.number_input(f"White paint, one painting ({cur} per m²)", 0.0, 10000.0, md.paint_per_m2,
                                     key=f"{k}paint")
        wet_cost = st.number_input(f"Canopy parts ({cur} per m²)", 0.0, 100000.0, md.wet_canopy_per_m2,
                                   key=f"{k}wet")
        dry_cost = st.number_input(f"Shade-only canopy parts ({cur} per m²)", 0.0, 100000.0, md.dry_canopy_per_m2,
                                   key=f"{k}dry")
        shared = st.number_input(f"Controller, solar panel, battery, pump and tank ({cur}, one per roof)", 0.0,
                                 1e7, md.shared_set, key=f"{k}shared",
                                 help="Priced for a 1 m² test panel. A whole roof needs a bigger pump, tank "
                                      "and solar panel, so this is too low for a big roof.")
        fabric = st.number_input(f"New canvas ({cur} per m²)", 0.0, 10000.0, md.fabric_per_m2, key=f"{k}fab")
        fabric_n = st.number_input("Replace the canvas every … seasons", 0.5, 5.0, md.fabric_every_seasons, 0.5,
                                   key=f"{k}fabn", help="Untreated cotton weakens after one to two summers in sun.")
        battery = st.number_input(f"Battery ({cur})", 0.0, 1e6, md.battery, key=f"{k}bat")
        battery_n = st.number_input("Replace the battery every … seasons", 1.0, 10.0, md.battery_every_seasons, 1.0,
                                    key=f"{k}batn")
        water_price = st.number_input(f"Water price ({cur} per 1,000 L)", 0.0, 10000.0, md.water_per_1000L,
                                      key=f"{k}water")

money = ss.Money(currency=cur, electricity_per_kwh=elec, ac_cop=cop, roof_area_m2=area, paint_per_m2=paint_cost,
                 wet_canopy_per_m2=wet_cost, dry_canopy_per_m2=dry_cost, shared_set=shared, fabric_per_m2=fabric,
                 fabric_every_seasons=fabric_n, battery=battery, battery_every_seasons=battery_n,
                 water_per_1000L=water_price)
opt = ss.Options(city=city, paint_reflectance_new=refl_new, months_since_painting=since, paint_ageing=ageing,
                 repaint_every_months=repaint, rain_wash=rain / 100, canopy_upkeep=upkeep,
                 wet_transmittance=trans, schedule=schedule)

# ---------------- results ----------------
st.title("CoolHead over a whole summer")
st.caption(f"Model v2 · {city}, April to September · one typical day per month from long-term weather "
           "averages · computer model, not measurements")

grid = load_grid()
if grid is None:
    st.error("season_grid.csv is missing. Run `python season_grid.py` once and upload the file it makes.")
    st.stop()

monthly = ss.monthly_results(grid, opt)
summary = ss.season_summary(monthly, opt, money).set_index("option")
paint_months, paintings = ss.paint_path(opt)
w, c = summary.loc["white"], summary.loc["wet_canopy"]
gap = c.heat_cut_pct - w.heat_cut_pct
if abs(gap) < 2:
    lead = "the wet canopy and white paint keep out **about the same** heat over the season"
else:
    lead = f"**{'the wet canopy' if gap > 0 else 'white paint'}** keeps more heat out over the season"
st.markdown(f"With these settings, {lead}: **{c.heat_cut_pct:.0f}%** less heat into the room than a bare "
            f"roof for the wet canopy, against **{w.heat_cut_pct:.0f}%** for white paint.")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Heat cut over the season, white paint", f"{w.heat_cut_pct:.0f}%")
m1.caption(f"Paint reflectance {paint_months.reflectance.iloc[0]:.2f} in April, "
           f"{paint_months.reflectance.iloc[-1]:.2f} in September")
m2.metric("Heat cut over the season, CoolHead", f"{c.heat_cut_pct:.0f}%")
pts = round(abs(gap))
m2.caption(f"{pts} percentage point{'' if pts == 1 else 's'} {'more' if gap >= 0 else 'less'} than white paint")
m3.metric("Water used by CoolHead", f"{c.water_l_m2:,.0f} L per m²")
m3.caption(f"{c.water_l_m2 * area:,.0f} litres for a {area:,.0f} m² roof")
m4.metric("AC electricity saved by CoolHead", f"{c.ac_kwh_saved_m2:,.0f} kWh per m²")
m4.caption(f"About {c.money_saved_m2 * area:,.0f} {cur} for a {area:,.0f} m² roof")

tab_month, tab_money, tab_noac, tab_assume, tab_data = st.tabs(
    ["Month by month", "Season totals and cost", "Homes without AC", "What this assumes", "Data"])

with tab_month:
    left, right = st.columns([3, 2])
    fig = go.Figure()
    for o in ORDER:
        d = monthly[monthly.option == o]
        fig.add_scatter(x=d.month_name, y=d.heat_in_Wh_m2_day, name=NAME[o], mode="lines+markers",
                        line=dict(color=COL[o], width=2), marker=dict(size=8), hovertemplate="%{y:,.0f}")
    base_layout(fig, yaxis_title="Heat into the room per day (Wh per m² of roof)")
    fig.update_yaxes(rangemode="tozero")
    left.plotly_chart(fig, width="stretch")
    left.caption("Lower is better. Each point is a typical day in that month.")

    fig = go.Figure()
    fig.add_scatter(x=paint_months.month.map(ss.MONTH_NAMES), y=paint_months.reflectance, name="White paint",
                    mode="lines+markers", line=dict(color=COL["white"], width=2), marker=dict(size=8),
                    hovertemplate="%{y:.2f}")
    base_layout(fig, showlegend=False, yaxis_title="Share of sunlight the paint reflects",
                title=dict(text="White paint reflectance", x=0, font=dict(size=14)))
    fig.update_yaxes(range=[0.3, 0.95])
    right.plotly_chart(fig, width="stretch")
    peeled = paint_months.peeled.iloc[-1]
    right.caption(f"Peeled back to bare concrete by September: {peeled:.0%} of the roof. "
                  f"Painted {paintings} time(s) during the season.")

with tab_money:
    def fmt_money(v):
        return "–" if pd.isna(v) else f"{v:,.0f}"

    def fmt_payback(o):
        r = summary.loc[o]
        if o == "bare":
            return "–"
        if r.setup_m2 == 0:
            return "already paid"
        net = r.money_saved_m2 - r.upkeep_m2
        return "never" if net <= 0 else f"{r.setup_m2 / net:.1f}"

    table = pd.DataFrame({
        "Heat into room (kWh per m²)": summary.heat_in_kwh_m2.map(lambda v: f"{v:,.0f}"),
        "Cut vs bare": summary.heat_cut_pct.map(lambda v: f"{v:.0f}%"),
        "AC electricity saved (kWh per m²)": summary.ac_kwh_saved_m2.map(lambda v: f"{v:,.1f}"),
        f"Money saved ({cur} per m²)": summary.money_saved_m2.map(fmt_money),
        "Water (L per m²)": summary.water_l_m2.map(lambda v: f"{v:,.0f}"),
        f"Setup ({cur} per m²)": summary.setup_m2.map(fmt_money),
        f"Upkeep this season ({cur} per m²)": summary.upkeep_m2.map(fmt_money),
        "Pays back in (seasons)": [fmt_payback(o) for o in summary.index],
    })
    table.index = [NAME[o] for o in summary.index]
    st.dataframe(table.T, width="stretch")
    st.caption(f"Money saved assumes an air-conditioned room: the heat kept out ÷ AC efficiency ({cop:g}) × "
               f"electricity price ({elec:g} {cur} per kWh). Setup and upkeep use the prices in the sidebar. "
               "'Pays back in' = setup ÷ (money saved − upkeep) per season.")
    st.markdown(f"For a **{area:,.0f} m²** roof over the season, CoolHead would use about "
                f"**{c.water_l_m2 * area:,.0f} litres** of water and save about "
                f"**{c.ac_kwh_saved_m2 * area:,.0f} kWh** of AC electricity; white paint would save about "
                f"**{w.ac_kwh_saved_m2 * area:,.0f} kWh**.")

with tab_noac:
    fig = go.Figure()
    for o in ORDER:
        d = monthly[monthly.option == o]
        fig.add_scatter(x=d.month_name, y=d.peak_ceiling_C, name=NAME[o], mode="lines+markers",
                        line=dict(color=COL[o], width=2), marker=dict(size=8), hovertemplate="%{y:.1f} °C")
    base_layout(fig, yaxis_title="Hottest ceiling temperature (°C)")
    st.plotly_chart(fig, width="stretch")
    st.caption("A hot ceiling radiates heat onto the people below, so this matters most in homes without AC. "
               "The model keeps the room at 26 °C, so in a room without AC the ceiling would be hotter than "
               "shown. Treat this as a rough guide.")

with tab_assume:
    st.subheader("Weather: one typical day per month")
    wt = ss.weather_table(city).rename(columns={"month": "Month", "max_C": "Max °C", "min_C": "Min °C",
                                                "dewpoint_C": "Dew point °C", "sun_strength": "Sun strength",
                                                "rain_mm": "Rain (mm per month)"})
    st.dataframe(wt, hide_index=True, width="stretch")
    st.caption(ss.WEATHER[city]["source"] + " Sun strength is the share of clear-sky sunlight, from monthly "
               "sunshine hours with the FAO-56 Angstrom formula (Allen et al., 1998). Wind is 2 m/s in every month.")
    st.subheader("How the roofs age")
    st.markdown(
        "- **White paint** loses reflectance towards a dirty level month by month, part of the roof can peel "
        "back to bare concrete, and heavy rain washes some dirt off. Repainting resets it.\n"
        "- **The canopy** starts clean and gets dustier and wicks less well by September. On some days it is "
        "not working (pump, battery or water problems) and acts like a dry canopy.\n"
        "- These ageing speeds are **scenarios**, chosen to cover a range around the sources below. "
        "They are not measured in Faisalabad or Hong Kong.")
    st.dataframe(pd.DataFrame([dict(Scenario=k, **{"Dirty reflectance": a.floor, "Time constant (months)":
                                                    a.tau_months, "Peeled after 6 months": f"{a.peel_per_season:.0%}"})
                               for k, a in ss.PAINT_AGEING.items()]), hide_index=True, width="stretch")
    st.dataframe(pd.DataFrame([dict(Scenario=k, **{"Wet cloth absorbs by Sep": u.wet_abs_end,
                                                    "Wetness by Sep": u.wet_fraction_end,
                                                    "Days not working": f"{u.days_not_working:.0%}"})
                               for k, u in ss.CANOPY_UPKEEP.items()]), hide_index=True, width="stretch")
    st.subheader("Limits")
    st.markdown(
        "- Each month is one average day, not real day-by-day weather, so heatwaves and dust storms are averaged out.\n"
        "- Winter is left out: the model holds the room at 26 °C, which only makes sense in the cooling season.\n"
        "- The canopy's wear is simplified: cotton weakening, storm damage and pump failures appear only as "
        "dust, less wetting, days not working and replacement costs.\n"
        "- Costs are for one roof; a large roof needs a bigger pump, tank and solar panel than the price shown.")
    st.subheader("Sources")
    st.markdown(
        "- Levinson, R. (2009). *Cool roof Q&A* (draft). Lawrence Berkeley National Laboratory.\n"
        "- UN-Habitat Pakistan (2010). *Energy efficient housing: Improvement of thermal performance of RC slab roofs*.\n"
        "- NRDC (2020). *Frequently asked questions: Cool roofs* (India).\n"
        "- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration* (FAO Irrigation "
        "and Drainage Paper 56), equations 24, 25, 34, 35 and 37.\n"
        "- Hong Kong Observatory. *Monthly meteorological normals for Hong Kong (1991-2020)*.\n"
        "- NEPRA domestic tariff FY2025-26 (via billsonline.pk); CLP Power average net tariff 2026.\n"
        "- VDL Hapro. *Can a cotton tent fabric be damaged by UV radiation?* (cotton lifespan in sun).\n"
        "- CoolHead cost sheet, 29 Oct 2026 (Pakistani prices).")

with tab_data:
    out = monthly.drop(columns=["paint_reflectance"]).assign(option=monthly.option.map(NAME))
    st.dataframe(out.round(2), hide_index=True, width="stretch")
    st.download_button("Download month-by-month results (CSV)", out.to_csv(index=False).encode(),
                       f"coolhead_season_{city.replace(' ', '_').lower()}.csv", "text/csv")
