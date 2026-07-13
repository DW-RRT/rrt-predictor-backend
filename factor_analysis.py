from typing import Any, Dict, List

from database import fetch_all, fetch_one

ANALYSIS_VERSION = "2.18.0"
MODEL_VERSION = "2.18.0"

FACTOR_COLUMNS = [
    {"key": "last10", "label": "Last 10 Form", "score_column": "last10_score", "weighted_column": "weighted_last10"},
    {"key": "win_place", "label": "Win / Place Record", "score_column": "win_place_score", "weighted_column": "weighted_win_place"},
    {"key": "track_record", "label": "Track Record", "score_column": "track_record_score", "weighted_column": "weighted_track_record"},
    {"key": "distance_record", "label": "Distance Record", "score_column": "distance_record_score", "weighted_column": "weighted_distance_record"},
    {"key": "track_distance", "label": "Track / Distance Record", "score_column": "track_distance_record_score", "weighted_column": "weighted_track_distance_record"},
    {"key": "track_condition", "label": "Track Condition", "score_column": "track_condition_score", "weighted_column": "weighted_track_condition"},
    {"key": "trainer", "label": "Trainer", "score_column": "trainer_score", "weighted_column": "weighted_trainer"},
    {"key": "jockey", "label": "Jockey", "score_column": "jockey_score", "weighted_column": "weighted_jockey"},
    {"key": "trainer_jockey", "label": "Trainer / Jockey Combo", "score_column": "trainer_jockey_score", "weighted_column": "weighted_trainer_jockey"},
    {"key": "barrier", "label": "Barrier", "score_column": "barrier_score", "weighted_column": "weighted_barrier"},
    {"key": "weight", "label": "Weight Carried", "score_column": "weight_score", "weighted_column": "weighted_weight"},
    {"key": "market", "label": "Market", "score_column": "market_score", "weighted_column": "weighted_market"},
]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _confidence_from_sample(sample_size: int, winners: int, placed: int) -> str:
    if sample_size >= 1000 and winners >= 80 and placed >= 250:
        return "High"
    if sample_size >= 400 and winners >= 30 and placed >= 100:
        return "Medium"
    if sample_size >= 150 and winners >= 10 and placed >= 40:
        return "Early"
    return "Low"


def _signal_strength(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 0.20:
        return "Strong"
    if abs_value >= 0.12:
        return "Moderate"
    if abs_value >= 0.06:
        return "Weak"
    return "Very Weak"


def _recommendation_from_signal(factor_label: str, winner_gap: float, place_gap: float, win_corr: float, place_corr: float, sample_confidence: str) -> Dict[str, Any]:
    combined_signal = (win_corr * 0.6) + (place_corr * 0.4)
    combined_gap = (winner_gap * 0.6) + (place_gap * 0.4)
    if sample_confidence == "Low":
        return {"direction": "Collect More Data", "priority": "Low", "reason": f"{factor_label} has insufficient completed runner data for a reliable recommendation."}
    if combined_signal >= 0.12 and combined_gap > 3:
        return {"direction": "Review for Increase", "priority": "High" if sample_confidence == "High" else "Medium", "reason": f"{factor_label} is scoring materially higher for successful runners and has a positive outcome relationship."}
    if combined_signal <= -0.08 and combined_gap < -2:
        return {"direction": "Review for Reduction", "priority": "High" if sample_confidence == "High" else "Medium", "reason": f"{factor_label} is not separating successful runners and may be over-emphasised."}
    if abs(combined_signal) < 0.06:
        return {"direction": "Hold / Recalibrate Later", "priority": "Medium", "reason": f"{factor_label} currently shows limited separation between successful and unsuccessful runners."}
    return {"direction": "Monitor", "priority": "Medium", "reason": f"{factor_label} shows some relationship to outcomes, but the signal is not strong enough for a weight recommendation."}


def _factor_sql(score_column: str, weighted_column: str) -> str:
    return f"""
        WITH completed AS (
            SELECT
                {score_column}::NUMERIC AS score_value,
                {weighted_column}::NUMERIC AS weighted_value,
                CASE WHEN actual_position = 1 THEN 1 ELSE 0 END::NUMERIC AS win_flag,
                CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END::NUMERIC AS place_flag
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL
              AND capture_scope = 'full_field'
              AND {score_column} IS NOT NULL
        )
        SELECT
            COUNT(*) AS runner_count,
            SUM(win_flag)::INTEGER AS winner_count,
            SUM(place_flag)::INTEGER AS placed_count,
            ROUND(AVG(score_value), 2) AS field_average,
            ROUND(AVG(score_value) FILTER (WHERE win_flag = 1), 2) AS winner_average,
            ROUND(AVG(score_value) FILTER (WHERE place_flag = 1), 2) AS placed_average,
            ROUND(AVG(score_value) FILTER (WHERE win_flag = 0), 2) AS non_winner_average,
            ROUND(AVG(score_value) FILTER (WHERE place_flag = 0), 2) AS non_placed_average,
            ROUND(STDDEV_POP(score_value), 2) AS score_stddev,
            ROUND(AVG(weighted_value), 4) AS weighted_average,
            ROUND(AVG(weighted_value) FILTER (WHERE win_flag = 1), 4) AS weighted_winner_average,
            ROUND(AVG(weighted_value) FILTER (WHERE place_flag = 1), 4) AS weighted_placed_average,
            ROUND(CORR(score_value, win_flag)::NUMERIC, 4) AS win_correlation,
            ROUND(CORR(score_value, place_flag)::NUMERIC, 4) AS place_correlation
        FROM completed;
    """


def get_factor_effectiveness_report() -> Dict[str, Any]:
    try:
        dataset = fetch_one("""
            SELECT
                COUNT(*) AS runner_factor_rows,
                COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS completed_runner_rows,
                COUNT(*) FILTER (WHERE actual_position = 1) AS winner_rows,
                COUNT(*) FILTER (WHERE hit_place IS TRUE) AS placed_rows,
                COUNT(DISTINCT meeting_id) AS meeting_count,
                COUNT(DISTINCT track) AS track_count,
                COUNT(DISTINCT meeting_date) AS date_count,
                MIN(meeting_date) AS first_meeting_date,
                MAX(meeting_date) AS latest_meeting_date
            FROM rrt_runner_factor_snapshots
            WHERE capture_scope = 'full_field';
        """) or {}
        completed_runner_rows = _to_int(dataset.get("completed_runner_rows"))
        winner_rows = _to_int(dataset.get("winner_rows"))
        placed_rows = _to_int(dataset.get("placed_rows"))
        factors: List[Dict[str, Any]] = []
        for factor in FACTOR_COLUMNS:
            row = fetch_one(_factor_sql(factor["score_column"], factor["weighted_column"])) or {}
            winner_gap = round(_to_float(row.get("winner_average")) - _to_float(row.get("non_winner_average")), 2)
            place_gap = round(_to_float(row.get("placed_average")) - _to_float(row.get("non_placed_average")), 2)
            win_corr = _to_float(row.get("win_correlation"))
            place_corr = _to_float(row.get("place_correlation"))
            combined_score = round((win_corr * 0.6) + (place_corr * 0.4), 4)
            confidence = _confidence_from_sample(_to_int(row.get("runner_count")), _to_int(row.get("winner_count")), _to_int(row.get("placed_count")))
            factors.append({
                "factor": factor["key"], "label": factor["label"], "score_column": factor["score_column"], "weighted_column": factor["weighted_column"],
                "runner_count": _to_int(row.get("runner_count")), "winner_count": _to_int(row.get("winner_count")), "placed_count": _to_int(row.get("placed_count")),
                "field_average": _to_float(row.get("field_average")), "winner_average": _to_float(row.get("winner_average")), "placed_average": _to_float(row.get("placed_average")),
                "non_winner_average": _to_float(row.get("non_winner_average")), "non_placed_average": _to_float(row.get("non_placed_average")),
                "winner_gap": winner_gap, "place_gap": place_gap, "score_stddev": _to_float(row.get("score_stddev")),
                "weighted_average": _to_float(row.get("weighted_average")), "weighted_winner_average": _to_float(row.get("weighted_winner_average")), "weighted_placed_average": _to_float(row.get("weighted_placed_average")),
                "win_correlation": win_corr, "place_correlation": place_corr, "combined_predictive_score": combined_score,
                "signal_strength": _signal_strength(combined_score), "confidence": confidence,
                "recommendation": _recommendation_from_signal(factor["label"], winner_gap, place_gap, win_corr, place_corr, confidence),
            })
        ranked_by_win = sorted(factors, key=lambda item: item.get("win_correlation") or 0, reverse=True)
        ranked_by_place = sorted(factors, key=lambda item: item.get("place_correlation") or 0, reverse=True)
        ranked_combined = sorted(factors, key=lambda item: item.get("combined_predictive_score") or 0, reverse=True)
        for rank, item in enumerate(ranked_combined, start=1):
            item["predictive_rank"] = rank
        return {"success": True, "provider": "PostgreSQL", "analysis_version": ANALYSIS_VERSION, "report": "factor_effectiveness", "model_version": MODEL_VERSION, "analysis_only": True, "prediction_model_changed": False, "dataset": {**dataset, "confidence": _confidence_from_sample(completed_runner_rows, winner_rows, placed_rows)}, "summary": {"best_win_factor": ranked_by_win[0] if ranked_by_win else None, "best_place_factor": ranked_by_place[0] if ranked_by_place else None, "best_combined_factor": ranked_combined[0] if ranked_combined else None, "weakest_combined_factor": ranked_combined[-1] if ranked_combined else None}, "factors": ranked_combined, "rankings": {"by_win_correlation": ranked_by_win, "by_place_correlation": ranked_by_place, "by_combined_predictive_score": ranked_combined}, "safety_note": "Analysis only. No model weights or production prediction behaviour have been changed."}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "analysis_version": ANALYSIS_VERSION, "report": "factor_effectiveness", "error": str(error)}


def _trend_factor_group(score_column: str, meeting_ids: List[Any]) -> Dict[str, Any]:
    if not meeting_ids:
        return {"runner_count": 0, "place_correlation": 0}
    placeholders = ",".join(["%s"] * len(meeting_ids))
    return fetch_one(f"""
        WITH completed AS (
            SELECT {score_column}::NUMERIC AS score_value, CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END::NUMERIC AS place_flag
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL AND capture_scope = 'full_field' AND {score_column} IS NOT NULL AND meeting_id IN ({placeholders})
        )
        SELECT COUNT(*) AS runner_count, ROUND(CORR(score_value, place_flag)::NUMERIC, 4) AS place_correlation FROM completed;
    """, tuple(meeting_ids)) or {}


def get_factor_trend_report(limit: int = 30) -> Dict[str, Any]:
    try:
        rows = fetch_all("""
            SELECT DISTINCT meeting_id, meeting_date
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL AND capture_scope = 'full_field'
            ORDER BY meeting_date DESC, meeting_id DESC
            LIMIT %s;
        """, (limit * 2,))
        if not rows:
            return {"success": True, "provider": "PostgreSQL", "analysis_version": ANALYSIS_VERSION, "report": "factor_trends", "message": "No completed factor rows available.", "trends": []}
        recent_meeting_ids = [row.get("meeting_id") for row in rows[:limit]]
        previous_meeting_ids = [row.get("meeting_id") for row in rows[limit:limit * 2]]
        trends = []
        for factor in FACTOR_COLUMNS:
            recent = _trend_factor_group(factor["score_column"], recent_meeting_ids)
            previous = _trend_factor_group(factor["score_column"], previous_meeting_ids)
            movement = round(_to_float(recent.get("place_correlation")) - _to_float(previous.get("place_correlation")), 4)
            trend = "Improving" if movement >= 0.04 else "Declining" if movement <= -0.04 else "Stable"
            trends.append({"factor": factor["key"], "label": factor["label"], "recent_place_correlation": _to_float(recent.get("place_correlation")), "previous_place_correlation": _to_float(previous.get("place_correlation")), "movement": movement, "trend": trend, "recent_runner_count": _to_int(recent.get("runner_count")), "previous_runner_count": _to_int(previous.get("runner_count"))})
        return {"success": True, "provider": "PostgreSQL", "analysis_version": ANALYSIS_VERSION, "report": "factor_trends", "analysis_only": True, "recent_meeting_window": limit, "trends": sorted(trends, key=lambda item: abs(item.get("movement") or 0), reverse=True), "safety_note": "Trend analysis is observational only and does not change model weights."}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "analysis_version": ANALYSIS_VERSION, "report": "factor_trends", "error": str(error)}


def get_model_health_report() -> Dict[str, Any]:
    try:
        factor_report = get_factor_effectiveness_report()
        if not factor_report.get("success"):
            return factor_report
        dataset = factor_report.get("dataset") or {}
        factors = factor_report.get("factors") or []
        overall = fetch_one("""
            SELECT COUNT(*) AS meeting_count, ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy, ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate, ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate, ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate, ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
            FROM rrt_performance_snapshots;
        """) or {}
        completed_rows = _to_int(dataset.get("completed_runner_rows")); winners = _to_int(dataset.get("winner_rows")); placed = _to_int(dataset.get("placed_rows")); tracks = _to_int(dataset.get("track_count")); dates = _to_int(dataset.get("date_count"))
        readiness_checks = {"completed_runner_rows": completed_rows >= 1000, "winner_rows": winners >= 80, "placed_rows": placed >= 250, "track_diversity": tracks >= 20, "date_diversity": dates >= 7}
        readiness_score = round((sum(1 for value in readiness_checks.values() if value) / len(readiness_checks)) * 100, 1)
        maturity = "Mature" if readiness_score >= 90 else "Developing" if readiness_score >= 60 else "Early"
        best_factor = factors[0] if factors else None; weakest_factor = factors[-1] if factors else None
        return {"success": True, "provider": "PostgreSQL", "analysis_version": ANALYSIS_VERSION, "report": "model_health", "analysis_only": True, "prediction_model_changed": False, "model_version": MODEL_VERSION, "performance_summary": overall, "learning_dataset": dataset, "readiness": {"score": readiness_score, "maturity": maturity, "checks": readiness_checks, "minimums": {"completed_runner_rows": 1000, "winner_rows": 80, "placed_rows": 250, "track_diversity": 20, "date_diversity": 7}}, "best_factor": best_factor, "weakest_factor": weakest_factor, "recommended_next_action": _model_health_action(maturity, best_factor, weakest_factor), "safety_note": "Model health is analysis-only. Production prediction weights remain unchanged."}
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "analysis_version": ANALYSIS_VERSION, "report": "model_health", "error": str(error)}


def _model_health_action(maturity: str, best_factor: Dict[str, Any], weakest_factor: Dict[str, Any]) -> str:
    if maturity == "Early":
        return "Continue collecting automated result updates before changing production weights. Use early factor rankings for monitoring only."
    if not best_factor:
        return "Continue collecting factor data."
    if maturity == "Developing":
        return f"Begin monitoring {best_factor.get('label')} as a candidate for future weighting review. Do not change production weights until the dataset reaches mature thresholds."
    if weakest_factor:
        return f"Review whether {best_factor.get('label')} should be strengthened and {weakest_factor.get('label')} should be reduced in a simulator before production use."
    return "Dataset is mature enough for simulation-only weight testing."
