from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import uuid

from database import execute_sql, fetch_all, fetch_one
from factor_analysis import get_factor_effectiveness_report
from adaptive_weight_recommendations import get_weight_recommendations
from simulator_engine import get_best_simulations, get_simulation_history
from selection_intelligence import get_latest_selection_analysis

LEARNING_VERSION = "2.18.4"
MODEL_VERSION = "2.18.4"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return default if value is None else int(float(value))
    except Exception:
        return default


def _historical_dataset_profile(factor_report: Dict[str, Any]) -> Dict[str, Any]:
    dataset = factor_report.get("dataset") or factor_report.get("summary") or {}
    db = fetch_one("""
        SELECT COUNT(*) AS runner_rows,
               COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS completed_runner_rows,
               COUNT(DISTINCT meeting_id) AS meeting_count,
               COUNT(DISTINCT (meeting_id::text || '|' || COALESCE(race_number::text,''))) AS race_count,
               MIN(meeting_date) AS first_meeting_date,
               MAX(meeting_date) AS latest_meeting_date
        FROM rrt_runner_factor_snapshots;
    """) or {}
    return {
        "source": "historical_factor_analysis_plus_native_capture",
        "historical_learning_retained": True,
        "native_full_field_capture_active": True,
        "runner_rows": _int(db.get("runner_rows") or dataset.get("runner_count") or dataset.get("runner_rows")),
        "completed_runner_rows": _int(db.get("completed_runner_rows")),
        "meeting_count": _int(db.get("meeting_count") or dataset.get("meeting_count")),
        "race_count": _int(db.get("race_count") or dataset.get("race_count")),
        "first_meeting_date": db.get("first_meeting_date"),
        "latest_meeting_date": db.get("latest_meeting_date"),
    }


def _find_simulation_evidence(factor: str, best: Dict[str, Any], history: Dict[str, Any]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for key in ("simulations", "best_simulations", "history"):
        value = best.get(key) or history.get(key)
        if isinstance(value, list):
            rows.extend(value)
    matches = [row for row in rows if str(row.get("factor_tested") or "") == str(factor)]
    if not matches:
        return {"available": False, "expected_improvement": 0.0, "simulation_count": 0}
    def score(row: Dict[str, Any]) -> float:
        improvement = row.get("improvement") or row.get("improvement_json") or {}
        return _float(improvement.get("overall_accuracy") or improvement.get("top_win_strike_rate"))
    strongest = max(matches, key=score)
    improvement = strongest.get("improvement") or strongest.get("improvement_json") or {}
    return {
        "available": True,
        "simulation_count": len(matches),
        "simulation_id": strongest.get("simulation_id"),
        "expected_improvement": _float(improvement.get("overall_accuracy") or improvement.get("top_win_strike_rate")),
        "top_win_improvement": _float(improvement.get("top_win_strike_rate")),
    }


def _selection_evidence(factor: str, selection: Dict[str, Any]) -> Dict[str, Any]:
    rollup = selection.get("factor_gap_rollup") or []
    match = next((row for row in rollup if str(row.get("factor")) == str(factor)), None) or {}
    return {
        "available": bool(match),
        "average_winner_gap_vs_top4": _float(match.get("average_winner_gap_vs_top4")),
        "direction": match.get("direction"),
        "missed_race_count": _int(match.get("missed_race_count")),
    }


def _confidence_score(rec: Dict[str, Any], dataset: Dict[str, Any], simulation: Dict[str, Any], selection: Dict[str, Any]) -> float:
    races = _int(dataset.get("race_count"))
    completed = _int(dataset.get("completed_runner_rows"))
    sample = min(100.0, (races / 5.0) + (completed / 50.0))
    signal = min(100.0, abs(_float(rec.get("combined_predictive_score") or rec.get("predictive_score"))) * 400.0)
    corroboration = 0.0
    if simulation.get("available"): corroboration += 50.0
    if selection.get("available"): corroboration += 50.0
    direction = 100.0 if abs(_float(rec.get("change") or rec.get("change_amount"))) > 0 else 60.0
    return round((sample * 0.45) + (signal * 0.25) + (corroboration * 0.20) + (direction * 0.10), 1)


def _status(confidence: float, expected_improvement: float, change: float) -> str:
    if change == 0:
        return "Monitor"
    if confidence >= 80 and expected_improvement > 0:
        return "Adopt Candidate"
    if confidence >= 60:
        return "Monitor"
    return "Reject"


def run_adaptive_learning_cycle(cycle_name: str = "v2.18.4 calibrated adaptive learning cycle", save_result: bool = True) -> Dict[str, Any]:
    try:
        factors = get_factor_effectiveness_report()
        weights = get_weight_recommendations()
        if not factors.get("success") or not weights.get("success"):
            return {
                "success": False, "provider": "PostgreSQL",
                "learning_version": LEARNING_VERSION, "model_version": MODEL_VERSION,
                "factor_report": factors, "weight_report": weights,
                "message": "Adaptive learning requires valid historical factor effectiveness and weight recommendations.",
            }

        dataset = _historical_dataset_profile(factors)
        if dataset.get("race_count", 0) <= 0 and dataset.get("completed_runner_rows", 0) <= 0:
            return {
                "success": False, "provider": "PostgreSQL",
                "learning_version": LEARNING_VERSION, "model_version": MODEL_VERSION,
                "analysis_only": True, "production_weights_changed": True,
                "message": "Adaptive learning not run: no completed historical factor evidence is available.",
                "dataset": dataset,
                "next_step": "Continue native full-field capture and automatic results processing. Historical reconstruction is not required.",
            }

        best_simulations = get_best_simulations(limit=100)
        simulation_history = get_simulation_history(limit=500)
        selection = get_latest_selection_analysis()

        recommendations: List[Dict[str, Any]] = []
        for item in weights.get("recommendations") or []:
            factor = item.get("factor")
            simulation = _find_simulation_evidence(factor, best_simulations, simulation_history)
            selection_ev = _selection_evidence(factor, selection)
            improvement = _float(simulation.get("expected_improvement"))
            change = _float(item.get("change") or item.get("change_amount"))
            confidence = _confidence_score(item, dataset, simulation, selection_ev)
            recommendations.append({
                **item,
                "expected_improvement": improvement,
                "expected_top_win_improvement": _float(simulation.get("top_win_improvement")),
                "confidence_pct": confidence,
                "sample_races": dataset.get("race_count"),
                "sample_runners": dataset.get("completed_runner_rows"),
                "simulation_evidence": simulation,
                "selection_evidence": selection_ev,
                "status": _status(confidence, improvement, change),
                "rationale": item.get("reason") or item.get("rationale"),
            })

        cycle_id = f"learn-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        result = {
            "success": True, "provider": "PostgreSQL",
            "learning_version": LEARNING_VERSION, "model_version": MODEL_VERSION,
            "cycle_id": cycle_id, "cycle_name": cycle_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_only": True, "production_weights_changed": True,
            "learning_source": "historical_factor_analysis",
            "historical_learning_retained": True,
            "reconstructed_full_field_history_required": False,
            "native_full_field_capture_active": True,
            "dataset": dataset,
            "factor_report": factors,
            "weight_report": weights,
            "simulation_report": {"best": best_simulations, "history_summary": simulation_history},
            "selection_report": selection,
            "recommendations": recommendations,
            "summary": {
                "recommendation_count": len(recommendations),
                "adopt_candidates": sum(1 for r in recommendations if r.get("status") == "Adopt Candidate"),
                "monitor": sum(1 for r in recommendations if r.get("status") == "Monitor"),
                "reject": sum(1 for r in recommendations if r.get("status") == "Reject"),
            },
            "safety_note": "The v2.18.4 calibrated production weights are active. New recommendations remain evidence-only and are never applied automatically.",
        }
        if save_result:
            execute_sql("""INSERT INTO rrt_learning_cycles
                (cycle_id,cycle_name,learning_version,model_version,dataset_json,factor_report_json,weight_report_json,simulation_report_json,selection_report_json,recommendations_json,cycle_json)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)
                ON CONFLICT (cycle_id) DO UPDATE SET cycle_json=EXCLUDED.cycle_json;""",
                (cycle_id,cycle_name,LEARNING_VERSION,MODEL_VERSION,json.dumps(dataset,default=str),json.dumps(factors,default=str),json.dumps(weights,default=str),json.dumps(result["simulation_report"],default=str),json.dumps(selection,default=str),json.dumps(recommendations,default=str),json.dumps(result,default=str)))
            for rec in recommendations:
                execute_sql("""INSERT INTO rrt_factor_recommendations
                    (cycle_id,factor,current_weight,recommended_weight,change_amount,expected_improvement,confidence_pct,status,rationale,recommendation_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb);""",
                    (cycle_id,rec.get("factor"),rec.get("current_weight"),rec.get("recommended_weight"),rec.get("change") or rec.get("change_amount"),rec.get("expected_improvement"),rec.get("confidence_pct"),rec.get("status"),rec.get("rationale"),json.dumps(rec,default=str)))
        return result
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "learning_version": LEARNING_VERSION, "model_version": MODEL_VERSION, "error": str(error)}


def get_learning_cycle_report(cycle_id: Optional[str] = None) -> Dict[str, Any]:
    row = fetch_one("SELECT cycle_json FROM rrt_learning_cycles WHERE cycle_id=%s;" if cycle_id else "SELECT cycle_json FROM rrt_learning_cycles ORDER BY created_at DESC LIMIT 1;", (cycle_id,) if cycle_id else ())
    return (row or {}).get("cycle_json") or {"success": False, "learning_version": LEARNING_VERSION, "message": "No learning cycle found."}


def get_learning_cycle_history(limit: int = 20) -> Dict[str, Any]:
    rows = fetch_all("""SELECT cycle_id,cycle_name,learning_version,model_version,created_at FROM rrt_learning_cycles ORDER BY created_at DESC LIMIT %s;""", (max(1,min(limit,100)),))
    return {"success": True, "learning_version": LEARNING_VERSION, "cycle_count": len(rows), "cycles": rows}


def get_learning_recommendation_history(limit: int = 100) -> Dict[str, Any]:
    rows = fetch_all("""SELECT cycle_id,factor,current_weight,recommended_weight,change_amount,expected_improvement,confidence_pct,status,rationale,created_at FROM rrt_factor_recommendations ORDER BY created_at DESC LIMIT %s;""", (max(1,min(limit,500)),))
    return {"success": True, "learning_version": LEARNING_VERSION, "recommendation_count": len(rows), "recommendations": rows}


def get_adaptive_learning_summary() -> Dict[str, Any]:
    row = fetch_one("SELECT COUNT(*) AS cycle_count,MAX(created_at) AS latest_cycle_at FROM rrt_learning_cycles;") or {}
    statuses = fetch_all("SELECT status,COUNT(*) AS count FROM rrt_factor_recommendations GROUP BY status ORDER BY status;")
    factors = get_factor_effectiveness_report()
    return {
        "success": True, "learning_version": LEARNING_VERSION, "model_version": MODEL_VERSION,
        "summary": row, "recommendation_statuses": statuses,
        "dataset": _historical_dataset_profile(factors),
        "learning_source": "historical_factor_analysis",
        "historical_learning_retained": True,
        "native_full_field_capture_active": True,
        "reconstructed_full_field_history_required": False,
        "analysis_only": True, "production_weights_changed": True,
    }
