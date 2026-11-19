"""Build shareable, data-driven charts for current-race SEO articles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTIONS = ROOT / "web" / "public" / "data" / "predictions.json"
DEFAULT_SEASON_SUMMARY = ROOT / "web" / "public" / "data" / "season_summary.json"
DEFAULT_DRIVER_HISTORY = ROOT / "web" / "public" / "data" / "driver_history.json"
DEFAULT_IMAGES_DIR = ROOT / "web" / "public" / "images"


def chart_slug(race: str, year: int) -> str:
    name = race.lower().replace("grand prix", "gp")
    slug = "-".join("".join(ch if ch.isalnum() else " " for ch in name).split())
    return f"{slug}-{year}-fantasy-forecast.png"


def season_report_slug(year: int) -> str:
    return f"f1-fantasy-{year}-mid-season-points-value.png"


def build_current_forecast_chart(predictions: dict, output_path: Path) -> Path:
    drivers = sorted(
        predictions.get("drivers", []),
        key=lambda driver: float(driver.get("expected_points") or 0),
        reverse=True,
    )[:8]
    if len(drivers) < 2:
        raise ValueError("At least two driver predictions are required for the forecast chart")

    names = [driver.get("name", driver.get("driver_id", "Driver")) for driver in drivers]
    means = np.array([float(driver.get("expected_points") or 0) for driver in drivers])
    lows = np.array([float(driver.get("mc_total_p5") or 0) for driver in drivers])
    highs = np.array([float(driver.get("mc_total_p95") or 0) for driver in drivers])
    y = np.arange(len(drivers))

    background = "#0a0d12"
    text = "#f1f5f9"
    muted = "#a8b3c2"
    range_color = "#64748b"
    colors = ["#ef4444", "#2dd4bf"] + ["#60a5fa"] * max(0, len(drivers) - 2)

    fig, ax = plt.subplots(figsize=(12, 6.3), dpi=100)
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)

    lower_error = np.maximum(means - lows, 0)
    upper_error = np.maximum(highs - means, 0)
    ax.errorbar(
        means,
        y,
        xerr=np.vstack([lower_error, upper_error]),
        fmt="none",
        ecolor=range_color,
        elinewidth=4,
        capsize=6,
        capthick=2,
        alpha=0.9,
        zorder=1,
    )
    ax.scatter(means, y, s=115, c=colors, edgecolors=background, linewidths=2, zorder=3)
    ax.axvline(0, color="#eab308", linewidth=1.2, alpha=0.75, zorder=0)

    for idx, mean in enumerate(means):
        ax.annotate(
            f"{mean:.1f}",
            (mean, idx),
            xytext=(10, 0),
            textcoords="offset points",
            va="center",
            color=text,
            fontsize=11,
            fontweight="bold",
        )

    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.tick_params(axis="y", colors=text, labelsize=12, length=0, pad=12)
    ax.tick_params(axis="x", colors=muted, labelsize=10, length=0)
    ax.set_xlabel("F1 Fantasy points", color=muted, fontsize=11, labelpad=10)
    ax.grid(axis="x", color="#273244", linewidth=0.8, alpha=0.75)
    ax.grid(axis="y", visible=False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    left = min(float(lows.min()) - 5, -20)
    right = max(float(highs.max()) + 12, 60)
    ax.set_xlim(left, right)

    race = predictions.get("race", "Current Grand Prix")
    year = int(predictions.get("season") or 2026)
    generated = str(predictions.get("generated_at") or "")[:10]
    generated_label = generated or "current export"
    fig.text(0.055, 0.935, f"{race} {year}", color=text, fontsize=25, fontweight="bold")
    fig.text(0.055, 0.885, "F1 Fantasy expected points and 90% simulation range", color=muted, fontsize=14)
    fig.text(0.945, 0.93, "BoxBoxF1Fantasy", color="#ef4444", fontsize=14, fontweight="bold", ha="right")
    fig.text(0.055, 0.045, f"PRE-PRACTICE SNAPSHOT  |  Model run {generated_label}  |  P5-P95 range", color=muted, fontsize=10)
    fig.text(0.945, 0.045, "boxboxf1fantasy.com", color=muted, fontsize=10, ha="right")
    fig.subplots_adjust(left=0.22, right=0.95, top=0.80, bottom=0.16)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_path,
        dpi=100,
        facecolor=background,
        metadata={
            "Title": f"{race} {year} F1 Fantasy forecast",
            "Author": "BoxBoxF1Fantasy",
            "Description": "Expected driver fantasy points with P5-P95 simulation ranges.",
        },
    )
    plt.close(fig)
    return output_path


def _season_rows(history_group: dict, prices_group: dict) -> list[dict]:
    rows = []
    for asset_id, price in prices_group.items():
        scores = [
            float(item.get("points") or 0)
            for item in (history_group.get(asset_id, {}).get("rounds") or [])
        ]
        if not scores:
            continue
        current_price = float(price.get("current_price") or 0)
        average = sum(scores) / len(scores)
        rows.append({
            "id": asset_id,
            "name": price.get("name") or asset_id,
            "total": sum(scores),
            "average": average,
            "price_change": float(price.get("price_change") or 0),
            "ppm": average / current_price if current_price else 0,
            "rounds": len(scores),
        })
    return rows


def build_midseason_report_chart(season: dict, history: dict, output_path: Path) -> Path:
    """Build a dated season-points and constructor-value editorial chart."""
    year = int(season.get("season") or history.get("season") or 2026)
    drivers = sorted(
        _season_rows(history.get("drivers") or {}, season.get("driver_prices") or {}),
        key=lambda item: item["total"],
        reverse=True,
    )[:8]
    constructors = sorted(
        _season_rows(history.get("constructors") or {}, season.get("constructor_prices") or {}),
        key=lambda item: item["ppm"],
        reverse=True,
    )[:6]
    if len(drivers) < 5 or len(constructors) < 3:
        raise ValueError("Season report chart requires recorded driver and constructor history")

    background = "#0a0d12"
    panel = "#0f141d"
    text = "#f1f5f9"
    muted = "#a8b3c2"
    grid = "#273244"
    driver_colors = ["#ef4444", "#f59e0b", "#60a5fa", "#2dd4bf"] + ["#64748b"] * 4
    constructor_colors = ["#2dd4bf", "#f59e0b", "#60a5fa", "#a78bfa", "#ef4444", "#64748b"]

    fig, (driver_ax, constructor_ax) = plt.subplots(
        1,
        2,
        figsize=(12, 6.3),
        dpi=100,
        gridspec_kw={"width_ratios": [1.12, 0.88], "wspace": 0.36},
    )
    fig.patch.set_facecolor(background)
    for ax in (driver_ax, constructor_ax):
        ax.set_facecolor(panel)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis="both", colors=muted, length=0)
        ax.grid(axis="x", color=grid, linewidth=0.8, alpha=0.72)
        ax.set_axisbelow(True)

    driver_names = [item["name"] for item in drivers]
    driver_totals = [item["total"] for item in drivers]
    y_drivers = np.arange(len(drivers))
    driver_ax.barh(y_drivers, driver_totals, color=driver_colors[:len(drivers)], height=0.58)
    driver_ax.set_yticks(y_drivers, driver_names)
    driver_ax.invert_yaxis()
    driver_ax.set_xlim(0, max(driver_totals) * 1.30)
    driver_ax.set_xlabel("Recorded fantasy points", color=muted, fontsize=10, labelpad=8)
    driver_ax.set_title("DRIVER POINTS LEADERS", color=text, fontsize=13, fontweight="bold", loc="left", pad=14)
    for idx, item in enumerate(drivers):
        change = item["price_change"]
        driver_ax.text(
            item["total"] + max(driver_totals) * 0.025,
            idx,
            f'{item["total"]:.0f}  ({change:+.1f}M)',
            va="center",
            color=text if idx < 4 else muted,
            fontsize=9.5,
            fontweight="bold" if idx < 3 else "normal",
        )

    constructor_names = [item["name"] for item in constructors]
    constructor_ppm = [item["ppm"] for item in constructors]
    y_constructors = np.arange(len(constructors))
    constructor_ax.barh(
        y_constructors,
        constructor_ppm,
        color=constructor_colors[:len(constructors)],
        height=0.58,
    )
    constructor_ax.set_yticks(y_constructors, constructor_names)
    constructor_ax.invert_yaxis()
    constructor_ax.set_xlim(0, max(constructor_ppm) * 1.28)
    constructor_ax.set_xlabel("Average points per race / current $M", color=muted, fontsize=10, labelpad=8)
    constructor_ax.set_title("CONSTRUCTOR VALUE", color=text, fontsize=13, fontweight="bold", loc="left", pad=14)
    for idx, item in enumerate(constructors):
        constructor_ax.text(
            item["ppm"] + max(constructor_ppm) * 0.035,
            idx,
            f'{item["ppm"]:.2f}',
            va="center",
            color=text,
            fontsize=10,
            fontweight="bold",
        )

    completed = [item for item in season.get("rounds", []) if item.get("has_actual")]
    latest = completed[-1].get("name", "latest completed race") if completed else "latest completed race"
    rounds = max((item["rounds"] for item in drivers), default=0)
    fig.text(0.055, 0.94, f"F1 Fantasy {year} Mid-Season Report", color=text, fontsize=24, fontweight="bold")
    fig.text(0.055, 0.895, "Recorded driver points, season price movement and constructor value", color=muted, fontsize=13)
    fig.text(0.945, 0.935, "BoxBoxF1Fantasy", color="#ef4444", fontsize=14, fontweight="bold", ha="right")
    fig.text(
        0.055,
        0.035,
        f"{rounds} COMPLETED RACES THROUGH {latest.upper()}  |  Driver totals exclude manager boosts  |  Value uses current price",
        color=muted,
        fontsize=9,
    )
    fig.text(0.945, 0.035, "boxboxf1fantasy.com/stats", color=muted, fontsize=9, ha="right")
    fig.subplots_adjust(left=0.19, right=0.95, top=0.80, bottom=0.15)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_path,
        dpi=100,
        facecolor=background,
        metadata={
            "Title": f"F1 Fantasy {year} mid-season points and value report",
            "Author": "BoxBoxF1Fantasy",
            "Description": "Recorded driver fantasy points, season price changes and constructor value after nine completed races.",
        },
    )
    plt.close(fig)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("forecast", "midseason"), default="forecast")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--season-summary", type=Path, default=DEFAULT_SEASON_SUMMARY)
    parser.add_argument("--driver-history", type=Path, default=DEFAULT_DRIVER_HISTORY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.kind == "midseason":
        season = json.loads(args.season_summary.read_text(encoding="utf-8"))
        history = json.loads(args.driver_history.read_text(encoding="utf-8"))
        output = args.output or DEFAULT_IMAGES_DIR / season_report_slug(int(season.get("season") or 2026))
        built = build_midseason_report_chart(season, history, output)
        print(f"Built SEO mid-season chart -> {built}")
        return
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    output = args.output or DEFAULT_IMAGES_DIR / chart_slug(
        predictions.get("race", "current-race"),
        int(predictions.get("season") or 2026),
    )
    built = build_current_forecast_chart(predictions, output)
    print(f"Built SEO forecast chart -> {built}")


if __name__ == "__main__":
    main()
