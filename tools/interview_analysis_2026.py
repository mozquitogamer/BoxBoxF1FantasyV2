"""Build an interview-focused statistical summary of the completed 2026 season.

The script reads only canonical website/seed JSON files and prints compact tables that
are easy to audit against the source data. It deliberately treats cancelled rounds as
calendar gaps and works in completed-race order.
"""

from __future__ import annotations

import itertools
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WEB = ROOT / "web" / "public" / "data"


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def fmt(value, digits=1):
    return f"{value:.{digits}f}"


def slope(values):
    if len(values) < 2:
        return 0.0
    xs = list(range(len(values)))
    xbar = statistics.mean(xs)
    ybar = statistics.mean(values)
    denom = sum((x - xbar) ** 2 for x in xs)
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, values)) / denom


def table(headers, rows):
    rendered = [[str(v) for v in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rendered:
        widths = [max(widths[i], len(row[i])) for i in range(len(headers))]
    print(" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("-+-".join("-" * width for width in widths))
    for row in rendered:
        print(" | ".join(row[i].ljust(widths[i]) for i in range(len(headers))))


drivers_seed = load(DATA / "seed" / "drivers.json")["drivers"]
constructors_seed = load(DATA / "seed" / "constructors.json")["constructors"]
races_seed = load(DATA / "seed" / "races.json")["races"]
official = load(DATA / "seed" / "official_fantasy_points.json")["rounds"]
prices = load(DATA / "seed" / "fantasy_prices.json")
horizon = load(WEB / "horizon_projections.json")
round14 = load(WEB / "predictions_round14_pre_fp.json")

driver_names = {
    row["driver_id"]: f'{row["first_name"]} {row["last_name"]}' for row in drivers_seed
}
driver_teams = {row["driver_id"]: row["constructor_id"] for row in drivers_seed}
constructor_names = {row["constructor_id"]: row["name"] for row in constructors_seed}
race_names = {row["round"]: row["name"] for row in races_seed}

completed_rounds = sorted(int(key) for key in official)
driver_ids = list(official[str(completed_rounds[0])]["drivers"])
constructor_ids = list(official[str(completed_rounds[0])]["constructors"])

driver_points = {
    driver_id: [official[str(rnd)]["drivers"][driver_id] for rnd in completed_rounds]
    for driver_id in driver_ids
}
constructor_points = {
    constructor_id: [official[str(rnd)]["constructors"][constructor_id] for rnd in completed_rounds]
    for constructor_id in constructor_ids
}

actual_drivers = defaultdict(list)
actual_constructors = defaultdict(list)
for rnd in completed_rounds:
    actual = load(WEB / f"actual_round{rnd}.json")
    for row in actual["drivers"]:
        actual_drivers[row["driver_id"]].append(row)
    for row in actual["constructors"]:
        actual_constructors[row["constructor_id"]].append(row)

price_history = prices["price_history"]
start_driver_prices = price_history["0"]["drivers"]
start_constructor_prices = price_history["0"]["constructors"]
end_driver_prices = price_history[str(completed_rounds[-1])]["drivers"]
end_constructor_prices = price_history[str(completed_rounds[-1])]["constructors"]


def asset_stats(asset_id, points, start_price, end_price, actual_rows=None):
    first5 = statistics.mean(points[:5])
    last5 = statistics.mean(points[-5:])
    result = {
        "id": asset_id,
        "total": sum(points),
        "avg": statistics.mean(points),
        "median": statistics.median(points),
        "sd": statistics.pstdev(points),
        "floor": min(points),
        "ceiling": max(points),
        "negative": sum(value < 0 for value in points),
        "twenty_plus": sum(value >= 20 for value in points),
        "thirty_plus": sum(value >= 30 for value in points),
        "first5": first5,
        "last5": last5,
        "delta5": last5 - first5,
        "recent3": statistics.mean(points[-3:]),
        "slope": slope(points),
        "start_price": start_price,
        "end_price": end_price,
        "price_delta": end_price - start_price,
        "ppm_start": sum(points) / start_price,
        "ppm_current": sum(points) / end_price,
    }
    if actual_rows:
        result.update(
            {
                "dnfs": sum(row["is_dnf"] or row["is_dsq"] or row["is_dns"] for row in actual_rows),
                "overtakes": sum(row["overtakes"] for row in actual_rows),
                "positions_gained": sum(row["positions_gained"] for row in actual_rows),
                "quali_points": sum(row["quali_points"] for row in actual_rows),
                "race_finish_points": sum(row["race_finish_points"] for row in actual_rows),
                "position_points": sum(row["position_points"] for row in actual_rows),
                "overtake_points": sum(row["overtake_points"] for row in actual_rows),
                "fl_points": sum(row["fastest_lap_points"] for row in actual_rows),
                "dotd_points": sum(row["dotd_points"] for row in actual_rows),
                "dnf_penalty": sum(row["dnf_penalty"] for row in actual_rows),
                "sprint_points": sum(row["sprint_points"] for row in actual_rows),
            }
        )
    return result


driver_stats = {
    driver_id: asset_stats(
        driver_id,
        driver_points[driver_id],
        start_driver_prices[driver_id],
        end_driver_prices[driver_id],
        actual_drivers[driver_id],
    )
    for driver_id in driver_ids
}
constructor_stats = {
    constructor_id: asset_stats(
        constructor_id,
        constructor_points[constructor_id],
        start_constructor_prices[constructor_id],
        end_constructor_prices[constructor_id],
    )
    for constructor_id in constructor_ids
}


print(f"COMPLETED RACES: {len(completed_rounds)} ({', '.join(map(str, completed_rounds))})")
print()
print("DRIVERS — TOTAL, CONSISTENCY, AND VALUE")
ranked = sorted(driver_stats.values(), key=lambda row: row["total"], reverse=True)
table(
    ["#", "Driver", "Pts", "Avg", "Med", "SD", "Neg", "20+", "DNF", "£ start→now", "Pts/£now"],
    [
        (
            index,
            f'{row["id"]} {driver_names[row["id"]]}',
            row["total"],
            fmt(row["avg"]),
            fmt(row["median"]),
            fmt(row["sd"]),
            row["negative"],
            row["twenty_plus"],
            row["dnfs"],
            f'{row["start_price"]:.1f}→{row["end_price"]:.1f}',
            fmt(row["ppm_current"]),
        )
        for index, row in enumerate(ranked, 1)
    ],
)

print()
print("DRIVER TREND — FIRST FIVE COMPLETED RACES VS LAST FIVE")
trend = sorted(driver_stats.values(), key=lambda row: row["delta5"], reverse=True)
table(
    ["Driver", "First5 avg", "Last5 avg", "Change", "Recent3", "Price Δ"],
    [
        (
            f'{row["id"]} {driver_names[row["id"]]}',
            fmt(row["first5"]),
            fmt(row["last5"]),
            f'{row["delta5"]:+.1f}',
            fmt(row["recent3"]),
            f'{row["price_delta"]:+.1f}',
        )
        for row in trend
    ],
)

print()
print("DRIVER SCORING SOURCES")
table(
    ["Driver", "Quali", "Finish", "+/−pos", "OT", "Sprint", "FL", "DOTD", "DNF pen"],
    [
        (
            row["id"],
            row["quali_points"],
            row["race_finish_points"],
            row["position_points"],
            row["overtake_points"],
            row["sprint_points"],
            row["fl_points"],
            row["dotd_points"],
            row["dnf_penalty"],
        )
        for row in ranked
    ],
)

print()
print("CONSTRUCTORS — TOTAL, TREND, CONSISTENCY, AND VALUE")
ranked_constructors = sorted(constructor_stats.values(), key=lambda row: row["total"], reverse=True)
table(
    ["#", "Constructor", "Pts", "Avg", "SD", "Neg", "First5", "Last5", "Δ", "£ start→now", "Pts/£now"],
    [
        (
            index,
            constructor_names[row["id"]],
            row["total"],
            fmt(row["avg"]),
            fmt(row["sd"]),
            row["negative"],
            fmt(row["first5"]),
            fmt(row["last5"]),
            f'{row["delta5"]:+.1f}',
            f'{row["start_price"]:.1f}→{row["end_price"]:.1f}',
            fmt(row["ppm_current"]),
        )
        for index, row in enumerate(ranked_constructors, 1)
    ],
)

print()
print("TEAMMATE GAPS")
by_team = defaultdict(list)
for driver_id in driver_ids:
    by_team[driver_teams[driver_id]].append(driver_id)
team_rows = []
for team_id, pair in by_team.items():
    if len(pair) != 2:
        continue
    pair = sorted(pair, key=lambda driver_id: driver_stats[driver_id]["total"], reverse=True)
    leader, trailer = pair
    team_rows.append(
        (
            constructor_names[team_id],
            leader,
            driver_stats[leader]["total"],
            trailer,
            driver_stats[trailer]["total"],
            driver_stats[leader]["total"] - driver_stats[trailer]["total"],
            fmt(driver_stats[leader]["recent3"] - driver_stats[trailer]["recent3"]),
        )
    )
table(
    ["Team", "Lead", "Pts", "Mate", "Pts", "Season gap", "Recent3 gap/race"],
    sorted(team_rows, key=lambda row: row[5], reverse=True),
)

print()
print("ROUND CHAOS / CHIP HINDSIGHT")
round_rows = []
for index, rnd in enumerate(completed_rounds):
    dvals = {driver_id: driver_points[driver_id][index] for driver_id in driver_ids}
    cvals = {constructor_id: constructor_points[constructor_id][index] for constructor_id in constructor_ids}
    negatives = [value for value in itertools.chain(dvals.values(), cvals.values()) if value < 0]
    dnfs = sum(
        row["is_dnf"] or row["is_dsq"] or row["is_dns"]
        for driver_id in driver_ids
        for row in [actual_drivers[driver_id][index]]
    )
    best_driver = max(dvals, key=dvals.get)
    round_rows.append(
        (
            rnd,
            race_names[rnd].replace(" Grand Prix", ""),
            dnfs,
            len(negatives),
            -sum(negatives),
            best_driver,
            dvals[best_driver],
            sum(dvals.values()),
            sum(cvals.values()),
        )
    )
table(
    ["R", "Race", "DNF/DSQ", "Neg assets", "Neg damage", "Best driver", "Pts", "Driver field", "Ctor field"],
    round_rows,
)

sprint_rounds = {row["round"] for row in races_seed if row.get("sprint")}
sprint_rows = [row for row in round_rows if row[0] in sprint_rounds]
normal_rows = [row for row in round_rows if row[0] not in sprint_rounds]


def group_round_summary(rows):
    return {
        "races": len(rows),
        "driver_field": statistics.mean(row[7] for row in rows),
        "constructor_field": statistics.mean(row[8] for row in rows),
        "best_driver": statistics.mean(row[6] for row in rows),
        "dnfs": statistics.mean(row[2] for row in rows),
        "negative_damage": statistics.mean(row[4] for row in rows),
    }


sprint_summary = group_round_summary(sprint_rows)
normal_summary = group_round_summary(normal_rows)
print()
print("SPRINT WEEKEND EFFECT")
table(
    ["Weekend", "Races", "Driver field avg", "Ctor field avg", "Best-driver avg", "DNF avg", "Neg damage avg"],
    [
        (
            label,
            summary["races"],
            fmt(summary["driver_field"]),
            fmt(summary["constructor_field"]),
            fmt(summary["best_driver"]),
            fmt(summary["dnfs"], 2),
            fmt(summary["negative_damage"]),
        )
        for label, summary in (("Sprint", sprint_summary), ("Normal", normal_summary))
    ],
)
print(
    "Sprint uplift: "
    f'{(sprint_summary["driver_field"] / normal_summary["driver_field"] - 1) * 100:.1f}% driver field, '
    f'{(sprint_summary["constructor_field"] / normal_summary["constructor_field"] - 1) * 100:.1f}% constructor field, '
    f'{(sprint_summary["best_driver"] / normal_summary["best_driver"] - 1) * 100:.1f}% best-driver ceiling.'
)


def best_lineup(driver_scores, constructor_scores, driver_prices, constructor_prices, cap=100.0):
    constructor_pairs = []
    for pair in itertools.combinations(constructor_ids, 2):
        price = sum(constructor_prices[item] for item in pair)
        score = sum(constructor_scores[item] for item in pair)
        constructor_pairs.append((price, score, pair))
    constructor_pairs.sort(key=lambda row: row[0])
    best = (-math.inf, None)
    for driver_combo in itertools.combinations(driver_ids, 5):
        dprice = sum(driver_prices[item] for item in driver_combo)
        if dprice > cap:
            continue
        dscore = sum(driver_scores[item] for item in driver_combo) + max(driver_scores[item] for item in driver_combo)
        remaining = cap - dprice
        for cprice, cscore, constructor_pair in constructor_pairs:
            if cprice > remaining:
                break
            total = dscore + cscore
            if total > best[0]:
                best = (total, (driver_combo, constructor_pair, dprice + cprice))
    return best


print()
print("PERFECT-HINDSIGHT LIMITLESS VALUE (normal score includes 2x captain)")
limitless_rows = []
for index, rnd in enumerate(completed_rounds):
    dvals = {driver_id: driver_points[driver_id][index] for driver_id in driver_ids}
    cvals = {constructor_id: constructor_points[constructor_id][index] for constructor_id in constructor_ids}
    round_prices = price_history[str(completed_rounds[index - 1]) if index else "0"]
    normal_score, normal_lineup = best_lineup(
        dvals, cvals, round_prices["drivers"], round_prices["constructors"]
    )
    limitless_drivers = sorted(driver_ids, key=dvals.get, reverse=True)[:5]
    limitless_constructors = sorted(constructor_ids, key=cvals.get, reverse=True)[:2]
    limitless_score = (
        sum(dvals[item] for item in limitless_drivers)
        + max(dvals[item] for item in limitless_drivers)
        + sum(cvals[item] for item in limitless_constructors)
    )
    limitless_rows.append(
        (
            rnd,
            race_names[rnd].replace(" Grand Prix", ""),
            int(normal_score),
            int(limitless_score),
            int(limitless_score - normal_score),
            ",".join(limitless_drivers),
            ",".join(limitless_constructors),
        )
    )
table(["R", "Race", "£100m best", "Limitless", "Uplift", "Top drivers", "Top ctors"], limitless_rows)

print()
print("PRICE MOVERS")
driver_price_rank = sorted(driver_stats.values(), key=lambda row: row["price_delta"], reverse=True)
constructor_price_rank = sorted(constructor_stats.values(), key=lambda row: row["price_delta"], reverse=True)
table(
    ["Driver", "Price Δ", "Season pts", "Pts/£ now", "Last5 avg"],
    [
        (row["id"], f'{row["price_delta"]:+.1f}', row["total"], fmt(row["ppm_current"]), fmt(row["last5"]))
        for row in driver_price_rank
    ],
)
print()
table(
    ["Constructor", "Price Δ", "Season pts", "Pts/£ now", "Last5 avg"],
    [
        (constructor_names[row["id"]], f'{row["price_delta"]:+.1f}', row["total"], fmt(row["ppm_current"]), fmt(row["last5"]))
        for row in constructor_price_rank
    ],
)

print()
print("FORWARD WATCHLIST — R14 PRE-FP PLUS R15-R19 PRIORS")
future_driver = defaultdict(list)
future_constructor = defaultdict(list)
for row in round14["drivers"]:
    future_driver[row["driver_id"]].append((14, row["expected_points"]))
for row in round14["constructors"]:
    future_constructor[row["constructor_id"]].append((14, row["expected_points"]))
for rnd_text, payload in horizon["rounds"].items():
    rnd = int(rnd_text)
    for driver_id, row in payload["drivers"].items():
        future_driver[driver_id].append((rnd, row["expected_points"]))
    for constructor_id, row in payload["constructors"].items():
        future_constructor[constructor_id].append((rnd, row["expected_points"]))

future_driver_rows = []
for driver_id, values in future_driver.items():
    values.sort()
    total = sum(value for _, value in values)
    future_driver_rows.append(
        (
            driver_id,
            fmt(total),
            fmt(total / len(values)),
            end_driver_prices[driver_id],
            fmt(total / end_driver_prices[driver_id]),
            ", ".join(f"R{rnd}:{value:.1f}" for rnd, value in values),
        )
    )
table(
    ["Driver", "R14-19 pts", "Avg", "Price", "6-race pts/£", "Round projections"],
    sorted(future_driver_rows, key=lambda row: float(row[1]), reverse=True),
)
print()
future_constructor_rows = []
for constructor_id, values in future_constructor.items():
    values.sort()
    total = sum(value for _, value in values)
    future_constructor_rows.append(
        (
            constructor_names[constructor_id],
            fmt(total),
            fmt(total / len(values)),
            end_constructor_prices[constructor_id],
            fmt(total / end_constructor_prices[constructor_id]),
            ", ".join(f"R{rnd}:{value:.1f}" for rnd, value in values),
        )
    )
table(
    ["Constructor", "R14-19 pts", "Avg", "Price", "6-race pts/£", "Round projections"],
    sorted(future_constructor_rows, key=lambda row: float(row[1]), reverse=True),
)
