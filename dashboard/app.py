"""
BoxBoxF1Fantasy Dashboard

Race weekend management dashboard for F1 Fantasy predictions.
Shows MC simulation results, allows manual overrides (grid penalties, DNS, DNF),
and displays historical actual vs predicted comparisons.

Usage:
    streamlit run dashboard/app.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# Project imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from config.settings import (
    CURRENT_SEASON,
    PREDICTIONS_DIR,
    DATA_DIR,
    SEED_DIR,
    WEB_DATA_DIR,
    SPRINT_ROUNDS_2026,
    CANCELLED_ROUNDS_2026,
)
from config.fantasy_scoring import (
    QUALIFYING_POSITION_POINTS,
    RACE_POSITION_POINTS,
    PITSTOP_TIME_POINTS,
    FASTEST_PITSTOP_BONUS,
)


# ==============================================================================
# Data loading
# ==============================================================================

@st.cache_data
def load_drivers_info():
    with open(SEED_DIR / "drivers.json") as f:
        data = json.load(f)
    return {d["driver_id"]: d for d in data["drivers"]}


@st.cache_data
def load_constructors_info():
    with open(SEED_DIR / "constructors.json") as f:
        data = json.load(f)
    return {c["constructor_id"]: c for c in data["constructors"]}


@st.cache_data
def load_driver_ids():
    with open(SEED_DIR / "driver_ids.json") as f:
        return json.load(f)


@st.cache_data
def load_fantasy_prices():
    path = SEED_DIR / "fantasy_prices.json"
    if not path.exists():
        return {}, {}
    with open(path) as f:
        data = json.load(f)
    dp = {k: v["current_price"] for k, v in data.get("drivers", {}).items()}
    cp = {k: v["current_price"] for k, v in data.get("constructors", {}).items()}
    return dp, cp


def load_predictions(round_num):
    path = PREDICTIONS_DIR / f"round{round_num}" / "predictions.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def load_fantasy_points(round_num):
    path = PREDICTIONS_DIR / f"round{round_num}" / "fantasy_points.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def load_mc_results(round_num):
    path = PREDICTIONS_DIR / f"round{round_num}" / "monte_carlo_fantasy.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_actual_results(round_num):
    path = PREDICTIONS_DIR / f"round{round_num}" / "actual_fantasy_points.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_overtakes(round_num):
    path = DATA_DIR / "overtakes" / f"year{CURRENT_SEASON}" / f"round{round_num}" / "overtakes.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def get_available_rounds():
    """Find all rounds with prediction or actual data."""
    rounds = []
    for rnd in range(1, 25):
        if rnd in CANCELLED_ROUNDS_2026:
            continue
        pred_path = PREDICTIONS_DIR / f"round{rnd}" / "predictions.parquet"
        fp_path = PREDICTIONS_DIR / f"round{rnd}" / "fantasy_points.parquet"
        act_path = PREDICTIONS_DIR / f"round{rnd}" / "actual_fantasy_points.json"
        if pred_path.exists() or fp_path.exists() or act_path.exists():
            rounds.append(rnd)
    return rounds


def get_race_name(round_num):
    """Get race name from actual or prediction data."""
    act = load_actual_results(round_num)
    if act:
        return act.get("race", f"Round {round_num}")
    return f"Round {round_num}"


# ==============================================================================
# MC Re-simulation with overrides
# ==============================================================================

def run_mc_with_overrides(round_num, overrides, n_sims=5000):
    """Run Monte Carlo simulation with user overrides applied.

    overrides: dict with keys like:
        grid_penalties: {driver_abbrev: new_grid_position}
        dns_drivers: [driver_abbrev, ...]
        dnf_overrides: {driver_abbrev: dnf_probability}

    TODO: implement run_mc_core in pipeline/08_monte_carlo_fantasy.py
    """
    st.warning("MC re-simulation with overrides not yet implemented.")
    return None


# ==============================================================================
# Page: Race Weekend Predictions
# ==============================================================================

def get_rounds_with_predictions():
    """Find rounds that have prediction data (fantasy_points.parquet)."""
    rounds = []
    for rnd in range(1, 25):
        if rnd in CANCELLED_ROUNDS_2026:
            continue
        fp_path = PREDICTIONS_DIR / f"round{rnd}" / "fantasy_points.parquet"
        mc_path = PREDICTIONS_DIR / f"round{rnd}" / "monte_carlo_fantasy.json"
        if fp_path.exists() or mc_path.exists():
            rounds.append(rnd)
    return rounds


def page_predictions():
    st.header("Race Weekend Predictions")

    rounds = get_rounds_with_predictions()
    if not rounds:
        st.warning("No prediction data found. Run the prediction pipeline first.")
        return

    # Round selector
    round_num = st.selectbox(
        "Select Round",
        rounds,
        format_func=lambda r: f"Round {r} — {get_race_name(r)}",
        index=len(rounds) - 1,
    )

    is_sprint = round_num in SPRINT_ROUNDS_2026

    # Load data
    fp_df = load_fantasy_points(round_num)
    mc_data = load_mc_results(round_num)
    drivers_info = load_drivers_info()
    driver_prices, constructor_prices = load_fantasy_prices()

    if fp_df is None and mc_data is None:
        st.warning(f"No fantasy points data for Round {round_num}. Run the prediction pipeline.")
        return

    # Sprint badge
    if is_sprint:
        st.info("Sprint Weekend")

    # --- Overrides Sidebar ---
    st.sidebar.header("Manual Overrides")
    st.sidebar.caption("Adjust predictions before the race")

    all_drivers = sorted(fp_df["driver_abbrev"].tolist())

    # Grid penalties
    st.sidebar.subheader("Grid Penalties")
    grid_penalties = {}
    n_penalties = st.sidebar.number_input("Number of grid penalties", 0, 5, 0)
    for i in range(int(n_penalties)):
        col1, col2 = st.sidebar.columns(2)
        drv = col1.selectbox(f"Driver {i+1}", all_drivers, key=f"gp_drv_{i}")
        new_pos = col2.number_input(f"New grid P", 1, 22, 20, key=f"gp_pos_{i}")
        grid_penalties[drv] = new_pos

    # DNS
    st.sidebar.subheader("Will Not Start")
    dns_drivers = st.sidebar.multiselect("DNS Drivers", all_drivers)

    # DNF probability overrides
    st.sidebar.subheader("DNF Risk Overrides")
    dnf_overrides = {}
    n_dnf = st.sidebar.number_input("Number of DNF overrides", 0, 5, 0)
    for i in range(int(n_dnf)):
        col1, col2 = st.sidebar.columns(2)
        drv = col1.selectbox(f"Driver {i+1}", all_drivers, key=f"dnf_drv_{i}")
        prob = col2.slider(f"DNF %", 0, 100, 15, key=f"dnf_prob_{i}")
        dnf_overrides[drv] = prob / 100.0

    has_overrides = grid_penalties or dns_drivers or dnf_overrides

    if has_overrides:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Active overrides:**")
        for drv, pos in grid_penalties.items():
            st.sidebar.write(f"  {drv}: Grid P{pos}")
        for drv in dns_drivers:
            st.sidebar.write(f"  {drv}: DNS")
        for drv, prob in dnf_overrides.items():
            st.sidebar.write(f"  {drv}: DNF {prob*100:.0f}%")

    # --- Main content ---
    tab1, tab2, tab3 = st.tabs(["Drivers", "Constructors", "Pit Stops"])

    with tab1:
        _show_driver_predictions(fp_df, mc_data, drivers_info, driver_prices,
                                 grid_penalties, dns_drivers, dnf_overrides)

    with tab2:
        _show_constructor_predictions(mc_data, constructor_prices)

    with tab3:
        _show_pitstop_info(round_num)


def _show_driver_predictions(fp_df, mc_data, drivers_info, driver_prices,
                             grid_penalties, dns_drivers, dnf_overrides):
    """Display driver prediction table with MC data."""

    mc_lookup = {}
    if mc_data:
        mc_lookup = {d["driver_abbrev"]: d for d in mc_data["drivers"]}

    rows = []
    for _, row in fp_df.iterrows():
        abbrev = row["driver_abbrev"]
        mc = mc_lookup.get(abbrev, {})
        info = drivers_info.get(abbrev, {})

        # Apply override indicators
        notes = []
        if abbrev in grid_penalties:
            notes.append(f"Grid P{grid_penalties[abbrev]}")
        if abbrev in dns_drivers:
            notes.append("DNS")
        if abbrev in dnf_overrides:
            notes.append(f"DNF {dnf_overrides[abbrev]*100:.0f}%")

        mc_mean = mc.get("mc_total_mean", row["total_expected_fantasy_points"])
        mc_std = mc.get("mc_total_std", 0)

        rows.append({
            "Driver": abbrev,
            "Team": info.get("constructor_id", row["constructor_id"]),
            "Quali": f"P{row['predicted_quali_position']}",
            "Race": f"P{row['predicted_race_position']}",
            "Det Pts": round(row["total_expected_fantasy_points"], 1),
            "MC Mean": round(mc_mean, 1),
            "MC Std": round(mc_std, 1),
            "P5": mc.get("mc_total_p5", ""),
            "P95": mc.get("mc_total_p95", ""),
            "Top3%": f"{mc.get('prob_top3', 0)*100:.0f}%" if mc else "",
            "DNF%": f"{mc.get('mc_dnf_rate', row.get('dnf_probability', 0))*100:.0f}%",
            "Price": driver_prices.get(abbrev, 0),
            "Value": round(mc_mean / driver_prices[abbrev], 2) if driver_prices.get(abbrev, 0) > 0 else 0,
            "Notes": ", ".join(notes) if notes else "",
        })

    df = pd.DataFrame(rows).sort_values("MC Mean", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "Rank"

    # Color the MC Mean column
    st.dataframe(
        df.style.background_gradient(subset=["MC Mean"], cmap="RdYlGn")
              .background_gradient(subset=["Value"], cmap="Blues")
              .format({"Price": "{:.1f}M", "Value": "{:.2f}", "MC Mean": "{:.1f}", "MC Std": "{:.1f}", "P5": "{:.0f}", "P95": "{:.0f}", "Det Pts": "{:.1f}"}),
        width="stretch",
        height=820,
    )

    # Summary metrics
    if mc_lookup:
        col1, col2, col3, col4 = st.columns(4)
        top = max(mc_lookup.values(), key=lambda d: d.get("mc_total_mean", 0))
        best_val = max(rows, key=lambda r: r["Value"])
        safest = min(
            [d for d in mc_lookup.values() if d.get("mc_total_mean", 0) > 5],
            key=lambda d: d.get("mc_total_std", 99),
            default=None,
        )
        most_upside = max(mc_lookup.values(), key=lambda d: d.get("mc_upside", 0))

        col1.metric("Highest Expected", f"{top['driver_abbrev']}", f"{top['mc_total_mean']:.1f} pts")
        col2.metric("Best Value", f"{best_val['Driver']}", f"{best_val['Value']:.2f} ppm")
        if safest:
            col3.metric("Most Consistent", f"{safest['driver_abbrev']}", f"std={safest['mc_total_std']:.1f}")
        col4.metric("Most Upside", f"{most_upside['driver_abbrev']}", f"+{most_upside.get('mc_upside', 0):.1f}")


def _show_constructor_predictions(mc_data, constructor_prices):
    """Display constructor prediction table."""
    if not mc_data or "constructors" not in mc_data:
        st.info("No Monte Carlo constructor data available. Run 08_monte_carlo_fantasy.py first.")
        return

    rows = []
    for c in mc_data["constructors"]:
        rows.append({
            "Constructor": c["name"],
            "D1": c["driver_1"],
            "D2": c["driver_2"],
            "MC Mean": c["mc_total_mean"],
            "MC Std": c["mc_total_std"],
            "P5": c["mc_total_p5"],
            "P95": c["mc_total_p95"],
            "Price": c.get("price", 0),
            "Value": c.get("mc_value_score", 0),
        })

    df = pd.DataFrame(rows)
    df.index = range(1, len(df) + 1)
    df.index.name = "Rank"

    st.dataframe(
        df.style.background_gradient(subset=["MC Mean"], cmap="RdYlGn")
              .background_gradient(subset=["Value"], cmap="Blues")
              .format({"Price": "{:.1f}M", "Value": "{:.2f}", "MC Mean": "{:.1f}", "MC Std": "{:.1f}", "P5": "{:.0f}", "P95": "{:.0f}"}),
        width="stretch",
    )


def _show_pitstop_info(round_num):
    """Display pit stop data and scoring breakdown."""
    ot_data = load_overtakes(round_num)
    if not ot_data or "pitstops" not in ot_data:
        st.info("No pit stop stationary time data available for this round.")
        st.caption("Run `python pipeline/13_fetch_openf1_overtakes.py --year 2026 --round N` to fetch.")
        return

    pitstops = ot_data["pitstops"]
    by_driver = pitstops.get("by_driver", {})

    st.subheader("Pit Stop Stationary Times")

    rows = []
    for abbrev, stops in sorted(by_driver.items()):
        for s in stops:
            dur = s["stop_duration"]
            pts = 0
            for lo, hi, p in PITSTOP_TIME_POINTS:
                if lo <= dur < hi:
                    pts = p
                    break
            rows.append({
                "Driver": abbrev,
                "Lap": s.get("lap", ""),
                "Stop Duration (s)": round(dur, 3),
                "Lane Duration (s)": round(s.get("lane_duration", 0), 3) if s.get("lane_duration") else "",
                "Fantasy Points": pts,
            })

    df = pd.DataFrame(rows).sort_values("Stop Duration (s)")
    df.index = range(1, len(df) + 1)

    st.dataframe(
        df.style.background_gradient(subset=["Fantasy Points"], cmap="Greens"),
        width="stretch",
    )

    fastest = pitstops.get("fastest_stop", {})
    if fastest:
        st.metric(
            "Fastest Pit Stop",
            f"{fastest.get('driver', '?')} — {fastest.get('stop_duration', 0):.3f}s",
            f"+{FASTEST_PITSTOP_BONUS} bonus points",
        )


# ==============================================================================
# Page: Actual Results & Comparison
# ==============================================================================

def page_actuals():
    st.header("Actual Results & Comparison")

    # Find rounds with actual data
    rounds_with_actuals = []
    for rnd in range(1, 25):
        if rnd in CANCELLED_ROUNDS_2026:
            continue
        act_path = PREDICTIONS_DIR / f"round{rnd}" / "actual_fantasy_points.json"
        if act_path.exists():
            rounds_with_actuals.append(rnd)

    if not rounds_with_actuals:
        st.warning("No actual results available yet.")
        return

    round_num = st.selectbox(
        "Select Round",
        rounds_with_actuals,
        format_func=lambda r: f"Round {r} — {get_race_name(r)}",
    )

    actual = load_actual_results(round_num)
    mc_data = load_mc_results(round_num)
    fp_df = load_fantasy_points(round_num)

    if actual is None:
        return

    st.subheader(f"{actual.get('race', 'Unknown')} — Actual Fantasy Points")

    tab1, tab2, tab3 = st.tabs(["Driver Results", "Constructor Results", "Predicted vs Actual"])

    with tab1:
        _show_actual_drivers(actual)

    with tab2:
        _show_actual_constructors(actual)

    with tab3:
        _show_comparison(actual, mc_data, fp_df, round_num)


def _show_actual_drivers(actual):
    rows = []
    for d in actual["drivers"]:
        rows.append({
            "Driver": d["driver_id"],
            "Team": d["constructor"],
            "Quali": f"P{d.get('quali_position', '-')}",
            "Grid": f"P{d['grid']}",
            "Finish": f"P{d['race_position']}" if d["race_position"] else d["status"][:10],
            "Status": d["status"][:15],
            "Quali Pts": d["quali_points"],
            "Race Pts": d["race_points"],
            "DOTD": "⭐" if d.get("is_dotd") else "",
            "Sprint Pts": d.get("sprint_points", 0),
            "Total": d["total_points"],
            "Overtakes": d.get("overtakes", 0),
            "OT Source": d.get("overtake_source", "estimated"),
            "Price": d.get("price", 0),
        })

    df = pd.DataFrame(rows)
    df.index = range(1, len(df) + 1)
    df.index.name = "Rank"

    st.dataframe(
        df.style.background_gradient(subset=["Total"], cmap="RdYlGn")
              .format({"Price": "{:.1f}M"}),
        width="stretch",
        height=820,
    )


def _show_actual_constructors(actual):
    rows = []
    for c in actual["constructors"]:
        rows.append({
            "Constructor": c["name"],
            "D1": c["driver_1"],
            "D2": c["driver_2"],
            "Quali": c["quali_points"],
            "Bonus": c["quali_bonus"],
            "Race": c["race_points"],
            "Pit Stop": c.get("pitstop_points", 0),
            "Sprint": c.get("sprint_points", 0),
            "Total": c["total_points"],
            "Price": c.get("price", 0),
        })

    df = pd.DataFrame(rows)
    df.index = range(1, len(df) + 1)
    st.dataframe(
        df.style.background_gradient(subset=["Total"], cmap="RdYlGn")
              .format({"Price": "{:.1f}M"}),
        width="stretch",
    )


def _show_comparison(actual, mc_data, fp_df, round_num):
    """Show predicted vs actual comparison."""
    if fp_df is None and mc_data is None:
        st.info("No prediction data available for this round to compare against.")
        return

    act_lookup = {d["driver_id"]: d for d in actual["drivers"]}
    mc_lookup = {d["driver_abbrev"]: d for d in mc_data["drivers"]} if mc_data else {}

    rows = []
    errors_det = []
    errors_mc = []
    in_ci = 0
    total = 0

    for abbrev, act in act_lookup.items():
        actual_pts = act["total_points"]

        # Deterministic
        det_pts = None
        if fp_df is not None and "driver_abbrev" in fp_df.columns:
            det_row = fp_df[fp_df["driver_abbrev"] == abbrev]
            if len(det_row) > 0:
                det_pts = det_row.iloc[0]["total_expected_fantasy_points"]

        # MC
        mc = mc_lookup.get(abbrev, {})
        mc_mean = mc.get("mc_total_mean")
        p5 = mc.get("mc_total_p5")
        p95 = mc.get("mc_total_p95")

        within_ci = ""
        if p5 is not None and p95 is not None:
            within_ci = "Yes" if p5 <= actual_pts <= p95 else "No"
            total += 1
            if within_ci == "Yes":
                in_ci += 1

        if det_pts is not None:
            errors_det.append(abs(actual_pts - det_pts))
        if mc_mean is not None:
            errors_mc.append(abs(actual_pts - mc_mean))

        rows.append({
            "Driver": abbrev,
            "Actual": actual_pts,
            "Det Pred": round(det_pts, 1) if det_pts is not None else "",
            "MC Mean": round(mc_mean, 1) if mc_mean is not None else "",
            "MC P5": p5 if p5 is not None else "",
            "MC P95": p95 if p95 is not None else "",
            "In 90% CI": within_ci,
            "Det Error": f"{actual_pts - det_pts:+.1f}" if det_pts is not None else "",
            "MC Error": f"{actual_pts - mc_mean:+.1f}" if mc_mean is not None else "",
        })

    df = pd.DataFrame(rows).sort_values("Actual", ascending=False)
    df.index = range(1, len(df) + 1)

    st.dataframe(df, width="stretch", height=820)

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    if errors_det:
        col1.metric("Deterministic MAE", f"{np.mean(errors_det):.1f}")
    if errors_mc:
        col2.metric("Monte Carlo MAE", f"{np.mean(errors_mc):.1f}")
    if total > 0:
        col3.metric("90% CI Coverage", f"{in_ci}/{total} ({in_ci/total*100:.0f}%)")


# ==============================================================================
# Page: Season Overview
# ==============================================================================

def page_season():
    st.header("Season Overview")

    drivers_info = load_drivers_info()
    driver_prices, _ = load_fantasy_prices()

    # Cumulative points across rounds
    rounds_with_actuals = []
    for rnd in range(1, 25):
        if rnd in CANCELLED_ROUNDS_2026:
            continue
        act_path = PREDICTIONS_DIR / f"round{rnd}" / "actual_fantasy_points.json"
        if act_path.exists():
            rounds_with_actuals.append(rnd)

    if not rounds_with_actuals:
        st.info("No completed rounds yet.")
        return

    # Build cumulative totals
    driver_totals: dict[str, dict] = {}
    for rnd in rounds_with_actuals:
        actual = load_actual_results(rnd)
        if not actual:
            continue
        for d in actual["drivers"]:
            abbrev = d["driver_id"]
            if abbrev not in driver_totals:
                driver_totals[abbrev] = {
                    "Driver": abbrev,
                    "Team": d["constructor"],
                    "Rounds": 0,
                    "Total Points": 0,
                    "Price": driver_prices.get(abbrev, 0),
                }
            driver_totals[abbrev]["Rounds"] += 1
            driver_totals[abbrev]["Total Points"] += d["total_points"]

    for dt in driver_totals.values():
        dt["Avg/Round"] = round(dt["Total Points"] / dt["Rounds"], 1)
        dt["Season Value"] = round(dt["Total Points"] / dt["Price"], 2) if dt["Price"] > 0 else 0

    df = pd.DataFrame(driver_totals.values()).sort_values("Total Points", ascending=False)
    df.index = range(1, len(df) + 1)
    df.index.name = "Rank"

    st.subheader(f"Driver Championship ({len(rounds_with_actuals)} rounds)")
    st.dataframe(
        df.style.background_gradient(subset=["Total Points"], cmap="RdYlGn")
              .background_gradient(subset=["Season Value"], cmap="Blues")
              .format({"Price": "{:.1f}M", "Season Value": "{:.2f}", "Avg/Round": "{:.1f}"}),
        width="stretch",
    )

    # Constructor totals
    constructors_info = load_constructors_info()
    constructor_totals: dict[str, dict] = {}
    for rnd in rounds_with_actuals:
        actual = load_actual_results(rnd)
        if not actual:
            continue
        for c in actual["constructors"]:
            cid = c["constructor_id"]
            if cid not in constructor_totals:
                constructor_totals[cid] = {
                    "Constructor": c["name"],
                    "Rounds": 0,
                    "Total Points": 0,
                }
            constructor_totals[cid]["Rounds"] += 1
            constructor_totals[cid]["Total Points"] += c["total_points"]

    for ct in constructor_totals.values():
        ct["Avg/Round"] = round(ct["Total Points"] / ct["Rounds"], 1)

    cdf = pd.DataFrame(constructor_totals.values()).sort_values("Total Points", ascending=False)
    cdf.index = range(1, len(cdf) + 1)

    st.subheader(f"Constructor Championship ({len(rounds_with_actuals)} rounds)")
    st.dataframe(
        cdf.style.background_gradient(subset=["Total Points"], cmap="RdYlGn"),
        width="stretch",
    )


# ==============================================================================
# Race Deep Dive
# ==============================================================================

TEAM_COLORS_HEX = {
    'red_bull': '#3671C6', 'ferrari': '#E80020', 'mercedes': '#27F4D2',
    'mclaren': '#FF8000', 'aston_martin': '#229971', 'alpine': '#FF87BC',
    'williams': '#64C4FF', 'racing_bulls': '#6692FF', 'audi': '#00E701',
    'haas': '#B6BABD', 'cadillac': '#FFD700',
}

def load_deep_dive(round_num):
    path = PREDICTIONS_DIR / f"round{round_num}" / "race_deep_dive.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def page_deep_dive():
    st.header("Race Deep Dive")
    st.caption("Fuel-corrected pace analysis, sector breakdowns, tyre degradation & more")

    # Find available rounds
    available = []
    for rd in sorted(PREDICTIONS_DIR.glob("round*")):
        rn = int(rd.name.replace("round", ""))
        if (rd / "race_deep_dive.json").exists():
            available.append(rn)

    if not available:
        st.warning("No deep dive data available. Run `python pipeline/11_race_deep_dive.py --round N` first.")
        return

    round_num = st.selectbox("Select Round", available, index=len(available) - 1,
                             format_func=lambda r: f"Round {r}")
    dd = load_deep_dive(round_num)
    if not dd:
        st.error("Failed to load deep dive data.")
        return

    st.subheader(f"{dd['race']} — {dd['season']}")

    metrics = dd["driver_metrics"]
    drivers_sorted = sorted(metrics.keys(), key=lambda d: metrics[d]["avg_lap"])

    # -- Pace Summary Table --
    st.markdown("### Driver Pace Summary (Fuel-Corrected)")
    pace_rows = []
    for d in drivers_sorted:
        m = metrics[d]
        pace_rows.append({
            "Driver": d,
            "Team": dd["driver_constructors"].get(d, ""),
            "Avg Lap": round(m["avg_lap"], 3),
            "Best Lap": round(m["best_lap"], 3),
            "3-Lap Avg": round(m["best_3_lap_avg"], 3),
            "5-Lap Avg": round(m["best_5_lap_avg"], 3),
            "10-Lap Avg": round(m["best_10_lap_avg"], 3),
            "Theo. Best": round(m["theoretical_best"], 3),
            "Gap": round(m["pace_delta"], 3),
            "Std Dev": round(m["lap_time_std"], 3),
            "Laps": m["laps_analyzed"],
        })
    st.dataframe(pd.DataFrame(pace_rows), use_container_width=True, hide_index=True)

    # -- Lap Time Evolution Chart --
    st.markdown("### Lap Time Evolution")
    n_drivers = st.slider("Number of drivers to show", 3, len(drivers_sorted), 5)
    show_drivers = drivers_sorted[:n_drivers]

    import plotly.graph_objects as go
    fig_laps = go.Figure()
    for d in show_drivers:
        laps = dd["lap_data"].get(d, [])
        if not laps:
            continue
        color = TEAM_COLORS_HEX.get(dd["driver_constructors"].get(d, ""), "#888")
        fig_laps.add_trace(go.Scatter(
            x=[l["lap"] for l in laps],
            y=[l["fuel_corrected"] for l in laps],
            name=d, mode='lines+markers',
            line=dict(color=color, width=2),
            marker=dict(size=3),
        ))
    fig_laps.update_layout(
        template="plotly_dark", height=450,
        xaxis_title="Lap", yaxis_title="Lap Time (s)",
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_laps, use_container_width=True)

    # -- Position Tracker --
    st.markdown("### Position Tracker")
    fig_pos = go.Figure()
    for d in show_drivers:
        positions = dd["position_tracker"].get(d, [])
        if not positions:
            continue
        color = TEAM_COLORS_HEX.get(dd["driver_constructors"].get(d, ""), "#888")
        fig_pos.add_trace(go.Scatter(
            x=[p["lap"] for p in positions],
            y=[p["position"] for p in positions],
            name=d, mode='lines',
            line=dict(color=color, width=2),
        ))
    fig_pos.update_layout(
        template="plotly_dark", height=450,
        xaxis_title="Lap", yaxis_title="Position",
        yaxis=dict(autorange="reversed", dtick=1),
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_pos, use_container_width=True)

    # -- Sector Performance --
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Sector Performance (Best)")
        sec_rows = []
        for d in drivers_sorted:
            m = metrics[d]
            sec_rows.append({
                "Driver": d,
                "Best S1": round(m["best_s1"], 3),
                "Best S2": round(m["best_s2"], 3),
                "Best S3": round(m["best_s3"], 3),
                "Theo. Best": round(m["theoretical_best"], 3),
            })
        st.dataframe(pd.DataFrame(sec_rows), use_container_width=True, hide_index=True)

    with col2:
        st.markdown("### Speed Trap")
        spd_rows = []
        for d in sorted(drivers_sorted, key=lambda d: -(metrics[d].get("max_speed_trap", 0))):
            m = metrics[d]
            spd_rows.append({
                "Driver": d,
                "Max Speed": round(m.get("max_speed_trap", 0), 1),
                "Avg Speed": round(m.get("avg_speed_trap", 0), 1),
            })
        st.dataframe(pd.DataFrame(spd_rows), use_container_width=True, hide_index=True)

    # -- Tyre Strategy --
    st.markdown("### Tyre Strategy & Degradation")
    stint_rows = []
    for d in drivers_sorted:
        for s in dd["stint_analysis"].get(d, []):
            cliff = any(c["stint"] == s["stint"] for c in dd["tyre_cliffs"].get(d, []))
            stint_rows.append({
                "Driver": d,
                "Stint": s["stint"],
                "Compound": s["compound"],
                "Laps": s["laps"],
                "Avg Pace": round(s["avg_pace"], 3),
                "Start Pace": round(s["start_pace"], 3),
                "End Pace": round(s["end_pace"], 3),
                "Deg Rate": round(s["degradation_rate"], 4),
                "Cliff?": "YES" if cliff else "",
            })
    st.dataframe(pd.DataFrame(stint_rows), use_container_width=True, hide_index=True)

    # -- Gap to Leader --
    st.markdown("### Gap to Leader")
    fig_gap = go.Figure()
    for d in drivers_sorted[:8]:
        gaps = dd["gap_to_leader"].get(d, [])
        if not gaps:
            continue
        color = TEAM_COLORS_HEX.get(dd["driver_constructors"].get(d, ""), "#888")
        fig_gap.add_trace(go.Scatter(
            x=[g["lap"] for g in gaps],
            y=[g["gap"] for g in gaps],
            name=d, mode='lines',
            line=dict(color=color, width=1.5),
        ))
    fig_gap.update_layout(
        template="plotly_dark", height=450,
        xaxis_title="Lap", yaxis_title="Gap to Leader (s)",
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_gap, use_container_width=True)

    # -- Race Momentum --
    if dd.get("race_momentum"):
        st.markdown("### Race Momentum (Pace by Third)")
        mom_rows = []
        for d in drivers_sorted:
            m = dd["race_momentum"].get(d)
            if not m:
                continue
            mom_rows.append({
                "Driver": d,
                "Opening Rank": m["opening_rank"],
                "Opening Pace": round(m["opening_pace"], 3),
                "Middle Rank": m["middle_rank"],
                "Middle Pace": round(m["middle_pace"], 3),
                "Closing Rank": m["closing_rank"],
                "Closing Pace": round(m["closing_pace"], 3),
            })
        st.dataframe(pd.DataFrame(mom_rows), use_container_width=True, hide_index=True)

    # -- Dirty Air --
    if dd.get("dirty_air"):
        st.markdown("### Dirty Air Effect")
        st.caption("Clean air = >3s gap ahead | Dirty air = <1.5s gap")
        da_rows = []
        for d, da in sorted(dd["dirty_air"].items(), key=lambda x: -x[1]["delta"]):
            da_rows.append({
                "Driver": d,
                "Clean Pace": round(da["clean_air_pace"], 3),
                "Dirty Pace": round(da["dirty_air_pace"], 3),
                "Delta": round(da["delta"], 3),
                "Clean Laps": da["clean_laps"],
                "Dirty Laps": da["dirty_laps"],
            })
        st.dataframe(pd.DataFrame(da_rows), use_container_width=True, hide_index=True)

    # -- Team Summary --
    if dd.get("team_summary"):
        st.markdown("### Team Performance")
        team_rows = []
        for t in sorted(dd["team_summary"].keys(), key=lambda t: dd["team_summary"][t]["avg_pace"]):
            ts = dd["team_summary"][t]
            team_rows.append({
                "Team": t,
                "Drivers": ", ".join(ts.get("drivers", [])),
                "Avg Pace": round(ts["avg_pace"], 3),
                "Best Pace": round(ts["best_pace"], 3),
                "Fastest Sector": ts.get("fastest_sector", "-"),
            })
        st.dataframe(pd.DataFrame(team_rows), use_container_width=True, hide_index=True)


# ==============================================================================
# Main App
# ==============================================================================

def main():
    st.set_page_config(
        page_title="BoxBoxF1Fantasy",
        page_icon="🏎️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("BoxBoxF1Fantasy Dashboard")
    st.caption(f"Season {CURRENT_SEASON}")

    page = st.sidebar.radio(
        "Navigation",
        ["Race Predictions", "Actual Results", "Season Overview", "Race Deep Dive"],
        index=0,
    )

    if page == "Race Predictions":
        page_predictions()
    elif page == "Actual Results":
        page_actuals()
    elif page == "Season Overview":
        page_season()
    elif page == "Race Deep Dive":
        page_deep_dive()


if __name__ == "__main__":
    main()
