from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import json
import uuid

from database import execute_sql, fetch_all, fetch_one

REPLAY_VERSION = "2.17.0"
MODEL_VERSION = "2.8.1"

DEFAULT_WEIGHTS: Dict[str, float] = {
    "last10": 0.15,
    "win_place": 0.08,
    "track_record": 0.08,
    "distance_record": 0.09,
    "track_distance": 0.09,
    "track_condition": 0.12,
    "trainer": 0.10,
    "jockey": 0.08,
    "trainer_jockey": 0.12,
    "barrier": 0.04,
    "weight": 0.02,
    "market": 0.03,
}

FACTOR_COLUMNS = {
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


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None or value == "" else float(value)
    except Exception:
        return default


def _normalise_weights(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    for key, value in (overrides or {}).items():
        if key in weights and value is not None:
            parsed = _float(value, weights[key])
            if parsed < 0:
                raise ValueError(f"Replay weight '{key}' cannot be negative.")
            weights[key] = parsed
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Replay weights must have a positive total.")
    return {key: round(value / total, 8) for key, value in weights.items()}


def _score(row: Dict[str, Any], weights: Dict[str, float]) -> float:
    return round(sum(_float(row.get(column), 50.0) * weights[key] for key, column in FACTOR_COLUMNS.items()), 4)


def _dataset(min_meeting_date: Optional[str], max_meeting_date: Optional[str], model_version: Optional[str]) -> List[Dict[str, Any]]:
    clauses = ["actual_position IS NOT NULL", "race_number IS NOT NULL"]
    params: List[Any] = []
    if min_meeting_date:
        clauses.append("meeting_date >= %s")
        params.append(min_meeting_date)
    if max_meeting_date:
        clauses.append("meeting_date <= %s")
        params.append(max_meeting_date)
    if model_version:
        clauses.append("model_version = %s")
        params.append(model_version)
    return fetch_all(
        f"""
        SELECT meeting_id, model_version, track, meeting_date, race_id, race_number,
               runner_key, runner_name, tab_number, final_score, confidence,
               market_price, market_rank, actual_position, actual_price,
               last10_score, win_place_score, track_record_score,
               distance_record_score, track_distance_record_score,
               track_condition_score, trainer_score, jockey_score,
               trainer_jockey_score, barrier_score, weight_score, market_score
        FROM rrt_runner_factor_snapshots
        WHERE {' AND '.join(clauses)}
        ORDER BY meeting_date, meeting_id, race_number, runner_key;
        """,
        tuple(params),
    )


def _race_key(row: Dict[str, Any]) -> Tuple[Any, Any]:
    return row.get("meeting_id"), row.get("race_id") or row.get("race_number")


def _metrics(groups: Dict[Tuple[Any, Any], List[Dict[str, Any]]], score_key: str, roughie_min_price: float, roughie_min_rank: int) -> Dict[str, Any]:
    races = 0
    top1_hits = top4_win_hits = top4_place_hits = roughie_hits = 0
    roughie_races = 0
    selections: List[Dict[str, Any]] = []
    for key, runners in groups.items():
        ranked = sorted(runners, key=lambda r: (_float(r.get(score_key)), -_float(r.get("market_price"))), reverse=True)
        if not ranked:
            continue
        races += 1
        top4 = ranked[:4]
        winner = next((r for r in runners if int(_float(r.get("actual_position"), 999)) == 1), None)
        top1_hit = int(_float(ranked[0].get("actual_position"), 999)) == 1
        win_hit = winner is not None and winner.get("runner_key") in {r.get("runner_key") for r in top4}
        place_hit = any(1 <= int(_float(r.get("actual_position"), 999)) <= 3 for r in top4)
        top1_hits += int(top1_hit); top4_win_hits += int(win_hit); top4_place_hits += int(place_hit)
        roughies = [r for r in ranked if _float(r.get("market_price")) >= roughie_min_price and int(_float(r.get("market_rank"), 0)) >= roughie_min_rank]
        roughie_hit = False
        if roughies:
            roughie_races += 1
            roughie_hit = any(int(_float(r.get("actual_position"), 999)) == 1 for r in roughies[:4])
            roughie_hits += int(roughie_hit)
        selections.append({
            "meeting_id": key[0], "race_number": ranked[0].get("race_number"), "track": ranked[0].get("track"),
            "meeting_date": ranked[0].get("meeting_date"), "top_selection": ranked[0].get("runner_name"),
            "top_selection_score": round(_float(ranked[0].get(score_key)), 2), "top_selection_position": ranked[0].get("actual_position"),
            "winner": winner.get("runner_name") if winner else None, "top1_hit": top1_hit, "top4_win_hit": win_hit,
            "top4_place_hit": place_hit, "roughie_hit": roughie_hit,
        })
    pct = lambda hits, total: round((hits / total * 100.0), 2) if total else 0.0
    return {
        "race_count": races, "top1_win_hits": top1_hits, "top1_win_strike_rate": pct(top1_hits, races),
        "top4_win_hits": top4_win_hits, "top4_win_strike_rate": pct(top4_win_hits, races),
        "top4_place_hits": top4_place_hits, "top4_place_strike_rate": pct(top4_place_hits, races),
        "roughie_eligible_races": roughie_races, "roughie_win_hits": roughie_hits,
        "roughie_win_strike_rate": pct(roughie_hits, roughie_races), "selections": selections,
    }


def run_historical_replay(
    replay_name: str = "v2.17.0 historical replay",
    test_weights: Optional[Dict[str, Any]] = None,
    min_meeting_date: Optional[str] = None,
    max_meeting_date: Optional[str] = None,
    model_version: Optional[str] = MODEL_VERSION,
    roughie_min_price: float = 7.0,
    roughie_min_market_rank: int = 5,
    save_result: bool = True,
    include_selections: bool = False,
) -> Dict[str, Any]:
    try:
        weights = _normalise_weights(test_weights)
        rows = _dataset(min_meeting_date, max_meeting_date, model_version)
        groups: Dict[Tuple[Any, Any], List[Dict[str, Any]]] = {}
        for row in rows:
            row["replay_score"] = _score(row, weights)
            groups.setdefault(_race_key(row), []).append(row)
        current = _metrics(groups, "final_score", roughie_min_price, roughie_min_market_rank)
        replay = _metrics(groups, "replay_score", roughie_min_price, roughie_min_market_rank)
        improvement = {
            key: round(_float(replay.get(key)) - _float(current.get(key)), 2)
            for key in ["top1_win_strike_rate", "top4_win_strike_rate", "top4_place_strike_rate", "roughie_win_strike_rate"]
        }
        replay_id = f"replay-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        result = {
            "success": True, "provider": "PostgreSQL", "replay_version": REPLAY_VERSION,
            "replay_id": replay_id, "replay_name": replay_name, "analysis_only": True,
            "production_weights_changed": False, "model_version": model_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": {"runner_count": len(rows), "race_count": len(groups), "meeting_count": len({r.get('meeting_id') for r in rows}),
                        "min_meeting_date": min_meeting_date, "max_meeting_date": max_meeting_date},
            "current_weights": DEFAULT_WEIGHTS, "replay_weights": weights,
            "roughie_rules": {"min_price": roughie_min_price, "min_market_rank": roughie_min_market_rank},
            "current_metrics": {k: v for k, v in current.items() if k != "selections"},
            "replay_metrics": {k: v for k, v in replay.items() if k != "selections"},
            "improvement": improvement,
            "recommendation": "Review replay evidence only; do not alter production weights automatically.",
        }
        if include_selections:
            result["current_selections"] = current["selections"]
            result["replay_selections"] = replay["selections"]
        if save_result:
            execute_sql(
                """INSERT INTO rrt_replay_runs
                (replay_id, replay_name, replay_version, model_version, min_meeting_date, max_meeting_date,
                 dataset_runner_count, dataset_race_count, dataset_meeting_count, current_weights_json,
                 replay_weights_json, current_metrics_json, replay_metrics_json, improvement_json, replay_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb);""",
                (replay_id, replay_name, REPLAY_VERSION, model_version, min_meeting_date, max_meeting_date,
                 len(rows), len(groups), len({r.get('meeting_id') for r in rows}), json.dumps(DEFAULT_WEIGHTS),
                 json.dumps(weights), json.dumps(result["current_metrics"]), json.dumps(result["replay_metrics"]),
                 json.dumps(improvement), json.dumps(result, default=str)),
            )
        return result
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "replay_version": REPLAY_VERSION, "error": str(error)}


def get_replay_report(replay_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        row = fetch_one(
            "SELECT replay_json FROM rrt_replay_runs WHERE replay_id = %s;" if replay_id else
            "SELECT replay_json FROM rrt_replay_runs ORDER BY created_at DESC LIMIT 1;",
            (replay_id,) if replay_id else (),
        )
        if not row:
            return {"success": False, "replay_version": REPLAY_VERSION, "message": "No replay run found."}
        return row.get("replay_json") or {}
    except Exception as error:
        return {"success": False, "replay_version": REPLAY_VERSION, "error": str(error)}


def get_replay_history(limit: int = 20) -> Dict[str, Any]:
    try:
        rows = fetch_all(
            """SELECT replay_id, replay_name, replay_version, model_version, min_meeting_date, max_meeting_date,
                      dataset_runner_count, dataset_race_count, dataset_meeting_count, improvement_json, created_at
               FROM rrt_replay_runs ORDER BY created_at DESC LIMIT %s;""", (max(1, min(limit, 100)),)
        )
        return {"success": True, "provider": "PostgreSQL", "replay_version": REPLAY_VERSION, "run_count": len(rows), "runs": rows}
    except Exception as error:
        return {"success": False, "replay_version": REPLAY_VERSION, "error": str(error)}


def get_replay_summary() -> Dict[str, Any]:
    try:
        summary = fetch_one("""SELECT COUNT(*) AS replay_count, MAX(created_at) AS latest_replay_at,
            ROUND(AVG((improvement_json->>'top1_win_strike_rate')::numeric),2) AS avg_top1_improvement,
            ROUND(AVG((improvement_json->>'top4_win_strike_rate')::numeric),2) AS avg_top4_win_improvement,
            ROUND(AVG((improvement_json->>'top4_place_strike_rate')::numeric),2) AS avg_top4_place_improvement
            FROM rrt_replay_runs;""") or {}
        return {"success": True, "provider": "PostgreSQL", "replay_version": REPLAY_VERSION, "summary": summary,
                "analysis_only": True, "production_weights_changed": False}
    except Exception as error:
        return {"success": False, "replay_version": REPLAY_VERSION, "error": str(error)}
