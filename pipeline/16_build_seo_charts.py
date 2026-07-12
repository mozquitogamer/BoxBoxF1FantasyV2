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
DEFAULT_IMAGES_DIR = ROOT / "web" / "public" / "images"


def chart_slug(race: str, year: int) -> str:
    name = race.lower().replace("grand prix", "gp")
    slug = "-".join("".join(ch if ch.isalnum() else " " for ch in name).split())
    return f"{slug}-{year}-fantasy-forecast.png"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    output = args.output or DEFAULT_IMAGES_DIR / chart_slug(
        predictions.get("race", "current-race"),
        int(predictions.get("season") or 2026),
    )
    built = build_current_forecast_chart(predictions, output)
    print(f"Built SEO forecast chart -> {built}")


if __name__ == "__main__":
    main()
