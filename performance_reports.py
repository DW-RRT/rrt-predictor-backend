from typing import Any, Dict, List, Optional
from datetime import datetime
from html import escape
from io import BytesIO

from database import fetch_all, fetch_one

from factor_analysis import get_factor_effectiveness_report, get_model_health_report
from adaptive_weight_recommendations import get_weight_recommendations
from simulator_engine import get_best_simulations, get_simulation_history
from selection_intelligence import get_latest_selection_analysis


REPORT_VERSION = "2.18.3"
ANALYTICS_VERSION = "2.18.3"
DATABASE_SCHEMA_VERSION = "2.18.3"
MODEL_VERSION = "2.18.3"
LEARNING_VERSION = "2.18.3"


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _grade_from_accuracy(value: Any) -> str:
    accuracy = _to_float(value)

    if accuracy >= 60:
        return "Strong"

    if accuracy >= 45:
        return "Good"

    if accuracy >= 35:
        return "Developing"

    return "Needs Review"


def _dominant_metric(summary: Dict[str, Any], mode: str = "best") -> Dict[str, Any]:
    metrics = {
        "top_win": summary.get("avg_top_win_strike_rate"),
        "each_way": summary.get("avg_each_way_strike_rate"),
        "roughie": summary.get("avg_roughie_strike_rate"),
        "double": summary.get("avg_double_strike_rate"),
        "quaddie": summary.get("avg_quaddie_strike_rate"),
        "pf_ai_top_win": summary.get("avg_pf_ai_top_win_strike_rate"),
    }

    cleaned = {
        key: _to_float(value)
        for key, value in metrics.items()
        if value is not None
    }

    if not cleaned:
        return {
            "metric": None,
            "value": None,
        }

    if mode == "worst":
        metric, value = min(cleaned.items(), key=lambda item: item[1])
    else:
        metric, value = max(cleaned.items(), key=lambda item: item[1])

    return {
        "metric": metric,
        "value": round(value, 2),
    }


def _learning_confidence(
    meeting_count: int,
    race_count: int,
    unique_tracks: int,
    unique_dates: int,
    model_count: int,
) -> str:
    if (
        meeting_count >= 60
        and race_count >= 400
        and unique_tracks >= 25
        and unique_dates >= 7
        and model_count >= 1
    ):
        return "High"

    if (
        meeting_count >= 35
        and race_count >= 200
        and unique_tracks >= 15
        and unique_dates >= 5
    ):
        return "Medium"

    return "Low"


def _learning_recommendation(confidence: str, ready: bool) -> str:
    if ready and confidence == "High":
        return (
            "Historical dataset is sufficient to begin adaptive weight analysis. "
            "Proceed with analysis-only recommendations before changing production weights."
        )

    if ready:
        return (
            "Dataset is usable for early adaptive analysis, but recommendations "
            "should remain conservative until more meetings are collected."
        )

    return (
        "Continue collecting/importing validated performance snapshots before "
        "adaptive weighting is enabled."
    )


# ---------------------------------------------------------------------
# Existing reporting endpoints - retained and version-aligned
# ---------------------------------------------------------------------


def get_overall_performance_report() -> Dict[str, Any]:
    try:
        summary = fetch_one(
            """
            SELECT
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
                ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
                ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
                ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
            FROM rrt_performance_snapshots;
            """
        )

        latest = fetch_all(
            """
            SELECT
                meeting_id,
                track,
                meeting_date,
                model_version,
                overall_accuracy,
                top_win_strike_rate,
                each_way_strike_rate,
                roughie_strike_rate,
                double_strike_rate,
                quaddie_strike_rate,
                pf_ai_top_win_strike_rate,
                created_at
            FROM rrt_performance_snapshots
            ORDER BY created_at DESC
            LIMIT 20;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "overall_performance",
            "summary": summary or {},
            "latest_meetings": latest,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "overall_performance",
            "error": str(error),
        }


def get_track_performance_report() -> Dict[str, Any]:
    try:
        tracks = fetch_all(
            """
            SELECT
                track,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
                ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
                ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate
            FROM rrt_performance_snapshots
            WHERE track IS NOT NULL
            GROUP BY track
            ORDER BY avg_overall_accuracy DESC, meeting_count DESC;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "track_performance",
            "track_count": len(tracks),
            "tracks": tracks,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "track_performance",
            "error": str(error),
        }


def get_best_worst_tracks_report(limit: int = 10) -> Dict[str, Any]:
    try:
        best_tracks = fetch_all(
            """
            SELECT
                track,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate
            FROM rrt_performance_snapshots
            WHERE track IS NOT NULL
            GROUP BY track
            ORDER BY avg_overall_accuracy DESC, meeting_count DESC
            LIMIT %s;
            """,
            (limit,),
        )

        worst_tracks = fetch_all(
            """
            SELECT
                track,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate
            FROM rrt_performance_snapshots
            WHERE track IS NOT NULL
            GROUP BY track
            ORDER BY avg_overall_accuracy ASC, meeting_count DESC
            LIMIT %s;
            """,
            (limit,),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "best_worst_tracks",
            "limit": limit,
            "best_tracks": best_tracks,
            "worst_tracks": worst_tracks,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "best_worst_tracks",
            "error": str(error),
        }


def get_rrt_vs_pf_ai_report() -> Dict[str, Any]:
    try:
        summary = fetch_one(
            """
            SELECT
                COUNT(*) AS meeting_count,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_rrt_top_win,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win,
                ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_advantage
            FROM rrt_performance_snapshots;
            """
        )

        meetings = fetch_all(
            """
            SELECT
                meeting_id,
                track,
                meeting_date,
                top_win_strike_rate AS rrt_top_win,
                pf_ai_top_win_strike_rate AS pf_ai_top_win,
                ROUND(top_win_strike_rate - pf_ai_top_win_strike_rate, 2) AS rrt_advantage,
                overall_accuracy
            FROM rrt_performance_snapshots
            ORDER BY meeting_date DESC, track ASC
            LIMIT 50;
            """
        )

        rrt_wins = fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM rrt_performance_snapshots
            WHERE top_win_strike_rate > pf_ai_top_win_strike_rate;
            """
        )

        pf_ai_wins = fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM rrt_performance_snapshots
            WHERE pf_ai_top_win_strike_rate > top_win_strike_rate;
            """
        )

        ties = fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM rrt_performance_snapshots
            WHERE pf_ai_top_win_strike_rate = top_win_strike_rate;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "rrt_vs_pf_ai",
            "summary": summary or {},
            "head_to_head": {
                "rrt_wins": _to_int((rrt_wins or {}).get("count")),
                "pf_ai_wins": _to_int((pf_ai_wins or {}).get("count")),
                "ties": _to_int((ties or {}).get("count")),
            },
            "meetings": meetings,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "rrt_vs_pf_ai",
            "error": str(error),
        }


def get_daily_performance_report() -> Dict[str, Any]:
    try:
        days = fetch_all(
            """
            SELECT
                meeting_date,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate
            FROM rrt_performance_snapshots
            GROUP BY meeting_date
            ORDER BY meeting_date DESC;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "daily_performance",
            "day_count": len(days),
            "days": days,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "daily_performance",
            "error": str(error),
        }


def get_model_version_report() -> Dict[str, Any]:
    try:
        models = fetch_all(
            """
            SELECT
                model_version,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate
            FROM rrt_performance_snapshots
            GROUP BY model_version
            ORDER BY model_version DESC;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "model_version_performance",
            "model_count": len(models),
            "models": models,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "model_version_performance",
            "error": str(error),
        }


# ---------------------------------------------------------------------
# v2.10.0 Analytics endpoints
# ---------------------------------------------------------------------


def get_analytics_summary() -> Dict[str, Any]:
    try:
        summary = fetch_one(
            """
            SELECT
                COUNT(*) AS meeting_count,
                COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER), 0) AS race_count,
                COUNT(DISTINCT track) AS unique_tracks,
                COUNT(DISTINCT meeting_date) AS unique_dates,
                COUNT(DISTINCT model_version) AS model_version_count,
                MIN(meeting_date) AS first_meeting_date,
                MAX(meeting_date) AS latest_meeting_date,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
                ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
                ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
                ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
            FROM rrt_performance_snapshots;
            """
        ) or {}

        models = fetch_all(
            """
            SELECT
                model_version,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy
            FROM rrt_performance_snapshots
            WHERE model_version IS NOT NULL
            GROUP BY model_version
            ORDER BY model_version DESC;
            """
        )

        best_track = fetch_one(
            """
            SELECT
                track,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy
            FROM rrt_performance_snapshots
            WHERE track IS NOT NULL
            GROUP BY track
            ORDER BY avg_overall_accuracy DESC, meeting_count DESC
            LIMIT 1;
            """
        )

        worst_track = fetch_one(
            """
            SELECT
                track,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy
            FROM rrt_performance_snapshots
            WHERE track IS NOT NULL
            GROUP BY track
            ORDER BY avg_overall_accuracy ASC, meeting_count DESC
            LIMIT 1;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_summary",
            "database_schema_version": DATABASE_SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "summary": {
                **summary,
                "performance_grade": _grade_from_accuracy(summary.get("avg_overall_accuracy")),
                "best_metric": _dominant_metric(summary, mode="best"),
                "weakest_metric": _dominant_metric(summary, mode="worst"),
            },
            "model_versions": models,
            "best_track": best_track,
            "weakest_track": worst_track,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_summary",
            "error": str(error),
        }


def get_analytics_by_track(min_meetings: int = 1, limit: int = 100) -> Dict[str, Any]:
    try:
        tracks = fetch_all(
            """
            SELECT
                track,
                COUNT(*) AS meeting_count,
                COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER), 0) AS race_count,
                MIN(meeting_date) AS first_meeting_date,
                MAX(meeting_date) AS latest_meeting_date,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
                ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
                ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
                ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
            FROM rrt_performance_snapshots
            WHERE track IS NOT NULL
            GROUP BY track
            HAVING COUNT(*) >= %s
            ORDER BY avg_overall_accuracy DESC, meeting_count DESC, track ASC
            LIMIT %s;
            """,
            (min_meetings, limit),
        )

        ranked_tracks: List[Dict[str, Any]] = []

        for rank, track in enumerate(tracks, start=1):
            ranked_tracks.append(
                {
                    "rank": rank,
                    **track,
                    "grade": _grade_from_accuracy(track.get("avg_overall_accuracy")),
                }
            )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_by_track",
            "min_meetings": min_meetings,
            "limit": limit,
            "track_count": len(ranked_tracks),
            "tracks": ranked_tracks,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_by_track",
            "error": str(error),
        }


def get_analytics_by_date(limit: int = 60) -> Dict[str, Any]:
    try:
        days = fetch_all(
            """
            SELECT
                meeting_date,
                COUNT(*) AS meeting_count,
                COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER), 0) AS race_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
                ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
                ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
                ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
            FROM rrt_performance_snapshots
            GROUP BY meeting_date
            ORDER BY meeting_date DESC
            LIMIT %s;
            """,
            (limit,),
        )

        ranked_days: List[Dict[str, Any]] = []

        for day in days:
            ranked_days.append(
                {
                    **day,
                    "grade": _grade_from_accuracy(day.get("avg_overall_accuracy")),
                }
            )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_by_date",
            "limit": limit,
            "day_count": len(ranked_days),
            "days": ranked_days,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_by_date",
            "error": str(error),
        }


def get_analytics_rrt_vs_pf_ai(limit: int = 100) -> Dict[str, Any]:
    try:
        summary = fetch_one(
            """
            SELECT
                COUNT(*) AS meeting_count,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_rrt_top_win,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win,
                ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_advantage,
                ROUND(MAX(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS largest_rrt_advantage,
                ROUND(MIN(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS largest_pf_ai_advantage
            FROM rrt_performance_snapshots;
            """
        ) or {}

        head_to_head = fetch_one(
            """
            SELECT
                SUM(CASE WHEN top_win_strike_rate > pf_ai_top_win_strike_rate THEN 1 ELSE 0 END) AS rrt_wins,
                SUM(CASE WHEN pf_ai_top_win_strike_rate > top_win_strike_rate THEN 1 ELSE 0 END) AS pf_ai_wins,
                SUM(CASE WHEN pf_ai_top_win_strike_rate = top_win_strike_rate THEN 1 ELSE 0 END) AS ties
            FROM rrt_performance_snapshots;
            """
        ) or {}

        meeting_count = _to_int(summary.get("meeting_count"))
        rrt_wins = _to_int(head_to_head.get("rrt_wins"))
        pf_ai_wins = _to_int(head_to_head.get("pf_ai_wins"))
        ties = _to_int(head_to_head.get("ties"))

        meetings = fetch_all(
            """
            SELECT
                meeting_id,
                track,
                meeting_date,
                model_version,
                top_win_strike_rate AS rrt_top_win,
                pf_ai_top_win_strike_rate AS pf_ai_top_win,
                ROUND(top_win_strike_rate - pf_ai_top_win_strike_rate, 2) AS rrt_advantage,
                overall_accuracy
            FROM rrt_performance_snapshots
            ORDER BY meeting_date DESC, track ASC
            LIMIT %s;
            """,
            (limit,),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_rrt_vs_pf_ai",
            "summary": {
                **summary,
                "rrt_win_percentage": (
                    round((rrt_wins / meeting_count) * 100, 2)
                    if meeting_count
                    else 0
                ),
                "pf_ai_win_percentage": (
                    round((pf_ai_wins / meeting_count) * 100, 2)
                    if meeting_count
                    else 0
                ),
                "tie_percentage": (
                    round((ties / meeting_count) * 100, 2)
                    if meeting_count
                    else 0
                ),
            },
            "head_to_head": {
                "rrt_wins": rrt_wins,
                "pf_ai_wins": pf_ai_wins,
                "ties": ties,
            },
            "limit": limit,
            "meetings": meetings,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "analytics_rrt_vs_pf_ai",
            "error": str(error),
        }


def get_analytics_learning_readiness() -> Dict[str, Any]:
    try:
        summary = fetch_one(
            """
            SELECT
                COUNT(*) AS meeting_count,
                COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER), 0) AS race_count,
                COUNT(DISTINCT track) AS unique_tracks,
                COUNT(DISTINCT meeting_date) AS unique_dates,
                COUNT(DISTINCT model_version) AS model_version_count,
                MIN(meeting_date) AS first_meeting_date,
                MAX(meeting_date) AS latest_meeting_date,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(STDDEV_POP(overall_accuracy), 2) AS overall_accuracy_stddev,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
            FROM rrt_performance_snapshots;
            """
        ) or {}

        models = fetch_all(
            """
            SELECT
                model_version,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy
            FROM rrt_performance_snapshots
            WHERE model_version IS NOT NULL
            GROUP BY model_version
            ORDER BY model_version DESC;
            """
        )

        missing_core_metrics = fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM rrt_performance_snapshots
            WHERE overall_accuracy IS NULL
               OR top_win_strike_rate IS NULL
               OR each_way_strike_rate IS NULL
               OR pf_ai_top_win_strike_rate IS NULL;
            """
        )

        meeting_count = _to_int(summary.get("meeting_count"))
        race_count = _to_int(summary.get("race_count"))
        unique_tracks = _to_int(summary.get("unique_tracks"))
        unique_dates = _to_int(summary.get("unique_dates"))
        model_count = _to_int(summary.get("model_version_count"))
        missing_count = _to_int((missing_core_metrics or {}).get("count"))

        minimums = {
            "meetings": 50,
            "races": 300,
            "unique_tracks": 20,
            "unique_dates": 7,
            "model_versions": 1,
        }

        checks = {
            "minimum_meetings_met": meeting_count >= minimums["meetings"],
            "minimum_races_met": race_count >= minimums["races"],
            "track_diversity_met": unique_tracks >= minimums["unique_tracks"],
            "date_diversity_met": unique_dates >= minimums["unique_dates"],
            "model_version_present": model_count >= minimums["model_versions"],
            "core_metrics_complete": missing_count == 0,
        }

        ready_for_learning = all(checks.values())
        confidence = _learning_confidence(
            meeting_count=meeting_count,
            race_count=race_count,
            unique_tracks=unique_tracks,
            unique_dates=unique_dates,
            model_count=model_count,
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "learning_readiness",
            "ready_for_learning": ready_for_learning,
            "confidence": confidence,
            "minimum_requirements": minimums,
            "checks": checks,
            "data_profile": {
                **summary,
                "missing_core_metric_rows": missing_count,
                "model_versions": models,
            },
            "recommendation": _learning_recommendation(
                confidence=confidence,
                ready=ready_for_learning,
            ),
            "safety_note": (
                "This endpoint authorises analysis only. It does not change "
                "prediction weights or production model behaviour."
            ),
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "analytics_version": ANALYTICS_VERSION,
            "report": "learning_readiness",
            "error": str(error),
        }


# ---------------------------------------------------------------------
# v2.11.0 Learning Centre
# ---------------------------------------------------------------------

def _pct(value: Any) -> str:
    return f"{_to_float(value):.2f}%"


def _now_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _metric_label(metric: Any) -> str:
    return {
        "top_win": "Top Win",
        "each_way": "Each Way",
        "roughie": "Roughie",
        "double": "Double",
        "quaddie": "Quadrella",
        "pf_ai_top_win": "PF AI Top Win",
    }.get(str(metric or ""), str(metric or "N/A"))


def _learning_summary_sql() -> str:
    return """
        SELECT
            COUNT(*) AS meeting_count,
            COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER), 0) AS race_count,
            COUNT(DISTINCT track) AS unique_tracks,
            COUNT(DISTINCT meeting_date) AS unique_dates,
            COUNT(DISTINCT model_version) AS model_version_count,
            MIN(meeting_date) AS first_meeting_date,
            MAX(meeting_date) AS latest_meeting_date,
            ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
            ROUND(STDDEV_POP(overall_accuracy), 2) AS overall_accuracy_stddev,
            ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
            ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
            ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
            ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
            ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
            ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
            ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
        FROM rrt_performance_snapshots;
    """


def _track_rollup_sql(order_clause: str, having_clause: str = "") -> str:
    return f"""
        SELECT
            track,
            COUNT(*) AS meeting_count,
            COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER), 0) AS race_count,
            ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
            ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
            ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
            ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
        FROM rrt_performance_snapshots
        WHERE track IS NOT NULL
        GROUP BY track
        {having_clause}
        {order_clause}
        LIMIT 10;
    """


def _learning_base() -> Dict[str, Any]:
    summary = fetch_one(_learning_summary_sql()) or {}
    h2h = fetch_one(
        """
        SELECT
            SUM(CASE WHEN top_win_strike_rate > pf_ai_top_win_strike_rate THEN 1 ELSE 0 END) AS rrt_wins,
            SUM(CASE WHEN pf_ai_top_win_strike_rate > top_win_strike_rate THEN 1 ELSE 0 END) AS pf_ai_wins,
            SUM(CASE WHEN pf_ai_top_win_strike_rate = top_win_strike_rate THEN 1 ELSE 0 END) AS ties
        FROM rrt_performance_snapshots;
        """
    ) or {}
    meeting_count = _to_int(summary.get("meeting_count"))
    race_count = _to_int(summary.get("race_count"))
    unique_tracks = _to_int(summary.get("unique_tracks"))
    unique_dates = _to_int(summary.get("unique_dates"))
    model_count = _to_int(summary.get("model_version_count"))
    minimums = {"meetings": 50, "races": 300, "unique_tracks": 20, "unique_dates": 7, "model_versions": 1}
    checks = {
        "minimum_meetings_met": meeting_count >= minimums["meetings"],
        "minimum_races_met": race_count >= minimums["races"],
        "track_diversity_met": unique_tracks >= minimums["unique_tracks"],
        "date_diversity_met": unique_dates >= minimums["unique_dates"],
        "model_version_present": model_count >= minimums["model_versions"],
    }
    confidence = _learning_confidence(meeting_count, race_count, unique_tracks, unique_dates, model_count)
    return {
        "summary": summary,
        "head_to_head": {
            "rrt_wins": _to_int(h2h.get("rrt_wins")),
            "pf_ai_wins": _to_int(h2h.get("pf_ai_wins")),
            "ties": _to_int(h2h.get("ties")),
        },
        "minimums": minimums,
        "checks": checks,
        "ready_for_learning": all(checks.values()),
        "confidence": confidence,
    }


def _learning_tracks() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "strong_tracks": fetch_all(_track_rollup_sql("ORDER BY avg_overall_accuracy DESC, meeting_count DESC")),
        "review_tracks": fetch_all(_track_rollup_sql("ORDER BY avg_overall_accuracy ASC, meeting_count DESC")),
        "reliable_tracks": fetch_all(_track_rollup_sql("ORDER BY avg_overall_accuracy DESC, meeting_count DESC", "HAVING COUNT(*) >= 2")),
    }


def _learning_dates() -> Dict[str, List[Dict[str, Any]]]:
    recent = fetch_all(
        """
        SELECT
            meeting_date,
            COUNT(*) AS meeting_count,
            COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER), 0) AS race_count,
            ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
            ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
            ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
            ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
            ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
            ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
            ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate), 2) AS avg_rrt_vs_pf_ai_gap
        FROM rrt_performance_snapshots
        GROUP BY meeting_date
        ORDER BY meeting_date DESC
        LIMIT 20;
        """
    )
    return {
        "recent_days": recent,
        "best_days": sorted(recent, key=lambda x: _to_float(x.get("avg_overall_accuracy")), reverse=True)[:5],
        "weakest_days": sorted(recent, key=lambda x: _to_float(x.get("avg_overall_accuracy")))[:5],
    }


def _learning_strengths(base: Dict[str, Any], tracks: Dict[str, Any], dates: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = base.get("summary") or {}
    h2h = base.get("head_to_head") or {}
    best = _dominant_metric(summary, "best")
    rows = [{
        "area": f"{_metric_label(best.get('metric'))} Performance",
        "metric_value": best.get("value"),
        "priority": "Maintain",
        "evidence": f"{_metric_label(best.get('metric'))} is currently the strongest category at {_pct(best.get('value'))}.",
    }]
    if _to_float(summary.get("avg_rrt_vs_pf_ai_gap")) > 0:
        rows.append({
            "area": "RRT vs PF AI",
            "metric_value": summary.get("avg_rrt_vs_pf_ai_gap"),
            "priority": "Maintain",
            "evidence": f"RRT is ahead of PF AI by {_pct(summary.get('avg_rrt_vs_pf_ai_gap'))}, with {h2h.get('rrt_wins')} RRT wins versus {h2h.get('pf_ai_wins')} PF AI wins.",
        })
    reliable = tracks.get("reliable_tracks") or []
    if reliable:
        item = reliable[0]
        rows.append({
            "area": "Repeat Track Performance",
            "metric_value": item.get("avg_overall_accuracy"),
            "priority": "Maintain",
            "evidence": f"{item.get('track')} is the strongest track with repeat data at {_pct(item.get('avg_overall_accuracy'))}.",
        })
    best_days = dates.get("best_days") or []
    if best_days:
        item = best_days[0]
        rows.append({
            "area": "Best Daily Performance",
            "metric_value": item.get("avg_overall_accuracy"),
            "priority": "Monitor",
            "evidence": f"{item.get('meeting_date')} is the strongest analysed day at {_pct(item.get('avg_overall_accuracy'))} across {item.get('meeting_count')} meetings.",
        })
    return rows


def _learning_weaknesses(base: Dict[str, Any], tracks: Dict[str, Any], dates: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = base.get("summary") or {}
    weak = _dominant_metric(summary, "worst")
    rows = [{
        "area": f"{_metric_label(weak.get('metric'))} Performance",
        "metric_value": weak.get("value"),
        "priority": "High" if weak.get("metric") == "roughie" else "Medium",
        "evidence": f"{_metric_label(weak.get('metric'))} is currently the weakest category at {_pct(weak.get('value'))}.",
    }]
    review = tracks.get("review_tracks") or []
    if review:
        item = review[0]
        rows.append({"area": "Track Review", "metric_value": item.get("avg_overall_accuracy"), "priority": "Medium", "evidence": f"{item.get('track')} is the lowest-ranked track at {_pct(item.get('avg_overall_accuracy'))}."})
    weak_days = dates.get("weakest_days") or []
    if weak_days:
        item = weak_days[0]
        rows.append({"area": "Daily Volatility", "metric_value": item.get("avg_overall_accuracy"), "priority": "Medium", "evidence": f"{item.get('meeting_date')} is the weakest analysed day at {_pct(item.get('avg_overall_accuracy'))}."})
    if _to_float(summary.get("overall_accuracy_stddev")) >= 12:
        rows.append({"area": "Performance Stability", "metric_value": summary.get("overall_accuracy_stddev"), "priority": "Medium", "evidence": f"Overall accuracy standard deviation is {_to_float(summary.get('overall_accuracy_stddev')):.2f}, indicating meaningful variation across meetings."})
    return rows


def _learning_actions(base: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = base.get("summary") or {}
    actions = []
    if _to_float(summary.get("avg_roughie_strike_rate")) < 20:
        actions.append({"priority": "High", "action": "Improve roughie selection logic", "reason": f"Roughie strike rate is {_pct(summary.get('avg_roughie_strike_rate'))}, materially below other categories.", "next_step": "Use the v2.13.0 automatic results processor to keep factor data current, then compare roughie candidates against completed result outcomes."})
    if _to_float(summary.get("avg_top_win_strike_rate")) < 35:
        actions.append({"priority": "High", "action": "Review top-win ranking precision", "reason": f"Top-win strike rate is {_pct(summary.get('avg_top_win_strike_rate'))}.", "next_step": "Compare top-win selections against PF AI, winner price bands, track condition, and field size once factor capture is available."})
    if _to_float(summary.get("avg_rrt_vs_pf_ai_gap")) > 0:
        actions.append({"priority": "Medium", "action": "Protect current RRT advantage over PF AI", "reason": f"RRT is currently ahead of PF AI by {_pct(summary.get('avg_rrt_vs_pf_ai_gap'))}.", "next_step": "Any future adaptive weighting should be tested against this baseline before production."})
    if base.get("ready_for_learning"):
        actions.append({"priority": "Medium", "action": "Review factor-capture dataset", "reason": "Dataset is large enough for learning analysis and v2.13.0 now automatically updates runner-level scoring factors after results are processed.", "next_step": "Collect completed meetings with factor rows and compare winning runners against each scoring component before recommending specific weight changes."})
    return actions



# ---------------------------------------------------------------------
# v2.12.3 Rolling Each-Way Leaderboards
# ---------------------------------------------------------------------

MIN_LEADERBOARD_RUNNERS = 1


def _rank_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "rank": index,
            **row,
        }
        for index, row in enumerate(rows, start=1)
    ]


def get_each_way_leaderboards(
    min_runners: int = MIN_LEADERBOARD_RUNNERS,
    limit: int = 10,
) -> Dict[str, Any]:
    try:
        totals = fetch_one(
            """
            SELECT
                COUNT(*) AS runner_factor_rows,
                COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS runners_with_results,
                COUNT(*) FILTER (WHERE hit_place IS TRUE) AS placed_runners,
                COUNT(DISTINCT meeting_id) AS meeting_count,
                COUNT(DISTINCT track) AS track_count,
                COUNT(DISTINCT meeting_date) AS date_count
            FROM rrt_runner_factor_snapshots;
            """
        ) or {}

        trainers = fetch_all(
            """
            SELECT
                NULLIF(TRIM(factor_json->>'trainer'), '') AS trainer,
                COUNT(*) AS runner_count,
                SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END) AS place_count,
                ROUND(
                    (SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100,
                    2
                ) AS each_way_place_strike_rate,
                ROUND(AVG(final_score), 2) AS avg_final_score,
                ROUND(AVG(confidence), 2) AS avg_confidence
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL
              AND NULLIF(TRIM(factor_json->>'trainer'), '') IS NOT NULL
              AND UPPER(TRIM(factor_json->>'trainer')) NOT IN ('N/A', 'UNKNOWN', 'NONE')
            GROUP BY NULLIF(TRIM(factor_json->>'trainer'), '')
            HAVING COUNT(*) >= %s
            ORDER BY each_way_place_strike_rate DESC, place_count DESC, runner_count DESC, avg_final_score DESC
            LIMIT %s;
            """,
            (min_runners, limit),
        )

        jockeys = fetch_all(
            """
            SELECT
                NULLIF(TRIM(factor_json->>'jockey'), '') AS jockey,
                COUNT(*) AS runner_count,
                SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END) AS place_count,
                ROUND(
                    (SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100,
                    2
                ) AS each_way_place_strike_rate,
                ROUND(AVG(final_score), 2) AS avg_final_score,
                ROUND(AVG(confidence), 2) AS avg_confidence
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL
              AND NULLIF(TRIM(factor_json->>'jockey'), '') IS NOT NULL
              AND UPPER(TRIM(factor_json->>'jockey')) NOT IN ('N/A', 'UNKNOWN', 'NONE')
            GROUP BY NULLIF(TRIM(factor_json->>'jockey'), '')
            HAVING COUNT(*) >= %s
            ORDER BY each_way_place_strike_rate DESC, place_count DESC, runner_count DESC, avg_final_score DESC
            LIMIT %s;
            """,
            (min_runners, limit),
        )

        combinations = fetch_all(
            """
            SELECT
                CONCAT(
                    NULLIF(TRIM(factor_json->>'trainer'), ''),
                    ' / ',
                    NULLIF(TRIM(factor_json->>'jockey'), '')
                ) AS trainer_jockey_combination,
                COUNT(*) AS runner_count,
                SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END) AS place_count,
                ROUND(
                    (SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100,
                    2
                ) AS each_way_place_strike_rate,
                ROUND(AVG(final_score), 2) AS avg_final_score,
                ROUND(AVG(confidence), 2) AS avg_confidence
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL
              AND NULLIF(TRIM(factor_json->>'trainer'), '') IS NOT NULL
              AND NULLIF(TRIM(factor_json->>'jockey'), '') IS NOT NULL
              AND UPPER(TRIM(factor_json->>'trainer')) NOT IN ('N/A', 'UNKNOWN', 'NONE')
              AND UPPER(TRIM(factor_json->>'jockey')) NOT IN ('N/A', 'UNKNOWN', 'NONE')
            GROUP BY
                NULLIF(TRIM(factor_json->>'trainer'), ''),
                NULLIF(TRIM(factor_json->>'jockey'), '')
            HAVING COUNT(*) >= %s
            ORDER BY each_way_place_strike_rate DESC, place_count DESC, runner_count DESC, avg_final_score DESC
            LIMIT %s;
            """,
            (min_runners, limit),
        )

        horses = fetch_all(
            """
            SELECT
                COALESCE(
                    NULLIF(TRIM(runner_name), ''),
                    NULLIF(TRIM(factor_json->>'horse_name'), ''),
                    NULLIF(TRIM(factor_json->>'runner'), '')
                ) AS horse,
                COUNT(*) AS runner_count,
                SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END) AS place_count,
                ROUND(
                    (SUM(CASE WHEN hit_place IS TRUE THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100,
                    2
                ) AS each_way_place_strike_rate,
                ROUND(AVG(final_score), 2) AS avg_final_score,
                ROUND(AVG(confidence), 2) AS avg_confidence
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL
              AND COALESCE(
                    NULLIF(TRIM(runner_name), ''),
                    NULLIF(TRIM(factor_json->>'horse_name'), ''),
                    NULLIF(TRIM(factor_json->>'runner'), '')
                  ) IS NOT NULL
            GROUP BY
                COALESCE(
                    NULLIF(TRIM(runner_name), ''),
                    NULLIF(TRIM(factor_json->>'horse_name'), ''),
                    NULLIF(TRIM(factor_json->>'runner'), '')
                )
            HAVING COUNT(*) >= %s
            ORDER BY each_way_place_strike_rate DESC, place_count DESC, runner_count DESC, avg_final_score DESC
            LIMIT %s;
            """,
            (min_runners, limit),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report": "rolling_each_way_leaderboards",
            "leaderboard_version": "2.15.0",
            "generated_at": _now_utc_iso(),
            "minimum_runners": min_runners,
            "limit": limit,
            "ranking_method": "Each-way placing success based on hit_place = true in rrt_runner_factor_snapshots.",
            "dataset": totals,
            "top_trainers": _rank_rows(trainers),
            "top_jockeys": _rank_rows(jockeys),
            "top_trainer_jockey_combinations": _rank_rows(combinations),
            "top_horses": _rank_rows(horses),
            "note": (
                "These are rolling figures from v2.12.1+ factor capture rows after official results have updated. "
                "Early figures may be volatile until more completed meetings are collected."
            ),
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report": "rolling_each_way_leaderboards",
            "leaderboard_version": "2.15.0",
            "error": str(error),
        }


def get_learning_recommendations() -> Dict[str, Any]:
    try:
        base = _learning_base()
        tracks = _learning_tracks()
        dates = _learning_dates()
        return {
            "success": True,
            "provider": "PostgreSQL",
            "learning_version": LEARNING_VERSION,
            "report": "learning_recommendations",
            "generated_at": _now_utc_iso(),
            "analysis_only": True,
            "prediction_model_changed": False,
            "database_schema_version": DATABASE_SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "learning_status": {
                "ready_for_learning": base.get("ready_for_learning"),
                "confidence": base.get("confidence"),
                "minimum_requirements": base.get("minimums"),
                "checks": base.get("checks"),
                "recommendation": _learning_recommendation(base.get("confidence"), bool(base.get("ready_for_learning"))),
            },
            "dataset": base.get("summary"),
            "head_to_head": base.get("head_to_head"),
            "strengths": _learning_strengths(base, tracks, dates),
            "weaknesses": _learning_weaknesses(base, tracks, dates),
            "priority_action_plan": _learning_actions(base),
            "track_sets": tracks,
            "date_sets": dates,
            "each_way_leaderboards": get_each_way_leaderboards(),
            "factor_effectiveness": get_factor_effectiveness_report(),
            "weight_recommendations": get_weight_recommendations(),
            "model_health": get_model_health_report(),
            "simulation_history": get_simulation_history(limit=5),
            "best_simulations": get_best_simulations(limit=5),
            "selection_intelligence": get_latest_selection_analysis(),
            "safety_note": "This report is analysis-only. No model weights, scoring factors, or production prediction behaviour have been changed.",
        }
    except Exception as error:
        return {"success": False, "provider": "PostgreSQL", "learning_version": LEARNING_VERSION, "report": "learning_recommendations", "error": str(error)}


def _html_table(headers: List[str], rows: List[List[Any]]) -> str:
    th = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    trs = []
    for row in rows:
        trs.append("<tr>" + "".join(f"<td>{escape(str(c if c is not None else ''))}</td>" for c in row) + "</tr>")
    return "<table><thead><tr>" + th + "</tr></thead><tbody>" + "".join(trs) + "</tbody></table>"


def generate_learning_report_html() -> str:
    report = get_learning_recommendations()
    if not report.get("success"):
        return "<html><body><h1>RRT Predictor Learning Report</h1><pre>" + escape(str(report)) + "</pre></body></html>"
    dataset = report.get("dataset") or {}
    status = report.get("learning_status") or {}
    h2h = report.get("head_to_head") or {}
    tracks = report.get("track_sets") or {}
    dates = report.get("date_sets") or {}
    ready = "READY" if status.get("ready_for_learning") else "NOT READY"
    def card(label: str, value: Any) -> str:
        return f'<div class="card"><div class="label">{escape(label)}</div><div class="value">{escape(str(value))}</div></div>'
    html = [
        '<!doctype html><html><head><meta charset="utf-8"><title>RRT Predictor Learning Report</title>',
        '<style>body{font-family:Arial,Helvetica,sans-serif;margin:32px;color:#1f2933}h1,h2{color:#0f2f57}h2{border-bottom:2px solid #0f2f57;padding-bottom:6px;margin-top:30px}.subtitle{color:#52606d}.badge{display:inline-block;padding:8px 14px;border-radius:6px;background:#e3fcec;color:#014d40;font-weight:bold;margin-right:8px}.warning{background:#fffbea;color:#8d2b0b}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.card{border:1px solid #d9e2ec;border-radius:8px;padding:14px;background:#f8fafc}.label{color:#627d98;font-size:12px;text-transform:uppercase}.value{font-size:22px;font-weight:bold;color:#102a43}table{width:100%;border-collapse:collapse;margin:14px 0 22px 0;font-size:13px}th{background:#0f2f57;color:white;text-align:left;padding:8px}td{border:1px solid #d9e2ec;padding:8px;vertical-align:top}tr:nth-child(even){background:#f8fafc}.note{background:#f0f4f8;border-left:5px solid #0f2f57;padding:12px 14px;margin-top:20px}.footer{margin-top:40px;font-size:12px;color:#627d98;border-top:1px solid #d9e2ec;padding-top:12px}@media print{.no-print{display:none}table{page-break-inside:avoid}}</style></head><body>',
        '<div class="no-print"><button onclick="window.print()">Print / Save as PDF</button></div>',
        f'<h1>RRT Predictor Learning Report</h1><p class="subtitle">Version {LEARNING_VERSION} | Generated {escape(report.get("generated_at") or "")}</p>',
        f'<span class="badge">{ready}</span><span class="badge">Confidence: {escape(str(status.get("confidence")))}</span><span class="badge warning">Analysis Only: No model weights changed</span>',
        '<h2>Dataset Audit</h2><div class="grid">',
        card('Meetings', dataset.get('meeting_count')), card('Races', dataset.get('race_count')), card('Tracks', dataset.get('unique_tracks')), card('Dates', dataset.get('unique_dates')),
        card('Overall Accuracy', _pct(dataset.get('avg_overall_accuracy'))), card('Top Win', _pct(dataset.get('avg_top_win_strike_rate'))), card('Each Way', _pct(dataset.get('avg_each_way_strike_rate'))), card('RRT v PF AI', _pct(dataset.get('avg_rrt_vs_pf_ai_gap'))),
        '</div>',
        f'<div class="note"><strong>Learning Recommendation:</strong> {escape(str(status.get("recommendation")))}</div>',
        '<h2>Current Model Performance</h2>',
        _html_table(['Metric','Value'], [['Readiness Score', ((report.get('model_health') or {}).get('readiness') or {}).get('score')], ['Dataset Maturity', ((report.get('model_health') or {}).get('readiness') or {}).get('maturity')], ['Next Action', (report.get('model_health') or {}).get('recommended_next_action')]]),
        '<h2>Strengths</h2>', _html_table(['Area','Priority','Metric','Evidence'], [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('strengths') or []]),
        '<h2>Weaknesses</h2>', _html_table(['Area','Priority','Metric','Evidence'], [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('weaknesses') or []]),
        '<h2>Priority Action Plan</h2>', _html_table(['Priority','Action','Reason','Next Step'], [[i.get('priority'),i.get('action'),i.get('reason'),i.get('next_step')] for i in report.get('priority_action_plan') or []]),
        '<h2>Strongest Tracks</h2>', _html_table(['Track','Meetings','Races','Accuracy','RRT v PF AI'], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('strong_tracks') or [])[:10]]),
        '<h2>Tracks Requiring Review</h2>', _html_table(['Track','Meetings','Races','Accuracy','RRT v PF AI'], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('review_tracks') or [])[:10]]),
        '<h2>Recent Daily Performance</h2>', _html_table(['Date','Meetings','Races','Accuracy','RRT v PF AI'], [[i.get('meeting_date'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (dates.get('recent_days') or [])[:10]]),
        '<h2>Rolling Each-Way Leaderboards</h2>',
        '<div class="note">These leaderboards are based on completed v2.12.1+ runner factor rows where official results have been matched. Ranking is by each-way placing strike rate.</div>',
        '<h3>Top 10 Trainers</h3>', _html_table(['Rank','Trainer','Runners','Placed','Place Strike Rate','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('trainer'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_trainers') or [])[:10]]),
        '<h3>Top 10 Jockeys</h3>', _html_table(['Rank','Jockey','Runners','Placed','Place Strike Rate','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('jockey'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_jockeys') or [])[:10]]),
        '<h3>Top 10 Trainer / Jockey Combinations</h3>', _html_table(['Rank','Combination','Runners','Placed','Place Strike Rate','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_trainer_jockey_combinations') or [])[:10]]),
        '<h3>Top 10 Horses</h3>', _html_table(['Rank','Horse','Runs','Placed','Place Strike Rate','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('horse'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_horses') or [])[:10]]),
        '<h2>Evidence-Based Factor Analysis</h2>',
        '<div class="note">This section compares completed runner factor scores against actual results. It is analysis-only and does not change production weights.</div>',
        '<h3>Factor Effectiveness Ranking</h3>',
        _html_table(['Rank','Factor','Winner Gap','Place Gap','Win Corr','Place Corr','Signal','Confidence','Recommendation'], [[i.get('predictive_rank'),i.get('label'),i.get('winner_gap'),i.get('place_gap'),i.get('win_correlation'),i.get('place_correlation'),i.get('signal_strength'),i.get('confidence'),(i.get('recommendation') or {}).get('direction')] for i in ((report.get('factor_effectiveness') or {}).get('factors') or [])[:12]]),
        '<h3>Weight Recommendation Review</h3>',
        _html_table(['Factor','Current','Recommended','Change','Direction','Priority','Reason'], [[i.get('label'),i.get('current_weight'),i.get('recommended_weight'),i.get('change'),i.get('direction'),i.get('priority'),i.get('reason')] for i in ((report.get('weight_recommendations') or {}).get('recommendations') or [])[:12]]),
        '<h3>Model Health</h3>',
        _html_table(['Metric','Value'], [['Readiness Score', ((report.get('model_health') or {}).get('readiness') or {}).get('score')], ['Dataset Maturity', ((report.get('model_health') or {}).get('readiness') or {}).get('maturity')], ['Next Action', (report.get('model_health') or {}).get('recommended_next_action')]]),
        '<h2>Historical Weight Simulation</h2>',
        '<div class="note">v2.15.0 adds offline historical replay. Simulations compare alternative weights and roughie rules against stored completed runner data without changing production weights.</div>',
        _html_table(['Simulation','Factor','Old','New','Change','Runners','Races','Overall +/-','Top Win +/-','Each Way +/-','Roughie +/-','Status'], [[i.get('simulation_name'),i.get('factor_tested'),i.get('old_weight'),i.get('new_weight'),i.get('change_amount'),i.get('dataset_runner_count'),i.get('dataset_race_count'),(i.get('improvement_json') or {}).get('overall_accuracy') or i.get('overall_improvement'),(i.get('improvement_json') or {}).get('top_win_strike_rate') or i.get('top_win_improvement'),(i.get('improvement_json') or {}).get('each_way_strike_rate') or i.get('each_way_improvement'),(i.get('improvement_json') or {}).get('roughie_strike_rate') or i.get('roughie_improvement'),(i.get('recommendation_json') or {}).get('status')] for i in ((report.get('best_simulations') or {}).get('simulations') or [])[:10]]),
        '<h2>Selection Intelligence</h2>',
        '<div class="note">v2.17.0 analyses why winners were missed, including Top 4 boundary misses, value/roughie winners, false positives and factor gaps. This is analysis-only.</div>',
        _html_table(['Metric','Value'], [
            ['Top 4 Hit Rate', (((report.get('selection_intelligence') or {}).get('analysis') or {}).get('summary') or {}).get('top4_hit_rate')],
            ['Near Miss Rate', (((report.get('selection_intelligence') or {}).get('analysis') or {}).get('summary') or {}).get('near_miss_rate')],
            ['Boundary Miss Rate', (((report.get('selection_intelligence') or {}).get('analysis') or {}).get('summary') or {}).get('boundary_miss_rate')],
            ['Roughie-like Winner Rate', (((report.get('selection_intelligence') or {}).get('analysis') or {}).get('summary') or {}).get('roughie_like_winner_rate')],
            ['Average False Positives / Race', (((report.get('selection_intelligence') or {}).get('analysis') or {}).get('summary') or {}).get('avg_false_positives_per_race')]
        ]),
        _html_table(['Priority','Area','Recommendation','Evidence'], [
            [i.get('priority'), i.get('area'), i.get('recommendation'), i.get('evidence')]
            for i in ((((report.get('selection_intelligence') or {}).get('analysis') or {}).get('recommendations') or [])[:8])
        ]),
        f'<h2>Safety Statement</h2><div class="note">{escape(str(report.get("safety_note")))}</div>',
        f'<div class="footer">RRT Predictor | Backend 2.17.0 | Model {MODEL_VERSION} | Database Schema {DATABASE_SCHEMA_VERSION} | Generated {escape(report.get("generated_at") or "")}</div>',
        '</body></html>'
    ]
    return ''.join(html)


def generate_learning_report_pdf_bytes() -> bytes:
    report = get_learning_recommendations()
    buffer = BytesIO()
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except Exception as error:
        raise RuntimeError("ReportLab is required for PDF generation. Add reportlab to requirements.txt.") from error
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RRTTitle", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#0f2f57"), spaceAfter=12))
    styles.add(ParagraphStyle(name="RRTHeading", parent=styles["Heading2"], textColor=colors.HexColor("#0f2f57"), spaceBefore=14, spaceAfter=8))
    styles.add(ParagraphStyle(name="RRTSmall", parent=styles["BodyText"], fontSize=8, leading=10))
    def p(v: Any) -> Paragraph:
        return Paragraph(escape(str(v if v is not None else "")), styles["RRTSmall"])
    def t(headers: List[str], rows: List[List[Any]], widths: List[Any] = None) -> Table:
        table = Table([[p(h) for h in headers]] + [[p(c) for c in row] for row in rows], colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0f2f57")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#d9e2ec")),("BACKGROUND",(0,1),(-1,-1),colors.HexColor("#f8fafc")),("VALIGN",(0,0),(-1,-1),"TOP")]))
        return table
    story = []
    if not report.get("success"):
        story += [Paragraph("RRT Predictor Learning Report", styles["RRTTitle"]), p(report)]
        doc.build(story); buffer.seek(0); return buffer.getvalue()
    dataset = report.get("dataset") or {}; status = report.get("learning_status") or {}; h2h = report.get("head_to_head") or {}; tracks = report.get("track_sets") or {}; dates = report.get("date_sets") or {}
    story.append(Paragraph("RRT Predictor Learning Report", styles["RRTTitle"]))
    story.append(Paragraph(f"Version {LEARNING_VERSION} | Generated {report.get('generated_at')}", styles["BodyText"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Status: {'READY' if status.get('ready_for_learning') else 'NOT READY'} | Confidence: {status.get('confidence')} | Analysis Only: No model weights changed", styles["BodyText"]))
    story.append(Paragraph("Dataset Audit", styles["RRTHeading"]))
    story.append(t(["Metric","Value"], [["Meetings analysed",dataset.get('meeting_count')],["Races analysed",dataset.get('race_count')],["Unique tracks",dataset.get('unique_tracks')],["Unique dates",dataset.get('unique_dates')],["Date range",f"{dataset.get('first_meeting_date')} to {dataset.get('latest_meeting_date')}"],["Database schema",DATABASE_SCHEMA_VERSION],["Prediction model",MODEL_VERSION]], [7*cm,9*cm]))
    story.append(Paragraph("Learning Recommendation", styles["RRTHeading"])); story.append(Paragraph(escape(str(status.get("recommendation"))), styles["BodyText"]))
    story.append(Paragraph("Current Model Performance", styles["RRTHeading"]))
    story.append(t(["Metric","Value"], [["Overall Accuracy",_pct(dataset.get('avg_overall_accuracy'))],["Top Win",_pct(dataset.get('avg_top_win_strike_rate'))],["Each Way",_pct(dataset.get('avg_each_way_strike_rate'))],["Roughie",_pct(dataset.get('avg_roughie_strike_rate'))],["Double",_pct(dataset.get('avg_double_strike_rate'))],["Quadrella",_pct(dataset.get('avg_quaddie_strike_rate'))],["PF AI Top Win",_pct(dataset.get('avg_pf_ai_top_win_strike_rate'))],["RRT Advantage",_pct(dataset.get('avg_rrt_vs_pf_ai_gap'))],["RRT / PF AI / Ties",f"{h2h.get('rrt_wins')} / {h2h.get('pf_ai_wins')} / {h2h.get('ties')}"]], [7*cm,9*cm]))
    for title, rows in [("Strengths", [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('strengths') or []]), ("Weaknesses", [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('weaknesses') or []])]:
        story.append(Paragraph(title, styles["RRTHeading"])); story.append(t(["Area","Priority","Metric","Evidence"], rows, [3.5*cm,2.2*cm,2.2*cm,8.5*cm]))
    story.append(PageBreak())
    story.append(Paragraph("Priority Action Plan", styles["RRTHeading"])); story.append(t(["Priority","Action","Reason","Next Step"], [[i.get('priority'),i.get('action'),i.get('reason'),i.get('next_step')] for i in report.get('priority_action_plan') or []], [2.2*cm,3.8*cm,5*cm,5.6*cm]))
    story.append(Paragraph("Strongest Tracks", styles["RRTHeading"])); story.append(t(["Track","Meetings","Races","Accuracy","RRT v PF AI"], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('strong_tracks') or [])[:10]]))
    story.append(Paragraph("Tracks Requiring Review", styles["RRTHeading"])); story.append(t(["Track","Meetings","Races","Accuracy","RRT v PF AI"], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('review_tracks') or [])[:10]]))
    story.append(Paragraph("Recent Daily Performance", styles["RRTHeading"])); story.append(t(["Date","Meetings","Races","Accuracy","RRT v PF AI"], [[i.get('meeting_date'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (dates.get('recent_days') or [])[:10]]))

    leaderboards = report.get("each_way_leaderboards") or {}
    story.append(PageBreak())
    story.append(Paragraph("Rolling Each-Way Leaderboards", styles["RRTHeading"]))
    story.append(Paragraph("These leaderboards are based on completed v2.12.1+ runner factor rows where official results have been matched. Ranking is by each-way placing strike rate.", styles["BodyText"]))
    story.append(Paragraph("Top 10 Trainers", styles["RRTHeading"]))
    story.append(t(["Rank","Trainer","Runners","Placed","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('trainer'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_trainers') or [])[:10]]))
    story.append(Paragraph("Top 10 Jockeys", styles["RRTHeading"]))
    story.append(t(["Rank","Jockey","Runners","Placed","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('jockey'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_jockeys') or [])[:10]]))
    story.append(Paragraph("Top 10 Trainer / Jockey Combinations", styles["RRTHeading"]))
    story.append(t(["Rank","Combination","Runners","Placed","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_trainer_jockey_combinations') or [])[:10]]))
    story.append(Paragraph("Top 10 Horses", styles["RRTHeading"]))
    story.append(t(["Rank","Horse","Runs","Placed","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('horse'),i.get('runner_count'),i.get('place_count'),_pct(i.get('each_way_place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_horses') or [])[:10]]))
    story.append(PageBreak())
    story.append(Paragraph("Evidence-Based Factor Analysis", styles["RRTHeading"]))
    story.append(Paragraph("This section compares completed runner factor scores against actual results. It is analysis-only and does not change production weights.", styles["BodyText"]))
    factor_effectiveness = report.get("factor_effectiveness") or {}
    weight_recommendations = report.get("weight_recommendations") or {}
    model_health = report.get("model_health") or {}
    story.append(Paragraph("Factor Effectiveness Ranking", styles["RRTHeading"]))
    story.append(t(["Rank","Factor","Win Gap","Place Gap","Win Corr","Place Corr","Signal","Conf"], [[i.get('predictive_rank'),i.get('label'),i.get('winner_gap'),i.get('place_gap'),i.get('win_correlation'),i.get('place_correlation'),i.get('signal_strength'),i.get('confidence')] for i in (factor_effectiveness.get('factors') or [])[:12]]))
    story.append(Paragraph("Weight Recommendation Review", styles["RRTHeading"]))
    story.append(t(["Factor","Current","Rec.","Change","Direction","Priority"], [[i.get('label'),i.get('current_weight'),i.get('recommended_weight'),i.get('change'),i.get('direction'),i.get('priority')] for i in (weight_recommendations.get('recommendations') or [])[:12]]))
    health_readiness = model_health.get("readiness") or {}
    story.append(Paragraph("Model Health", styles["RRTHeading"]))
    story.append(t(["Metric","Value"], [["Readiness Score", health_readiness.get('score')],["Dataset Maturity", health_readiness.get('maturity')],["Best Factor", (model_health.get('best_factor') or {}).get('label')],["Weakest Factor", (model_health.get('weakest_factor') or {}).get('label')],["Next Action", model_health.get('recommended_next_action')]], [5*cm,11*cm]))
    story.append(Paragraph("Safety Statement", styles["RRTHeading"])); story.append(Paragraph(escape(str(report.get("safety_note"))), styles["BodyText"]))
    doc.build(story); buffer.seek(0); return buffer.getvalue()
