from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import uuid

from database import execute_sql, fetch_all, fetch_one
from learning_dataset import get_learning_dataset_audit
from factor_analysis import get_factor_effectiveness_report
from adaptive_weight_recommendations import get_weight_recommendations
from replay_engine import run_historical_replay

LEARNING_VERSION = "2.18.1"
MODEL_VERSION = "2.18.1"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
    except Exception:
        return default


def _confidence_score(rec: Dict[str, Any], audit: Dict[str, Any]) -> float:
    comparison = audit.get("prediction_comparison") or {}
    races = int(comparison.get("race_count") or 0)
    sample = min(100.0, races / 5.0)
    signal = min(100.0, abs(_float(rec.get("combined_predictive_score"))) * 400.0)
    direction = 100.0 if abs(_float(rec.get("change"))) > 0 else 60.0
    return round((sample * 0.55) + (signal * 0.35) + (direction * 0.10), 1)


def _status(confidence: float, expected_improvement: float, change: float) -> str:
    if change == 0:
        return "Monitor"
    if confidence >= 80 and expected_improvement > 0:
        return "Adopt Candidate"
    if confidence >= 60:
        return "Monitor"
    return "Reject"


def run_adaptive_learning_cycle(cycle_name: str = "v2.18.1 adaptive learning cycle", save_result: bool = True) -> Dict[str, Any]:
    try:
        audit = get_learning_dataset_audit()
        comparison = audit.get("prediction_comparison") or {}
        if int(comparison.get("race_count") or 0) <= 0 or int(comparison.get("runner_count") or 0) <= 0:
            return {
                "success": False,
                "provider": "PostgreSQL",
                "learning_version": LEARNING_VERSION,
                "model_version": MODEL_VERSION,
                "analysis_only": True,
                "production_weights_changed": False,
                "message": "Adaptive learning not run: no valid full-field pre-race learning rows are available.",
                "dataset_audit": audit,
                "next_step": "Run /api/learning-dataset/reconstruct, then collect new v2.18.1 full-field predictions and official results.",
            }
        factors = get_factor_effectiveness_report()
        weights = get_weight_recommendations()
        if not factors.get("success") or not weights.get("success"):
            return {"success": False, "learning_version": LEARNING_VERSION, "audit": audit, "factor_report": factors, "weight_report": weights}

        recommendations: List[Dict[str, Any]] = []
        for item in weights.get("recommendations") or []:
            factor = item.get("factor")
            replay = run_historical_replay(
                replay_name=f"{cycle_name} - {factor}",
                test_weights={factor: item.get("recommended_weight")},
                save_result=False,
            )
            improvement = _float((replay.get("improvement") or {}).get("top1_win_strike_rate"))
            confidence = _confidence_score(item, audit)
            change = _float(item.get("change"))
            recommendations.append({
                **item,
                "expected_top1_improvement": improvement,
                "confidence_pct": confidence,
                "sample_races": ((audit.get("prediction_comparison") or {}).get("race_count") or 0),
                "sample_runners": ((audit.get("prediction_comparison") or {}).get("runner_count") or 0),
                "status": _status(confidence, improvement, change),
                "rationale": item.get("reason"),
            })

        cycle_id = f"learn-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        result = {
            "success": True,
            "provider": "PostgreSQL",
            "learning_version": LEARNING_VERSION,
            "model_version": MODEL_VERSION,
            "cycle_id": cycle_id,
            "cycle_name": cycle_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_only": True,
            "production_weights_changed": False,
            "dataset_audit": audit,
            "recommendations": recommendations,
            "summary": {
                "recommendation_count": len(recommendations),
                "adopt_candidates": sum(1 for r in recommendations if r.get("status") == "Adopt Candidate"),
                "monitor": sum(1 for r in recommendations if r.get("status") == "Monitor"),
                "reject": sum(1 for r in recommendations if r.get("status") == "Reject"),
            },
            "safety_note": "Recommendations are evidence-only. Production weights are never changed automatically.",
        }
        if save_result:
            execute_sql("""INSERT INTO rrt_learning_cycles
                (cycle_id,cycle_name,learning_version,model_version,dataset_json,recommendations_json,cycle_json)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb);""",
                (cycle_id,cycle_name,LEARNING_VERSION,MODEL_VERSION,json.dumps(audit,default=str),json.dumps(recommendations,default=str),json.dumps(result,default=str)))
            for rec in recommendations:
                execute_sql("""INSERT INTO rrt_factor_recommendations
                    (cycle_id,factor,current_weight,recommended_weight,change_amount,expected_improvement,confidence_pct,status,rationale,recommendation_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb);""",
                    (cycle_id,rec.get("factor"),rec.get("current_weight"),rec.get("recommended_weight"),rec.get("change"),
                     rec.get("expected_top1_improvement"),rec.get("confidence_pct"),rec.get("status"),rec.get("rationale"),json.dumps(rec,default=str)))
        return result
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "learning_version": LEARNING_VERSION, "error": str(error)}


def get_learning_cycle_report(cycle_id: Optional[str] = None) -> Dict[str, Any]:
    row = fetch_one("SELECT cycle_json FROM rrt_learning_cycles WHERE cycle_id=%s;" if cycle_id else "SELECT cycle_json FROM rrt_learning_cycles ORDER BY created_at DESC LIMIT 1;", (cycle_id,) if cycle_id else ())
    return (row or {}).get("cycle_json") or {"success": False, "learning_version": LEARNING_VERSION, "message": "No learning cycle found."}


def get_learning_cycle_history(limit: int = 20) -> Dict[str, Any]:
    rows = fetch_all("""SELECT cycle_id,cycle_name,learning_version,model_version,created_at
        FROM rrt_learning_cycles ORDER BY created_at DESC LIMIT %s;""", (max(1,min(limit,100)),))
    return {"success": True, "learning_version": LEARNING_VERSION, "cycle_count": len(rows), "cycles": rows}


def get_learning_recommendation_history(limit: int = 100) -> Dict[str, Any]:
    rows = fetch_all("""SELECT cycle_id,factor,current_weight,recommended_weight,change_amount,
        expected_improvement,confidence_pct,status,rationale,created_at
        FROM rrt_factor_recommendations ORDER BY created_at DESC LIMIT %s;""", (max(1,min(limit,500)),))
    return {"success": True, "learning_version": LEARNING_VERSION, "recommendation_count": len(rows), "recommendations": rows}


def get_adaptive_learning_summary() -> Dict[str, Any]:
    row = fetch_one("""SELECT COUNT(*) AS cycle_count,MAX(created_at) AS latest_cycle_at FROM rrt_learning_cycles;""") or {}
    statuses = fetch_all("""SELECT status,COUNT(*) AS count FROM rrt_factor_recommendations GROUP BY status ORDER BY status;""")
    return {"success": True, "learning_version": LEARNING_VERSION, "model_version": MODEL_VERSION,
            "summary": row, "recommendation_statuses": statuses, "dataset_audit": get_learning_dataset_audit(),
            "analysis_only": True, "production_weights_changed": False}
