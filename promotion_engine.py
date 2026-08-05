from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json
import os
import uuid

from database import execute_sql, fetch_all, fetch_one
from adaptive_weight_recommendations import get_weight_recommendations
from factor_analysis import get_factor_effectiveness_report
from replay_engine import run_historical_replay
from selection_intelligence import run_selection_intelligence_analysis
from simulator_engine import run_weight_simulation

PROMOTION_VERSION = "2.21.0"
MODEL_VERSION = "2.21.0"

PROMOTION_MODE = os.getenv("RRT_PROMOTION_MODE", "shadow").strip().lower()
if PROMOTION_MODE not in {"off", "shadow", "live"}:
    PROMOTION_MODE = "shadow"

MIN_NATIVE_RACES = int(os.getenv("RRT_PROMOTION_MIN_NATIVE_RACES", "1000"))
MIN_COMPLETED_RUNNERS = int(os.getenv("RRT_PROMOTION_MIN_COMPLETED_RUNNERS", "8000"))
MIN_OVERALL_IMPROVEMENT = float(os.getenv("RRT_PROMOTION_MIN_OVERALL_IMPROVEMENT", "0.25"))
MIN_TOP1_IMPROVEMENT = float(os.getenv("RRT_PROMOTION_MIN_TOP1_IMPROVEMENT", "0.00"))
MIN_TOP4_IMPROVEMENT = float(os.getenv("RRT_PROMOTION_MIN_TOP4_IMPROVEMENT", "0.00"))
MAX_EACH_WAY_DEGRADATION = float(os.getenv("RRT_PROMOTION_MAX_EACH_WAY_DEGRADATION", "0.25"))
MAX_ROUGHIE_DEGRADATION = float(os.getenv("RRT_PROMOTION_MAX_ROUGHIE_DEGRADATION", "0.25"))
MIN_STABILITY_INDEX = float(os.getenv("RRT_PROMOTION_MIN_STABILITY_INDEX", "90.0"))
REQUIRED_SHADOW_PASSES = int(os.getenv("RRT_PROMOTION_REQUIRED_SHADOW_PASSES", "2"))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None or value == "" else float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return default if value is None or value == "" else int(float(value))
    except Exception:
        return default


def _normalise(weights: Dict[str, Any]) -> Dict[str, float]:
    cleaned = {str(key): max(0.0, _float(value)) for key, value in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("Candidate weights must have a positive total.")
    scaled = {key: round(value * 100.0 / total, 2) for key, value in cleaned.items()}
    delta = round(100.0 - sum(scaled.values()), 2)
    if scaled:
        largest = max(scaled, key=scaled.get)
        scaled[largest] = round(scaled[largest] + delta, 2)
    return scaled


def _active_weight_row() -> Dict[str, Any]:
    return fetch_one(
        """
        SELECT model_version, status, weights_json, source, notes, activated_at,
               automatic_promotion, promoted_by_cycle_id
        FROM rrt_model_weight_sets
        WHERE status = 'Active'
        ORDER BY activated_at DESC NULLS LAST, created_at DESC
        LIMIT 1;
        """
    ) or {}


def _dataset_summary() -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT COUNT(*) AS runner_rows,
               COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS completed_runner_rows,
               COUNT(DISTINCT meeting_id) FILTER (WHERE actual_position IS NOT NULL) AS completed_meetings,
               COUNT(DISTINCT (meeting_id::text || '|' || COALESCE(race_number::text, '')))
                   FILTER (WHERE actual_position IS NOT NULL) AS native_completed_races,
               MIN(meeting_date) FILTER (WHERE actual_position IS NOT NULL) AS first_meeting_date,
               MAX(meeting_date) FILTER (WHERE actual_position IS NOT NULL) AS latest_meeting_date
        FROM rrt_runner_factor_snapshots;
        """
    ) or {}
    return {
        "runner_rows": _int(row.get("runner_rows")),
        "completed_runner_rows": _int(row.get("completed_runner_rows")),
        "completed_meetings": _int(row.get("completed_meetings")),
        "native_completed_races": _int(row.get("native_completed_races")),
        "first_meeting_date": row.get("first_meeting_date"),
        "latest_meeting_date": row.get("latest_meeting_date"),
    }


def _candidate_weights(weight_report: Dict[str, Any], active_weights: Dict[str, Any]) -> Dict[str, float]:
    candidate = dict(active_weights)
    for recommendation in weight_report.get("recommendations") or []:
        factor = str(recommendation.get("factor") or "").strip()
        if factor and recommendation.get("recommended_weight") is not None:
            candidate[factor] = _float(recommendation.get("recommended_weight"), _float(candidate.get(factor)))
    candidate.setdefault("speed", _float(active_weights.get("speed"), 0.0))
    return _normalise(candidate)


def _recent_shadow_passes() -> int:
    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT decision
            FROM rrt_weight_promotion_audit
            WHERE decision IN ('Approved-Shadow', 'Promoted')
            ORDER BY created_at DESC
            LIMIT %s
        ) recent;
        """,
        (max(0, REQUIRED_SHADOW_PASSES - 1),),
    ) or {}
    return _int(row.get("count"))


def _gate(dataset: Dict[str, Any], simulation: Dict[str, Any], replay: Dict[str, Any]) -> Dict[str, Any]:
    simulation_improvement = simulation.get("improvement") or {}
    replay_improvement = replay.get("improvement") or {}
    sensitivity = simulation.get("sensitivity") or {}

    checks = {
        "minimum_native_races": dataset.get("native_completed_races", 0) >= MIN_NATIVE_RACES,
        "minimum_completed_runners": dataset.get("completed_runner_rows", 0) >= MIN_COMPLETED_RUNNERS,
        "simulator_overall_improvement": _float(simulation_improvement.get("overall_accuracy")) >= MIN_OVERALL_IMPROVEMENT,
        "simulator_top1_not_degraded": _float(simulation_improvement.get("top1_win_strike_rate")) >= MIN_TOP1_IMPROVEMENT,
        "simulator_top4_not_degraded": _float(simulation_improvement.get("top4_winner_coverage_rate")) >= MIN_TOP4_IMPROVEMENT,
        "simulator_each_way_within_tolerance": _float(simulation_improvement.get("each_way_strike_rate")) >= -MAX_EACH_WAY_DEGRADATION,
        "simulator_roughie_within_tolerance": _float(simulation_improvement.get("roughie_strike_rate")) >= -MAX_ROUGHIE_DEGRADATION,
        "prediction_stability": _float(sensitivity.get("prediction_stability_index"), 100.0) >= MIN_STABILITY_INDEX,
        "replay_top1_not_degraded": _float(replay_improvement.get("top1_win_strike_rate")) >= MIN_TOP1_IMPROVEMENT,
        "replay_top4_not_degraded": _float(replay_improvement.get("top4_win_strike_rate")) >= MIN_TOP4_IMPROVEMENT,
        "replay_roughie_within_tolerance": _float(replay_improvement.get("roughie_win_strike_rate")) >= -MAX_ROUGHIE_DEGRADATION,
    }
    passed = all(checks.values())
    consecutive_passes = _recent_shadow_passes() + 1 if passed else 0
    live_authorised = (
        passed
        and consecutive_passes >= REQUIRED_SHADOW_PASSES
        and PROMOTION_MODE == "live"
    )
    decision = "Approved-Shadow" if passed else "Rejected"
    if live_authorised:
        decision = "Promoted"
    elif PROMOTION_MODE == "off":
        decision = "Controller-Off"

    return {
        "decision": decision,
        "passed": passed,
        "promotion_mode": PROMOTION_MODE,
        "live_promotion_authorised": live_authorised,
        "consecutive_shadow_passes": consecutive_passes,
        "required_shadow_passes": REQUIRED_SHADOW_PASSES,
        "checks": checks,
        "thresholds": {
            "minimum_native_races": MIN_NATIVE_RACES,
            "minimum_completed_runners": MIN_COMPLETED_RUNNERS,
            "minimum_overall_improvement": MIN_OVERALL_IMPROVEMENT,
            "minimum_top1_improvement": MIN_TOP1_IMPROVEMENT,
            "minimum_top4_improvement": MIN_TOP4_IMPROVEMENT,
            "maximum_each_way_degradation": MAX_EACH_WAY_DEGRADATION,
            "maximum_roughie_degradation": MAX_ROUGHIE_DEGRADATION,
            "minimum_stability_index": MIN_STABILITY_INDEX,
        },
    }


def _save_candidate(
    candidate_id: str,
    cycle_id: Optional[str],
    active: Dict[str, Any],
    candidate_weights: Dict[str, float],
    simulation: Dict[str, Any],
    replay: Dict[str, Any],
    gate: Dict[str, Any],
) -> None:
    status = "Approved" if gate.get("passed") else "Rejected"
    if PROMOTION_MODE == "shadow" and gate.get("passed"):
        status = "Shadow-Approved"
    if gate.get("live_promotion_authorised"):
        status = "Active"
    execute_sql(
        """
        INSERT INTO rrt_model_candidates(
            candidate_id, cycle_id, base_weight_set, status, weights_json,
            simulator_id, replay_id, gate_json, decision_reason, evaluated_at
        ) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s,NOW())
        ON CONFLICT(candidate_id) DO UPDATE SET
            status=EXCLUDED.status,
            weights_json=EXCLUDED.weights_json,
            simulator_id=EXCLUDED.simulator_id,
            replay_id=EXCLUDED.replay_id,
            gate_json=EXCLUDED.gate_json,
            decision_reason=EXCLUDED.decision_reason,
            evaluated_at=NOW();
        """,
        (
            candidate_id,
            cycle_id,
            active.get("model_version"),
            status,
            json.dumps(candidate_weights),
            simulation.get("simulation_id"),
            replay.get("replay_id"),
            json.dumps(gate, default=str),
            "All gates passed." if gate.get("passed") else "One or more safety gates failed.",
        ),
    )


def _promote(
    candidate_id: str,
    cycle_id: Optional[str],
    active: Dict[str, Any],
    candidate_weights: Dict[str, float],
    gate: Dict[str, Any],
) -> Dict[str, Any]:
    new_weight_set = f"2.21.0-auto-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    execute_sql("UPDATE rrt_model_weight_sets SET status='Archive' WHERE status='Rollback';")
    execute_sql("UPDATE rrt_model_weight_sets SET status='Rollback' WHERE status='Active';")
    execute_sql(
        """
        INSERT INTO rrt_model_weight_sets(
            model_version, status, weights_json, source, notes, activated_at,
            promoted_by_cycle_id, promotion_evidence_json, automatic_promotion
        ) VALUES(%s,'Active',%s::jsonb,'v2.21.0 Promotion Controller',%s,NOW(),%s,%s::jsonb,TRUE);
        """,
        (
            new_weight_set,
            json.dumps(candidate_weights),
            "Automatically promoted after Simulator, Replay, stability and non-degradation gates passed.",
            cycle_id,
            json.dumps(gate, default=str),
        ),
    )
    execute_sql(
        "UPDATE rrt_model_candidates SET status='Active', promoted_at=NOW() WHERE candidate_id=%s;",
        (candidate_id,),
    )
    return {
        "applied": True,
        "from_weight_set": active.get("model_version"),
        "to_weight_set": new_weight_set,
        "rollback_available": True,
    }


def run_promotion_cycle(
    cycle_id: Optional[str] = None,
    candidate_name: str = "v2.21.0 autonomous promotion candidate",
    save_result: bool = True,
) -> Dict[str, Any]:
    try:
        active = _active_weight_row()
        active_weights = active.get("weights_json") or {}
        if not active_weights:
            return {"success": False, "promotion_version": PROMOTION_VERSION, "message": "No active production weight set found."}

        factor_report = get_factor_effectiveness_report()
        weight_report = get_weight_recommendations()
        selection_report = run_selection_intelligence_analysis(save_result=True)
        candidate_weights = _candidate_weights(weight_report, active_weights)
        dataset = _dataset_summary()
        candidate_id = f"candidate-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        simulation = run_weight_simulation(
            test_weights=candidate_weights,
            simulation_name=candidate_name,
            notes="v2.21.0 exact adaptive candidate evaluated by the promotion controller.",
            save_result=True,
            simulation_group="v2.21.0 promotion-controller",
        )
        replay = run_historical_replay(
            replay_name=candidate_name,
            test_weights=candidate_weights,
            model_version=None,
            save_result=True,
            include_selections=False,
        )
        gate = _gate(dataset, simulation, replay)

        _save_candidate(candidate_id, cycle_id, active, candidate_weights, simulation, replay, gate)

        promotion = {"applied": False, "reason": "Shadow evaluation only."}
        if gate.get("live_promotion_authorised"):
            promotion = _promote(candidate_id, cycle_id, active, candidate_weights, gate)

        audit_id = f"promotion-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        execute_sql(
            """
            INSERT INTO rrt_weight_promotion_audit(
                promotion_id, cycle_id, from_weight_set, to_weight_set, decision,
                gate_json, previous_weights_json, proposed_weights_json, applied,
                rollback_available, candidate_id, simulator_id, replay_id
            ) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,TRUE,%s,%s,%s);
            """,
            (
                audit_id,
                cycle_id,
                active.get("model_version"),
                promotion.get("to_weight_set") or candidate_id,
                gate.get("decision"),
                json.dumps(gate, default=str),
                json.dumps(active_weights),
                json.dumps(candidate_weights),
                bool(promotion.get("applied")),
                candidate_id,
                simulation.get("simulation_id"),
                replay.get("replay_id"),
            ),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "promotion_version": PROMOTION_VERSION,
            "model_version": MODEL_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "promotion_mode": PROMOTION_MODE,
            "automatic_weight_changes_enabled": PROMOTION_MODE == "live",
            "shadow_mode_active": PROMOTION_MODE == "shadow",
            "candidate_id": candidate_id,
            "cycle_id": cycle_id,
            "active_weight_set_before_cycle": active,
            "candidate_weights": candidate_weights,
            "dataset": dataset,
            "factor_report": factor_report,
            "weight_report": weight_report,
            "selection_report": selection_report,
            "simulation_report": simulation,
            "replay_report": replay,
            "promotion_gate": gate,
            "promotion": promotion,
            "audit_id": audit_id,
            "production_weights_changed": bool(promotion.get("applied")),
            "safety_note": "Shadow mode evaluates and records candidates but cannot alter production weights. Live promotion requires RRT_PROMOTION_MODE=live and every gate to pass.",
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "promotion_version": PROMOTION_VERSION,
            "model_version": MODEL_VERSION,
            "error": str(error),
        }


def get_promotion_status() -> Dict[str, Any]:
    active = _active_weight_row()
    latest_candidate = fetch_one(
        """
        SELECT candidate_id, cycle_id, base_weight_set, status, weights_json,
               simulator_id, replay_id, gate_json, decision_reason,
               created_at, evaluated_at, promoted_at
        FROM rrt_model_candidates
        ORDER BY created_at DESC
        LIMIT 1;
        """
    ) or {}
    audit = fetch_one(
        """
        SELECT COUNT(*) AS audit_count,
               COUNT(*) FILTER (WHERE applied IS TRUE) AS promotion_count,
               MAX(created_at) AS latest_decision_at
        FROM rrt_weight_promotion_audit;
        """
    ) or {}
    return {
        "success": True,
        "promotion_version": PROMOTION_VERSION,
        "model_version": MODEL_VERSION,
        "promotion_mode": PROMOTION_MODE,
        "automatic_weight_changes_enabled": PROMOTION_MODE == "live",
        "shadow_mode_active": PROMOTION_MODE == "shadow",
        "active_weight_set": active,
        "latest_candidate": latest_candidate,
        "audit_summary": audit,
        "thresholds": {
            "minimum_native_races": MIN_NATIVE_RACES,
            "minimum_completed_runners": MIN_COMPLETED_RUNNERS,
            "minimum_overall_improvement": MIN_OVERALL_IMPROVEMENT,
            "minimum_top1_improvement": MIN_TOP1_IMPROVEMENT,
            "minimum_top4_improvement": MIN_TOP4_IMPROVEMENT,
            "maximum_each_way_degradation": MAX_EACH_WAY_DEGRADATION,
            "maximum_roughie_degradation": MAX_ROUGHIE_DEGRADATION,
            "minimum_stability_index": MIN_STABILITY_INDEX,
            "required_shadow_passes": REQUIRED_SHADOW_PASSES,
        },
    }


def get_candidate_history(limit: int = 20) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT candidate_id, cycle_id, base_weight_set, status, weights_json,
               simulator_id, replay_id, gate_json, decision_reason,
               created_at, evaluated_at, promoted_at
        FROM rrt_model_candidates
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (max(1, min(limit, 100)),),
    )
    return {
        "success": True,
        "promotion_version": PROMOTION_VERSION,
        "candidate_count": len(rows),
        "candidates": rows,
    }
