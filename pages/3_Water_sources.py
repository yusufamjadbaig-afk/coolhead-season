"""Where CoolHead's water comes from: shorter watering hours, rain off the roof and AC water.

A page of the CoolHead roof model app. The maths is in water_sources.py (next to app.py), which uses
the season model in season.py for how much water the wet canopy uses up each month.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))    # find season.py next to app.py

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import season as ss

st.set_page_config(page_title="CoolHead water sources", page_icon="🏠", layout="wide")


def load_water_sources():
    """Find water_sources.py next to app.py, or anywhere else in the repo (for example in pages/,
    or saved as 'water_sources (1).py' by the browser), and load it."""
    here = Path(__file__).resolve().parent
    candidates = [ROOT / "water_sources.py", here / "water_sources.py", ROOT / "tools" / "water_sources.py",
                  *sorted(ROOT.rglob("water_sources*.py"))]
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("water_sources", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            continue
        if hasattr(module, "WaterSettings"):            # the newer version that this page needs
            sys.modules["water_sources"] = module
            return module
    st.error("This page needs the newer **water_sources.py** in the main folder of the GitHub repo, next to "
             "season.py and app.py. Upload it there (replace any older copy), then reboot the app.")
    st.stop()


ws = load_water_sources()

LIGHT = dict(tank="#2a78d6", tap="#eb6834", rain="#1baf7a", ink2="#52514e", grid="#e1e0d9")
DARK = dict(tank="#3987e5", tap="#d95926", rain="#199e70", ink2="#c3c2b7", grid="#2c2c2a")
theme = getattr(getattr(st.context, "theme", None), "type", None)
COL = DARK if theme == "dark" else LIGHT
D = ws.WaterSettings()


@st.cache_resource(show_spinner=False)
def load_grid():
    return ss.Grid(ss.load_grid()) if ss.GRID_FILE.exists() else None


@st.cache_data(show_spinner=False)
def run(_grid, s: ws.WaterSettings):
    return ws.monthly_balance(_grid, s), ws.plans(_grid, s), ws.sensitivity(_grid, s)


# ---------------- sidebar ----------------
with st.sidebar:
    st.header("Watering")
    schedule = st.radio("Keep the canopy wet", list(ws.SCHEDULE_NAMES), index=1, horizontal=True,
                        format_func=ws.SCHEDULE_NAMES.get, key="schedule")
    rain_year = st.radio("Rain", list(ws.RAIN_YEARS), horizontal=True, key="rain_year",
                         help="Average year: long-term monthly rain. Dry spring: a year with less rain in "
                              "April to June.")

    st.header("Your home")
    canopy = st.slider("Canopy area (m²)", 5, 200, int(D.canopy_m2), 5, key="canopy",
                       help="Cover the hottest rooms only. The rest of the roof still collects rain.")
    roof = st.slider("Roof area that drains into the tank (m²)", 20, 300, int(D.roof_m2), 10, key="roof")
    tank = st.select_slider("Tank size (L)", [250, 500, 1000, 2000, 5000], int(D.tank_l), key="tank")
    runoff = st.slider("Share of roof rain that reaches the tank (%)", 50, 90, int(D.runoff * 100), 5,
                       help="0.6 to 0.8 for a concrete roof. The rest splashes off, dries, or goes out "
                            "with the first, dirtiest rain.")
    n_ac = st.number_input("ACs with their drain pipe into the tank (optional)", 0, 6, D.n_ac, key="n_ac",
                           help="AC water is an optional extra. ACs make very little water in dry April to "
                                "June, so it saves only about 225 L a summer for a 5 × 5 m canopy.")

    with st.expander("AC water and storms"):
        ac_dry = st.slider("AC water per AC, April to June (L a day)", 0.0, 10.0, D.ac_dry_l_day, 0.5,
                           help="Dry air: about 1 L a day for a home AC (Lancaster, 2010).")
        ac_humid = st.slider("AC water per AC, July to September (L a day)", 0.0, 70.0, D.ac_humid_l_day, 5.0,
                             help="Humid air: up to about 68 L a day for an AC running all day "
                                  "(Lancaster, 2010). Ours assumes about 9 hours a day.")
        storm = st.slider("Rain falls on this share of the rainy days (%)", 20, 100, int(D.storm_share * 100), 10,
                          help="Lower = fewer, bigger storms, so more water overflows a small tank.")

s = ws.WaterSettings(canopy_m2=float(canopy), roof_m2=float(roof), tank_l=float(tank), runoff=runoff / 100,
                     n_ac=int(n_ac), ac_dry_l_day=ac_dry, ac_humid_l_day=ac_humid, storm_share=storm / 100,
                     rain_year=rain_year, schedule=schedule)

# ---------------- results ----------------
st.title("Where CoolHead's water comes from")
st.caption(f"Model v2 · Faisalabad, April to September · {rain_year.lower()} · day-by-day tank balance · "
           "computer model, not measurements")

grid = load_grid()
if grid is None:
    st.error("season_grid.csv is missing. Run `python season_grid.py` once and upload the file it makes.")
    st.stop()
if roof < canopy:
    st.warning("The roof is smaller than the canopy. The canopy sits on the roof, so make the roof at least "
               "as big as the canopy.")

monthly, plan_table, sens = run(grid, s)
need, tap = monthly.need.sum(), monthly.tap.sum()
now = plan_table.tap_average.iloc[0]
cover = 1 - tap / need if need else 0.0
cut = 1 - tap / now if now else 0.0

src = "Rain and AC water cover" if n_ac else "Rain off the roof covers"
st.markdown(f"With these settings the canopy uses up **{need:,.0f} L** over the summer. {src} "
            f"**{cover:.0%}** of it, so **{tap:,.0f} L** comes from the tap: **{cut:.0%} less** than "
            f"watering from 08:00 to 19:00 with tap water only ({now:,.0f} L).")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Water the canopy uses up", f"{need:,.0f} L")
m1.caption(f"{need / canopy:,.0f} L per m² of canopy")
m2.metric("Rain collected", f"{monthly.rain_in.sum():,.0f} L")
m2.caption(f"{monthly.overflow.sum():,.0f} L overflowed a full tank")
m3.metric("AC water collected", f"{monthly.ac_in.sum():,.0f} L")
m3.caption("Mostly July to September, when the air is humid" if n_ac else "Optional: add ACs in the sidebar")
m4.metric("From the tap", f"{tap:,.0f} L")
m4.caption(f"{tap / canopy:,.0f} L per m² of canopy")

fig = go.Figure()
fig.add_bar(x=monthly.month_name, y=monthly.from_tank, name="From the tank (rain and AC water)" if n_ac else "From the tank (rain)",
            marker_color=COL["tank"], hovertemplate="%{y:,.0f} L")
fig.add_bar(x=monthly.month_name, y=monthly.tap, name="From the tap", marker_color=COL["tap"],
            hovertemplate="%{y:,.0f} L")
fig.add_scatter(x=monthly.month_name, y=monthly.rain_in + monthly.ac_in, name="Rain and AC water collected" if n_ac else "Rain collected",
                mode="markers", marker=dict(color=COL["rain"], size=11, symbol="diamond"),
                hovertemplate="%{y:,.0f} L")
fig.update_layout(barmode="stack", height=400, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), font=dict(color=COL["ink2"]),
                  yaxis_title="Litres per month")
fig.update_xaxes(gridcolor=COL["grid"])
fig.update_yaxes(gridcolor=COL["grid"], rangemode="tozero")
st.plotly_chart(fig, width="stretch")
st.caption("Tap water is needed in April to June, when there is little rain and the air is too dry for the AC "
           "to make much water. From July the monsoon rain fills the tank.")

tab_plans, tab_month, tab_what, tab_src = st.tabs(["Compare plans", "Month by month", "What if",
                                                   "Sources and assumptions"])
with tab_plans:
    t = plan_table.copy()
    show = pd.DataFrame({
        "Plan": t.plan,
        "Tap water, average year (L)": t.tap_average.map("{:,.0f}".format),
        "Tap water, dry spring (L)": t.tap_dry_spring.map("{:,.0f}".format),
        "Less tap water than now": [("-" if i == 0 else f"{100 * a:.0f}%" if round(100 * a) == round(100 * d)
                                     else f"{100 * d:.0f}% to {100 * a:.0f}%")
                                    for i, (a, d) in enumerate(zip(t.cut_average, t.cut_dry_spring))],
        "Heat cut over the season": t.heat_cut_pct.map("{:.0f}%".format)})
    st.dataframe(show, hide_index=True, width="stretch")
    st.caption("“Now” is watering from 08:00 to 19:00 with tap water only. Heat cut is the share of the bare "
               "roof's heat the wet canopy keeps out over the season (Summer season page).")

with tab_month:
    mt = pd.DataFrame({
        "Month": monthly.month_name, "Rain (mm)": monthly.rain_mm.round(1),
        "Canopy uses up (L)": monthly.need.round(0), "Rain collected (L)": monthly.rain_in.round(0),
        "AC water collected (L)": monthly.ac_in.round(0), "Overflowed (L)": monthly.overflow.round(0),
        "From the tap (L)": monthly.tap.round(0), "In the tank at month end (L)": monthly.tank_end.round(0)})
    st.dataframe(mt, hide_index=True, width="stretch")

with tab_what:
    st.markdown("Tap water in an average year when one setting changes and the others stay as you set them "
                "in the sidebar.")
    st.dataframe(pd.DataFrame({
        "Setting": sens.setting, "Value": sens.value, "From the tap (L)": sens.tap.map("{:,.0f}".format),
        "Less than now": sens.cut.map("{:.0%}".format),
        "Rain and AC water cover": sens.rain_ac_share.map("{:.0%}".format)}), hide_index=True, width="stretch",
        height=35 * (len(sens) + 1) + 3)
    st.caption("The bigger the canopy compared with the roof, the less of its water the rain can cover. "
               "AC water hardly changes the answer, because it comes in the months when rain already fills "
               "the tank.")

with tab_src:
    st.subheader("How it works")
    st.markdown(
        "Each day of April to September, the tank gets any rain caught on the roof and any AC water, up to "
        "the tank's size. The canopy then takes what it needs, and the tap tops up anything missing. Water "
        "that runs off the canopy goes back to the tank, so the canopy only uses up what evaporates.")
    st.subheader("Sources")
    st.dataframe(pd.DataFrame(ws.SOURCES, columns=["What", "Source"]), hide_index=True, width="stretch")
    st.subheader("Our assumptions")
    st.markdown(
        "- Example home: a 5 × 5 m (25 m²) canopy over the hottest rooms on a 100 m² roof, a 1,000 L covered tank.\n"
        "- Rain is the main water source. AC water is an optional extra: 1 L a day per AC from April to June "
        "and 25 L a day from July to September. The 68 L figure is "
        "for an AC running all day; ours runs about 9 hours.\n"
        "- Rain comes in a few big storms (half the listed rainy days), spread evenly through the month.\n"
        "- The tank starts empty on 1 April.\n"
        "- Measure your own AC's water with a bucket for an hour to check the AC numbers.")
