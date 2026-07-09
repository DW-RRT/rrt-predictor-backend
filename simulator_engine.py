from typing import Any, Dict, List, Optional
import json
import uuid

from database import fetch_all, fetch_one, execute_sql


SIMULATOR_VERSION = "2.15.2"
MODEL_VERSION = "2.8.1"


CURRENT_MODEL_WEIGHTS = {
    "last10": 14.0,
    "win_place": 8.0,
    "track_record": 8.0,
    "distance_record": 8.0,
    "track_distance": 8.0,
    "track_condition": 8.0,
    "trainer": 7.0,
    "jockey": 7.0,
    "trainer_jockey": 10.0,
    "barrier": 5.0,
    "weight": 5.0,
    "market": 12.0,
}


DEFAULT_TEST_WEIGHTS = {
    "last10": 15.0,
    "win_place": 9.0,
    "track_record": 7.0,
    "distance_record": 7.0,
    "track_distance": 7.0,
    "track_condition": 7.0,
    "trainer": 6.0,
    "jockey": 7.0,
    "trainer_jockey": 9.0,
    "barrier": 4.0,
    "weight": 5.0,
    "market": 14.0,
}


DEFAULT_SINGLE_FACTOR_SUITE = [
    {"factor": "market", "change": 1.0, "label": "Market +1"},
    {"factor": "market", "change": 2.0, "label": "Market +2"},
    {"factor": "win_place", "change": 1.0, "label": "Win / Place +1"},
    {"factor": "last10", "change": 1.0, "label": "Last 10 +1"},
    {"factor": "weight", "change": -1.0, "label": "Weight -1"},
    {"factor": "weight", "change": -2.0, "label": "Weight -2"},
    {"factor": "barrier", "change": 1.0, "label": "Barrier +1"},
    {"factor": "trainer", "change": -1.0, "label": "Trainer -1"},
    {"factor": "trainer_jockey", "change": -1.0, "label": "Trainer / Jockey -1"},
    {"factor": "track_condition", "change": -1.0, "label": "Track Condition -1"},
    {"factor": "distance_record", "change": -1.0, "label": "Distance Record -1"},
    {"factor": "track_record", "change": -1.0, "label": "Track Record -1"},
    {"factor": "track_distance", "change": -1.0, "label": "Track / Distance -1"},
]


FACTOR_SCORE_COLUMNS = {
    "last10": "last10_score",
    "win_place": "win_place_score",
    "track_record": "track_record_score",
    "distance_record": "distance_record_score",
    "track_distance": "track_distance_record_score",
    "track_condition": "track_condition_score",
    "trainer": "trainer_score",
    "jockey": "jockey_score",
    "trainer_jockey": "trainer_jockey_score",
    "barrier": "barrier_score",
    "weight": "weight_score",
    "market": "market_score",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    """PostgreSQL JSONB-safe serialiser for dates, datetimes and Decimal-like values."""
    return json.dumps(value, default=str)


def _normalise_weights(weights: Optional[Dict[str, Any]]) -> Dict[str, float]:
    merged = dict(CURRENT_MODEL_WEIGHTS)
    for key, value in (weights or {}).items():
        if key in merged:
            merged[key] = max(0.0, _to_float(value, merged[key]))
    return merged


def _score_runner_from_weights(row: Dict[str, Any], weights: Dict[str, float]) -> float:
    weighted_sum = 0.0
    weight_total = 0.0
    for factor_key, column in FACTOR_SCORE_COLUMNS.items():
        factor_score = _to_float(row.get(column), 50.0)
        factor_weight = _to_float(weights.get(factor_key), 0.0)
        weighted_sum += factor_score * factor_weight
        weight_total += factor_weight
    if weight_total <= 0:
        return 0.0
    return round(weighted_sum / weight_total, 2)


def _load_completed_runner_rows(min_meeting_date: Optional[str]=None, max_meeting_date: Optional[str]=None) -> List[Dict[str, Any]]:
    where_parts = ["actual_position IS NOT NULL", "race_number IS NOT NULL", "meeting_id IS NOT NULL"]
    params: List[Any] = []
    if min_meeting_date:
        where_parts.append("meeting_date >= %s")
        params.append(min_meeting_date)
    if max_meeting_date:
        where_parts.append("meeting_date <= %s")
        params.append(max_meeting_date)
    where_sql = " AND ".join(where_parts)
    return fetch_all(f"""
        SELECT meeting_id, model_version, track, meeting_date, race_id, race_number,
               runner_key, runner_name, tab_number, final_score, confidence,
               market_price, market_rank, last10_score, win_place_score,
               track_record_score, distance_record_score, track_distance_record_score,
               track_condition_score, trainer_score, jockey_score, trainer_jockey_score,
               barrier_score, weight_score, market_score, actual_position, actual_price,
               hit_win, hit_place, factor_json
        FROM rrt_runner_factor_snapshots
        WHERE {where_sql}
        ORDER BY meeting_date ASC, meeting_id ASC, race_number ASC, runner_name ASC;
    """, tuple(params))


def _group_by_race(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(f"{row.get('meeting_id')}|{row.get('race_number')}", []).append(row)
    return grouped


def _evaluate_race_rows(race_rows: List[Dict[str, Any]], weights: Dict[str, float], roughie_min_price: float=7.0, roughie_min_market_rank: int=5, roughie_min_score: float=50.0) -> Dict[str, Any]:
    scored = [{**row, "simulated_score": _score_runner_from_weights(row, weights)} for row in race_rows]
    ranked = sorted(scored, key=lambda item: (_to_float(item.get("simulated_score")), -_to_float(item.get("market_price"), 9999)), reverse=True)
    top_4_win = ranked[:4]
    top_4_each_way = ranked[4:8] if len(ranked) >= 8 else ranked[:4]
    excluded_keys = {item.get("runner_key") for item in top_4_win + top_4_each_way}
    roughies = []
    for item in ranked:
        if item.get("runner_key") in excluded_keys:
            continue
        price = _to_float(item.get("market_price"))
        market_rank = _to_int(item.get("market_rank"), 99)
        score = _to_float(item.get("simulated_score"))
        if price > 0 and price >= roughie_min_price and market_rank >= roughie_min_market_rank and score >= roughie_min_score:
            roughies.append(item)
    return {"top_4_win": top_4_win, "top_4_each_way": top_4_each_way, "top_4_roughies": roughies[:4]}


def _selection_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "meeting_id": item.get("meeting_id"),
        "track": item.get("track"),
        "meeting_date": item.get("meeting_date"),
        "race_number": item.get("race_number"),
        "runner": item.get("runner_name"),
        "tab_number": item.get("tab_number"),
        "market_price": item.get("market_price"),
        "market_rank": item.get("market_rank"),
        "simulated_score": item.get("simulated_score"),
        "actual_position": item.get("actual_position"),
        "hit_win": item.get("actual_position") == 1,
        "hit_place": item.get("actual_position") in [1, 2, 3],
        "hit_roughie_place": item.get("actual_position") in [1, 2, 3, 4],
    }


def _evaluate_grouped_races(grouped: Dict[str, List[Dict[str, Any]]], weights: Dict[str, float], roughie_min_price: float, roughie_min_market_rank: int, roughie_min_score: float) -> Dict[str, Any]:
    race_results = []
    race_count = len(grouped)
    top_win_hits = 0
    each_way_hits = 0
    each_way_total = 0
    roughie_hits = 0
    roughie_total = 0
    for race_key, race_rows in grouped.items():
        evaluated = _evaluate_race_rows(race_rows, weights, roughie_min_price, roughie_min_market_rank, roughie_min_score)
        win_hit = any(item.get("actual_position") == 1 for item in evaluated["top_4_win"])
        ew_hits = sum(1 for item in evaluated["top_4_each_way"] if item.get("actual_position") in [1,2,3])
        rough_hits = sum(1 for item in evaluated["top_4_roughies"] if item.get("actual_position") in [1,2,3,4])
        top_win_hits += 1 if win_hit else 0
        each_way_hits += ew_hits
        each_way_total += len(evaluated["top_4_each_way"])
        roughie_hits += rough_hits
        roughie_total += len(evaluated["top_4_roughies"])
        first = race_rows[0] if race_rows else {}
        race_results.append({
            "race_key": race_key,
            "meeting_id": first.get("meeting_id"),
            "track": first.get("track"),
            "meeting_date": first.get("meeting_date"),
            "race_number": first.get("race_number"),
            "runner_count": len(race_rows),
            "top_win_hit": win_hit,
            "each_way_hit_count": ew_hits,
            "roughie_hit_count": rough_hits,
            "top_4_win": [_selection_summary(i) for i in evaluated["top_4_win"]],
            "top_4_each_way": [_selection_summary(i) for i in evaluated["top_4_each_way"]],
            "top_4_roughies": [_selection_summary(i) for i in evaluated["top_4_roughies"]],
        })
    top_win_rate = round((top_win_hits / race_count) * 100, 2) if race_count else 0.0
    each_way_rate = round((each_way_hits / each_way_total) * 100, 2) if each_way_total else 0.0
    roughie_rate = round((roughie_hits / roughie_total) * 100, 2) if roughie_total else 0.0
    overall = round((top_win_rate * 0.45) + (each_way_rate * 0.35) + (roughie_rate * 0.20), 2)
    return {
        "race_count": race_count,
        "selection_totals": {"top_win_total": race_count * 4, "top_win_hits": top_win_hits, "each_way_total": each_way_total, "each_way_hits": each_way_hits, "roughie_total": roughie_total, "roughie_hits": roughie_hits},
        "metrics": {"top_win_strike_rate": top_win_rate, "each_way_strike_rate": each_way_rate, "roughie_strike_rate": roughie_rate, "overall_accuracy": overall},
        "race_results_preview": race_results[:25],
    }


def _simulation_recommendation(improvement: Dict[str, Any]) -> Dict[str, Any]:
    overall = _to_float(improvement.get("overall_accuracy"))
    top_win = _to_float(improvement.get("top_win_strike_rate"))
    each_way = _to_float(improvement.get("each_way_strike_rate"))
    roughie = _to_float(improvement.get("roughie_strike_rate"))
    if overall >= 2 and top_win >= 0 and each_way >= 0:
        return {"status": "Promising", "priority": "High", "message": "Simulation improved overall accuracy without weakening top-win or each-way performance."}
    if overall > 0 and roughie > 0:
        return {"status": "Monitor", "priority": "Medium", "message": "Simulation improved roughie performance and total accuracy, but requires more testing before production review."}
    if overall < -1:
        return {"status": "Reject", "priority": "High", "message": "Simulation reduced overall accuracy and should not be promoted."}
    return {"status": "Neutral", "priority": "Medium", "message": "Simulation did not materially outperform the current model."}


def run_weight_simulation(test_weights: Optional[Dict[str, Any]]=None, simulation_name: str="v2.15.0 default simulation", notes: str="", min_meeting_date: Optional[str]=None, max_meeting_date: Optional[str]=None, roughie_min_price: float=7.0, roughie_min_market_rank: int=5, roughie_min_score: float=50.0, save_result: bool=True) -> Dict[str, Any]:
    try:
        rows = _load_completed_runner_rows(min_meeting_date, max_meeting_date)
        grouped = _group_by_race(rows)
        current_weights = _normalise_weights(CURRENT_MODEL_WEIGHTS)
        proposed_weights = _normalise_weights(test_weights or DEFAULT_TEST_WEIGHTS)
        current_result = _evaluate_grouped_races(grouped, current_weights, 10.0, 6, 45.0)
        simulated_result = _evaluate_grouped_races(grouped, proposed_weights, roughie_min_price, roughie_min_market_rank, roughie_min_score)
        cm = current_result.get("metrics") or {}
        sm = simulated_result.get("metrics") or {}
        improvement = {k: round(_to_float(sm.get(k)) - _to_float(cm.get(k)), 2) for k in ["top_win_strike_rate", "each_way_strike_rate", "roughie_strike_rate", "overall_accuracy"]}
        simulation_id = str(uuid.uuid4())
        response = {
            "success": True,
            "provider": "RRT Predictor",
            "simulator_version": SIMULATOR_VERSION,
            "report": "historical_weight_simulation",
            "simulation_id": simulation_id,
            "simulation_name": simulation_name,
            "simulation_group": simulation_group,
            "factor_tested": factor_tested,
            "old_weight": old_weight,
            "new_weight": new_weight,
            "change_amount": change_amount,
            "analysis_only": True,
            "prediction_model_changed": False,
            "dataset": {"completed_runner_rows": len(rows), "race_count": len(grouped), "min_meeting_date": min_meeting_date, "max_meeting_date": max_meeting_date},
            "roughie_rules": {"current_baseline": {"min_price": 10.0, "min_market_rank": 6, "min_score": 45.0}, "simulated": {"min_price": roughie_min_price, "min_market_rank": roughie_min_market_rank, "min_score": roughie_min_score}},
            "current_weights": current_weights,
            "test_weights": proposed_weights,
            "current_model": current_result,
            "simulated_model": simulated_result,
            "improvement": improvement,
            "recommendation": _simulation_recommendation(improvement),
            "notes": notes,
            "safety_note": "Simulation only. No production model weights have been changed.",
        }
        if save_result:
            response["postgres_history"] = save_weight_simulation(response)
        return response
    except Exception as error:
        return {"success": False, "provider": "RRT Predictor", "simulator_version": SIMULATOR_VERSION, "report": "historical_weight_simulation", "error": str(error)}


def save_weight_simulation(simulation: Dict[str, Any]) -> Dict[str, Any]:
    try:
        execute_sql("""
            INSERT INTO rrt_weight_simulations (
                simulation_id, simulation_name, simulator_version, model_version, dataset_runner_count, dataset_race_count,
                current_weights_json, test_weights_json, roughie_rules_json, current_metrics_json, simulated_metrics_json,
                improvement_json, recommendation_json, simulation_json, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s)
            ON CONFLICT (simulation_id) DO UPDATE SET
                simulation_name=EXCLUDED.simulation_name, test_weights_json=EXCLUDED.test_weights_json,
                roughie_rules_json=EXCLUDED.roughie_rules_json, current_metrics_json=EXCLUDED.current_metrics_json,
                simulated_metrics_json=EXCLUDED.simulated_metrics_json, improvement_json=EXCLUDED.improvement_json,
                recommendation_json=EXCLUDED.recommendation_json, simulation_json=EXCLUDED.simulation_json,
                notes=EXCLUDED.notes, created_at=NOW();
        """, (
            simulation.get("simulation_id"), simulation.get("simulation_name"), simulation.get("simulator_version"), MODEL_VERSION,
            (simulation.get("dataset") or {}).get("completed_runner_rows"), (simulation.get("dataset") or {}).get("race_count"),
            _json_dumps(simulation.get("current_weights") or {}), _json_dumps(simulation.get("test_weights") or {}), _json_dumps(simulation.get("roughie_rules") or {}),
            _json_dumps((simulation.get("current_model") or {}).get("metrics") or {}), _json_dumps((simulation.get("simulated_model") or {}).get("metrics") or {}),
            _json_dumps(simulation.get("improvement") or {}), _json_dumps(simulation.get("recommendation") or {}), _json_dumps(simulation), simulation.get("notes") or "",
        ))
        return {"success": True, "provider": "PostgreSQL", "message": "Weight simulation saved.", "simulation_id": simulation.get("simulation_id"), "duplicate_safe": True}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "message": "Failed to save weight simulation.", "error": str(error)}


def get_simulation_history(limit: int=20) -> Dict[str, Any]:
    try:
        rows = fetch_all("""
            SELECT simulation_id, simulation_name, simulator_version, model_version, dataset_runner_count, dataset_race_count,
                   current_metrics_json, simulated_metrics_json, improvement_json, recommendation_json, notes, created_at
            FROM rrt_weight_simulations ORDER BY created_at DESC LIMIT %s;
        """, (limit,))
        return {"success": True, "provider": "PostgreSQL", "simulator_version": SIMULATOR_VERSION, "report": "simulation_history", "limit": limit, "simulation_count": len(rows), "simulations": rows}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "simulator_version": SIMULATOR_VERSION, "report": "simulation_history", "error": str(error)}


def get_best_simulations(limit: int=10) -> Dict[str, Any]:
    try:
        rows = fetch_all("""
            SELECT simulation_id, simulation_name, simulator_version, model_version, dataset_runner_count, dataset_race_count,
                   ROUND((improvement_json->>'overall_accuracy')::NUMERIC, 2) AS overall_improvement,
                   ROUND((improvement_json->>'top_win_strike_rate')::NUMERIC, 2) AS top_win_improvement,
                   ROUND((improvement_json->>'each_way_strike_rate')::NUMERIC, 2) AS each_way_improvement,
                   ROUND((improvement_json->>'roughie_strike_rate')::NUMERIC, 2) AS roughie_improvement,
                   recommendation_json, notes, created_at
            FROM rrt_weight_simulations
            ORDER BY overall_improvement DESC, roughie_improvement DESC LIMIT %s;
        """, (limit,))
        return {"success": True, "provider": "PostgreSQL", "simulator_version": SIMULATOR_VERSION, "report": "best_simulations", "limit": limit, "simulation_count": len(rows), "simulations": rows}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "simulator_version": SIMULATOR_VERSION, "report": "best_simulations", "error": str(error)}



def run_default_simulation_suite(
    min_meeting_date: Optional[str] = None,
    max_meeting_date: Optional[str] = None,
    roughie_min_price: float = 10.0,
    roughie_min_market_rank: int = 6,
    roughie_min_score: float = 45.0,
) -> Dict[str, Any]:
    """Run one-factor-at-a-time simulations and save each result."""
    try:
        results: List[Dict[str, Any]] = []

        for test in DEFAULT_SINGLE_FACTOR_SUITE:
            factor = test.get("factor")
            change = _to_float(test.get("change"))
            old_weight = _to_float(CURRENT_MODEL_WEIGHTS.get(factor))
            new_weight = max(0.0, old_weight + change)

            test_weights = {factor: new_weight}
            label = test.get("label") or f"{factor} {change:+.0f}"

            result = run_weight_simulation(
                test_weights=test_weights,
                simulation_name=str(label),
                notes="v2.15.2 single-factor default suite",
                min_meeting_date=min_meeting_date,
                max_meeting_date=max_meeting_date,
                roughie_min_price=roughie_min_price,
                roughie_min_market_rank=roughie_min_market_rank,
                roughie_min_score=roughie_min_score,
                save_result=True,
                simulation_group="v2.15.2 default single-factor suite",
                factor_tested=factor,
                old_weight=old_weight,
                new_weight=new_weight,
                change_amount=round(new_weight - old_weight, 2),
            )

            results.append(
                {
                    "simulation_id": result.get("simulation_id"),
                    "simulation_name": result.get("simulation_name"),
                    "factor_tested": factor,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "change_amount": round(new_weight - old_weight, 2),
                    "success": result.get("success"),
                    "improvement": result.get("improvement"),
                    "recommendation": result.get("recommendation"),
                    "postgres_history": result.get("postgres_history"),
                }
            )

        improved = [
            item for item in results
            if _to_float((item.get("improvement") or {}).get("overall_accuracy")) > 0
        ]
        rejected = [
            item for item in results
            if (item.get("recommendation") or {}).get("status") == "Reject"
        ]
        neutral = [
            item for item in results
            if item not in improved and item not in rejected
        ]

        ranked = sorted(
            results,
            key=lambda item: _to_float((item.get("improvement") or {}).get("overall_accuracy")),
            reverse=True,
        )

        return {
            "success": True,
            "provider": "RRT Predictor",
            "simulator_version": SIMULATOR_VERSION,
            "report": "default_single_factor_simulation_suite",
            "analysis_only": True,
            "prediction_model_changed": False,
            "simulation_count": len(results),
            "summary": {
                "improved": len(improved),
                "neutral": len(neutral),
                "rejected": len(rejected),
                "best_simulation": ranked[0] if ranked else None,
                "recommended_for_further_testing": ranked[:5],
            },
            "results": ranked,
            "safety_note": "Simulation suite only. No production model weights have been changed.",
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "RRT Predictor",
            "simulator_version": SIMULATOR_VERSION,
            "report": "default_single_factor_simulation_suite",
            "error": str(error),
        }


def get_simulation_report(simulation_id: Optional[str]=None) -> Dict[str, Any]:
    try:
        if simulation_id:
            row = fetch_one("SELECT simulation_json FROM rrt_weight_simulations WHERE simulation_id = %s LIMIT 1;", (simulation_id,))
        else:
            row = fetch_one("SELECT simulation_json FROM rrt_weight_simulations ORDER BY created_at DESC LIMIT 1;")
        if not row:
            return {"success": False, "provider": "PostgreSQL", "simulator_version": SIMULATOR_VERSION, "message": "No simulation report found.", "simulation_id": simulation_id}
        simulation_json = row.get("simulation_json") or {}
        if isinstance(simulation_json, str):
            simulation_json = json.loads(simulation_json)
        return {"success": True, "provider": "PostgreSQL", "simulator_version": SIMULATOR_VERSION, "report": "simulation_report", "simulation": simulation_json}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "simulator_version": SIMULATOR_VERSION, "report": "simulation_report", "error": str(error)}
