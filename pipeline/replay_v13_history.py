"""Recalculate V13 from saved practice forecasts without rewriting live records.

No prediction model is trained or run here. Forecasts after lock are rejected;
the explicitly labelled R1/R2/R3/R6 research fallbacks are the sole exception.
The original experiment's four research chip dates remain policy inputs. From
R14, 3x timing uses only a horizon forecast archived before that weekend's lock.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import build_v13_manager as v13
from pipeline import publish_v13_decision as publisher
from pipeline import simulate_fantasy_season_strategies as season

ACTIVE_PATH = ROOT / "data/v13/active_replay.json"
RESEARCH_FALLBACKS = {1, 2, 3, 6}


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save_once(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"Refusing to replace immutable replay input: {path}")
    else:
        path.write_bytes(raw)


def choose_source(candidates, round_num, lock):
    eligible = [c for c in candidates if c["payload"].get("round") == round_num
                and c["payload"].get("phase") == "post_fp"
                and not c["payload"].get("reconstructed")
                and publisher._parse_time(c["payload"]["generated_at"]) < lock
                and not c["payload"].get("final_fix", {}).get("qualifying_locked")]
    if not eligible:
        raise ValueError(f"R{round_num}: no genuine pre-lock practice forecast")
    return max(eligible, key=lambda c: publisher._parse_time(c["payload"]["generated_at"]))


def scan_sources(roots):
    candidates = []
    for root in roots:
        paths = list((root / "web/public/data").glob("predictions*.json"))
        paths += list((root / "data/audit/snapshots").glob("round*/*.json"))
        for path in sorted(paths):
            wrapper = json.loads(path.read_bytes())
            payload = wrapper.get("predictions", wrapper)
            if (payload.get("phase") != "post_fp" or not payload.get("generated_at")
                    or len(payload.get("drivers", [])) < 20):
                continue
            candidates.append({"payload": payload, "source": str(path.relative_to(root)).replace("\\", "/"),
                               "source_sha256": digest(path.read_bytes()),
                               "sessions": payload.get("fp_sessions_included", wrapper.get("metadata", {}).get("fp_sessions_included", []))})
    return candidates


def historical_horizon(lock):
    """Read a saved horizon as it existed before lock; never today's horizon."""
    path = "web/public/data/horizon_projections.json"
    commits = subprocess.check_output(
        ["git", "log", "-40", "--format=%H", f"--before={lock.isoformat()}", "HEAD", "--", path],
        cwd=ROOT, text=True).splitlines()
    for commit in commits:
        raw = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)
        payload = json.loads(raw)
        stamp = payload.get("generated_at")
        if stamp and publisher._parse_time(stamp) < lock:
            return {"commit": commit, "payload": payload, "sha256": digest(raw)}
    return None


def git_forecasts(round_num, lock):
    """Recover exports overwritten later but retained by Git before lock."""
    output = []
    for path in ("web/public/data/predictions.json", f"web/public/data/predictions_round{round_num}.json"):
        commits = subprocess.check_output(
            ["git", "log", "-20", "--format=%H", f"--before={lock.isoformat()}", "HEAD", "--", path],
            cwd=ROOT, text=True).splitlines()
        for commit in commits:
            raw = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)
            payload = json.loads(raw)
            if payload.get("round") == round_num and payload.get("phase") == "post_fp" and payload.get("generated_at"):
                output.append({"payload": payload, "source": f"git:{commit}:{path}",
                               "source_sha256": digest(raw), "sessions": payload.get("fp_sessions_included", [])})
    return output


def three_x_choice(round_num, normal, data, horizon):
    lookup = dict(zip(data.drivers, data.driver_projection))
    current = sum(sorted((float(lookup[k]) for k in normal.drivers), reverse=True)[:2])
    future = []
    if horizon:
        rows = horizon["payload"].get("rounds", {})
        for row in rows.values() if isinstance(rows, dict) else rows:
            if int(row["round"]) <= round_num:
                continue
            scores = sorted((float(x["expected_points"]) for x in row["drivers"].values()), reverse=True)
            if len(scores) >= 2:
                future.append((scores[0] + scores[1], int(row["round"])))
    benchmark = max(future) if future else None
    play = benchmark is not None and current >= benchmark[0]
    return ("3x_boost" if play else None), {
        "result": "play" if play else "save", "current_selected_team_extra_points": round(current, 2),
        "largest_remaining_priors_top_two": round(benchmark[0], 2) if benchmark else None,
        "largest_remaining_priors_round": benchmark[1] if benchmark else None,
        "reason": "Archived pre-lock horizon comparison" if benchmark else "No historical future benchmark; chip retained",
        "horizon_sha256": horizon["sha256"] if horizon else None,
    }


def replay(rounds, sources, horizons, research_schedule, old_public):
    state = None
    cumulative = 0.0
    chips_used = {}
    history = []
    driver_names, _ = v13._names()
    old_rows = {r["round"]: r for r in old_public["research_replay"]["rounds"] + old_public["live_history"]}
    for data in rounds:
        n = data.round_num
        combos = season.build_combo_matrices(data)
        price_weight = 20.0 if n <= 13 else v13.live_price_gain_value(n)
        kwargs = dict(round_data=data, combos=combos, state=state, strategy=v13.V13_STRATEGY,
                      risk_profile=v13.V13_RISK_PROFILE, price_gain_value=price_weight)
        chip = research_schedule.get(str(n)) if n <= 13 else None
        chip_detail = {"result": "research_policy", "reason": "Original V13 research chip timing retained"}
        normal = season.choose_lineup(**kwargs, chip=None)
        if n > 13 and "3x_boost" not in chips_used:
            chip, chip_detail = three_x_choice(n, normal, data, horizons.get(n))
        if chip in chips_used:
            raise ValueError(f"R{n}: chip already used: {chip}")
        candidate = season.choose_lineup(**kwargs, chip=chip) if chip else normal
        budget = season.STARTING_BUDGET if state is None else state.budget
        free_before = 0 if state is None else state.free_transfers
        if chip != "limitless" and candidate.cost > budget + 1e-6:
            raise ValueError(f"R{n}: replay selected an over-budget team")
        if chip == "limitless" and state:
            drivers, constructors, bank = state.drivers, state.constructors, state.bank
            transfers, penalty = 0, 0
        else:
            drivers, constructors = candidate.drivers, candidate.constructors
            bank = round(budget - candidate.cost, 1)
            transfers = candidate.transfers if state else 0
            penalty = candidate.transfer_penalty
        free_next = (season.next_free_transfers(free_before, transfers, chip)
                     if state else season.INITIAL_FREE_TRANSFERS_AFTER_R1)
        gross, actual_captain, actual_second, _ = season._actual_score(candidate=candidate, round_data=data, chip=chip)
        fix = None
        if "final_fix" not in chips_used and chip is None:
            archive = v13._valid_post_quali_archive(n)
            if archive:
                driver_names.update({d["driver_id"]: d.get("name", d["driver_id"]) for d in v13._load_json(archive)["drivers"]})
            fix = v13._final_fix({"round": n, "persistent_drivers": list(drivers),
                                 "bank_after_transfers": bank, "captain": candidate.captain}, driver_names)
            if fix:
                drivers = tuple(fix["incoming"] if k == fix["outgoing"] else k for k in drivers)
                bank = fix["bank_after"]
                gross += fix["actual_gain"]
                chips_used["final_fix"] = n
        next_state = season.TeamState(drivers, constructors, bank, budget, free_next)
        next_state.budget = season._closing_team_value(next_state, data)
        actual = round(float(gross - penalty), 1)
        cumulative = round(cumulative + actual, 1)
        if chip:
            chips_used[chip] = n
        source = sources[n]
        decision = {
            "round": n, "race": data.race_name, "phase": "post_fp", "status": "retrospective_correction",
            "archive": data.archive_path, "archive_sha256": v13._sha256(ROOT / data.archive_path),
            "source_generated_at": source["generated_at"], "lock_deadline": publisher._lock_deadline(n),
            "drivers": list(candidate.drivers), "constructors": list(candidate.constructors),
            "persistent_drivers": list(drivers), "persistent_constructors": list(constructors),
            "captain": candidate.captain, "second_boost": candidate.second_captain, "chip": chip,
            "team_cost": candidate.cost, "budget_before": budget, "transfers": transfers,
            "transfer_penalty": penalty, "projected_points": candidate.projected_points,
            "projected_price_gain": candidate.projected_gain, "downside_risk": candidate.downside_risk,
            "chip_decision": chip_detail, "policy": v13.live_policy(n) if n > 13 else {"price_gain_weight": 20.0},
            "fp_sessions_included": source["sessions"], "source_quality": source["quality"],
        }
        history.append({"round": n, "race": data.race_name,
                        "provenance": "reconstructed" if source["quality"] == "reconstructed" else "corrected_replay",
                        "early_thoughts": old_rows.get(n, {}).get("early_thoughts"), "post_fp_final": decision,
                        "final_fix": fix, "actual_points": actual, "projected_points": candidate.projected_points,
                        "score_delta_vs_projection": round(actual - candidate.projected_points, 1),
                        "cumulative_points": cumulative, "budget_after": next_state.budget,
                        "bank_after": bank, "free_transfers_next": free_next,
                        "actual_captain": fix["incoming"] if fix and fix["boost_transferred"] else actual_captain,
                        "actual_second_boost": actual_second})
        print(f"R{n:2}: {actual:6.1f} pts; total {cumulative:7.1f}; budget ${next_state.budget:.1f}M; chip {chip or '-'}; Final Fix {bool(fix)}", flush=True)
        state = next_state
    return history, state, chips_used


def build_corrected_payload():
    pointer = v13._load_json(ACTIVE_PATH)
    path = ROOT / pointer["path"]
    if digest(path.read_bytes()) != pointer["sha256"]:
        raise ValueError("Active V13 replay ledger hash mismatch")
    ledger = v13._load_json(path)
    public = v13._load_json(ROOT / ledger["previous_public"])
    for source in ledger["sources"].values():
        for driver in v13._load_json(ROOT / source["archive"])["drivers"]:
            public["labels"]["drivers"][driver["driver_id"]] = driver.get("name", driver["driver_id"])
    live_forecast = v13.WEB_DATA_DIR / "predictions.json"
    if live_forecast.exists():
        for driver in v13._load_json(live_forecast)["drivers"]:
            public["labels"]["drivers"][driver["driver_id"]] = driver.get("name", driver["driver_id"])
    official = v13._load_json(v13.SEED_DIR / "official_fantasy_points.json")["rounds"]
    state = ledger["state"]
    manager = {"rounds": [{"round": ledger["through_round"], "free_transfers_next": state["free_transfers"]}],
               "summary": {"final_drivers": state["drivers"], "final_constructors": state["constructors"],
                           "final_bank": state["bank"], "final_budget": state["budget"], "season_points": ledger["total_points"]},
               "chip_schedule": {str(n): chip for chip, n in ledger["chips_used"].items()}}
    later, settled, chips = v13._live_rounds_and_state(manager, None, official)
    all_rows = copy.deepcopy(ledger["history"]) + later
    # Older replay ledgers preserve the original gross-forecast field. Present
    # comparable net forecasts without editing those immutable input records.
    for row in all_rows:
        decision = row["post_fp_final"]
        if row["round"] <= ledger["through_round"] and decision.get("points_basis") != "net_after_transfers":
            gross = decision["projected_points"]
            decision.update(projected_points_gross=gross, points_basis="net_after_transfers",
                            projected_points=round(gross - decision.get("transfer_penalty", 0), 2))
            row["projected_points"] = decision["projected_points"]
            row["score_delta_vs_projection"] = round(row["actual_points"] - row["projected_points"], 1)
    research = [r for r in all_rows if r["round"] <= 13]
    live = [r for r in all_rows if r["round"] > 13]
    last = all_rows[-1]
    next_round = v13._next_scheduled_round(last["round"])
    fixes = sum((r.get("final_fix") or {}).get("actual_gain", 0) for r in research)
    research_total = research[-1]["cumulative_points"]
    public["research_replay"].update({"rounds": research, "total_points": research_total,
        "base_points_before_final_fix": research_total - fixes, "final_fix_adjustment": fixes,
        "final_budget": research[-1]["budget_after"], "final_bank": research[-1]["bank_after"],
        "genuine_archive_points_before_final_fix": sum(r["actual_points"] - (r.get("final_fix") or {}).get("actual_gain", 0)
            for r in research if ledger["sources"][str(r["round"])]["quality"] == "pre_lock"),
        "disclaimer": "Retrospective correction using the latest saved pre-lock practice forecasts. R1–R3 are reconstructed; R6 has no verifiable pre-lock forecast. Older session coverage is not fully recorded."})
    public["live_history"] = live
    public["live_status"] = {"status": "corrected_replay", "through_round": last["round"], "race": last["race"],
        "round_points": last["actual_points"], "projected_points": last["projected_points"],
        "score_delta_vs_projection": last["score_delta_vs_projection"], "total_points": last["cumulative_points"],
        "budget": settled["budget"], "bank": settled["bank"]}
    public["current_state"] = {"as_of_round": last["round"], "drivers": settled["drivers"],
        "constructors": settled["constructors"], "budget": settled["budget"], "bank": settled["bank"],
        "free_transfers": settled["free_transfers"], "chips_remaining": [c for c in (*season.CHIPS, "final_fix") if c not in chips],
        "chips_used": chips, "next_round": next_round,
        "early_thoughts": v13._live_decision(next_round, "pre_fp") if next_round else None,
        "post_fp_final": v13._live_decision(next_round, "post_fp") if next_round else None}
    public["historical_correction"] = {"generated_at": ledger["generated_at"], "through_round": ledger["through_round"],
        "ledger": pointer["path"], "sha256": pointer["sha256"], "sources": ledger["sources"],
        "previous_total_points": ledger["previous_total_points"], "previous_budget": ledger["previous_budget"],
        "note": "History recalculated from archived practice forecasts. Earlier published decisions are retained. R1–R3 remain reconstructed research; R6 lacks a verifiable pre-lock forecast. FP3 coverage is only claimed where recorded."}
    public["manager"]["policy"]["price_gain_weight"] = round(v13.live_price_gain_value(next_round), 3) if next_round else 0
    public["source"]["active_replay"] = pointer
    public["source"]["live_decisions"] = [r["round"] for r in live]
    public["generated_at"] = datetime.now(timezone.utc).isoformat()
    return public


def validate_ledger(ledger):
    """Reconcile scores and closing balances independently of the optimizer."""
    official = v13._load_json(v13.SEED_DIR / "official_fantasy_points.json")["rounds"]
    cumulative = 0
    prior_budget = season.STARTING_BUDGET
    prior_bank = 0
    used = set()
    for row in ledger["history"]:
        n, decision = row["round"], row["post_fp_final"]
        source = ledger["sources"].get(n, ledger["sources"].get(str(n)))
        if source["quality"] == "pre_lock":
            assert publisher._parse_time(source["generated_at"]) < publisher._parse_time(decision["lock_deadline"])
        else:
            assert n in RESEARCH_FALLBACKS
        score, _, _ = v13._live_actual_score(decision, official[str(n)], n)
        fix = row.get("final_fix")
        if fix:
            assert "final_fix" not in used
            used.add("final_fix")
            score += fix["actual_gain"]
        assert round(score, 1) == row["actual_points"], (n, score, row["actual_points"])
        cumulative = round(cumulative + score, 1)
        assert cumulative == row["cumulative_points"]
        chip = decision.get("chip")
        if chip:
            assert chip not in used
            used.add(chip)
        assert decision["budget_before"] == prior_budget
        expected_bank = prior_bank if chip == "limitless" else round(prior_budget - decision["team_cost"], 1)
        if fix:
            assert fix["bank_before"] == expected_bank
            expected_bank = fix["bank_after"]
        assert expected_bank >= 0 and expected_bank == row["bank_after"]
        prices = v13._price_after_round(n)
        close = expected_bank + sum(float(prices["drivers"][k]) for k in decision["persistent_drivers"])
        close += sum(float(prices["constructors"][k]) for k in decision["persistent_constructors"])
        assert round(close, 1) == row["budget_after"], n
        prior_budget, prior_bank = row["budget_after"], expected_bank
    assert cumulative == ledger["total_points"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through-round", type=int, required=True)
    parser.add_argument("--extra-root", type=Path, action="append", default=[])
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    old = v13._load_json(v13.OUTPUT_PATH)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    directory = ROOT / "data/v13/replays" / stamp
    candidates = scan_sources([ROOT, *args.extra_root])
    official = v13._load_json(v13.SEED_DIR / "official_fantasy_points.json")["rounds"]
    numbers = sorted(int(n) for n in official if int(n) <= args.through_round)
    sources, paths, horizons = {}, {}, {}
    for n in numbers:
        lock = publisher._parse_time(publisher._lock_deadline(n))
        candidates.extend(git_forecasts(n, lock))
        try:
            chosen = choose_source(candidates, n, lock)
            quality = "pre_lock"
        except ValueError:
            if n not in RESEARCH_FALLBACKS:
                raise
            original = v13.WEB_DATA_DIR / f"predictions_round{n}_post_fp.json"
            chosen = {"payload": v13._load_json(original), "source": str(original.relative_to(ROOT)).replace("\\", "/"),
                      "source_sha256": digest(original.read_bytes()), "sessions": []}
            quality = "reconstructed" if n <= 3 else "unverified_pre_lock_research"
        raw = canonical(chosen["payload"])
        target = v13.WEB_DATA_DIR / "v13_sources" / f"round{n}_{digest(raw)[:16]}.json"
        save_once(target, raw)
        paths[n] = target
        sources[n] = {k: chosen[k] for k in ("source", "source_sha256", "sessions")}
        sources[n].update({"generated_at": chosen["payload"]["generated_at"], "quality": quality,
                           "archive": str(target.relative_to(ROOT)).replace("\\", "/"), "archive_sha256": digest(raw)})
        if n > 13:
            horizons[n] = historical_horizon(lock)
    experiment = v13._v13_manager(v13._load_json(v13.EXPERIMENT_PATH))
    history, state, chips = replay(season.load_rounds(args.through_round, archive_paths=paths,
                                  prefer_archive_prices={n for n, s in sources.items() if s["quality"] == "pre_lock"}), sources,
                                  horizons, experiment["chip_schedule"], old)
    directory.mkdir(parents=True, exist_ok=True)
    previous = directory / "previous_public.json"
    save_once(previous, canonical(old))
    ledger = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "through_round": numbers[-1], "previous_public": str(previous.relative_to(ROOT)).replace("\\", "/"),
        "previous_total_points": old["live_status"]["total_points"], "previous_budget": old["current_state"]["budget"],
        "sources": sources, "horizons": horizons, "research_chip_schedule": experiment["chip_schedule"],
        "history": history, "total_points": history[-1]["cumulative_points"], "chips_used": chips,
        "state": {"drivers": list(state.drivers), "constructors": list(state.constructors),
                  "bank": state.bank, "budget": state.budget, "free_transfers": state.free_transfers}}
    validate_ledger(ledger)
    ledger["code_sha256"] = {name: digest((ROOT / "pipeline" / name).read_bytes()) for name in
                             ("replay_v13_history.py", "simulate_fantasy_season_strategies.py", "publish_v13_decision.py")}
    path = directory / "ledger.json"
    save_once(path, canonical(ledger))
    if args.activate:
        ACTIVE_PATH.write_bytes(canonical({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path.read_bytes())}))
        v13.main()
    print(f"Replay saved: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
