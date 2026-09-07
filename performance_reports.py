from typing import Any, Dict, List, Optional
from datetime import datetime
from html import escape
from io import BytesIO
import re

from database import fetch_all, fetch_one

from factor_analysis import get_factor_effectiveness_report, get_model_health_report, get_freshness_first_up_analysis, get_track_condition_audit
from adaptive_weight_recommendations import get_weight_recommendations
from simulator_engine import get_best_simulations, get_simulation_history, run_no_market_comparison
from selection_intelligence import get_latest_selection_analysis
from profile_cache_engine import get_historical_horse_leaderboard, get_strike_rate_leaderboard, get_profile_cache_summary


REPORT_VERSION = "2.22.2"
ANALYTICS_VERSION = "2.22.2"
DATABASE_SCHEMA_VERSION = "2.21.0"
MODEL_VERSION = "2.22.2"
LEARNING_VERSION = "2.22.2"




def _align_analysis_metadata(report: Dict[str, Any]) -> Dict[str, Any]:
    """Align nested legacy analysis metadata without changing calculations."""
    if not isinstance(report, dict):
        return report
    aligned = dict(report)
    aligned["analysis_version"] = REPORT_VERSION
    aligned["model_version"] = MODEL_VERSION
    aligned["analysis_only"] = True
    aligned["prediction_model_changed"] = False
    return aligned

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
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate,
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
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate
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


def get_best_worst_tracks_report(limit: int = 10, min_meetings: int = 3) -> Dict[str, Any]:
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
            HAVING COUNT(*) >= %s
            ORDER BY avg_overall_accuracy DESC, meeting_count DESC
            LIMIT %s;
            """,
            (min_meetings, limit),
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
            HAVING COUNT(*) >= %s
            ORDER BY avg_overall_accuracy ASC, meeting_count DESC
            LIMIT %s;
            """,
            (min_meetings, limit),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report_version": REPORT_VERSION,
            "report": "best_worst_tracks",
            "limit": limit,
            "min_meetings": min_meetings,
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
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate
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
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate,
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate
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
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate,
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
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate,
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
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate,
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
        "pf_ai_top_win": "Race Data AI Top Win",
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
                ROUND(AVG(trifecta_strike_rate), 2) AS avg_trifecta_strike_rate,
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
        "strong_tracks": fetch_all(_track_rollup_sql("ORDER BY avg_overall_accuracy DESC, meeting_count DESC", "HAVING COUNT(*) >= 3")),
        "review_tracks": fetch_all(_track_rollup_sql("ORDER BY avg_overall_accuracy ASC, meeting_count DESC", "HAVING COUNT(*) >= 3")),
        "reliable_tracks": fetch_all(_track_rollup_sql("ORDER BY avg_overall_accuracy DESC, meeting_count DESC", "HAVING COUNT(*) >= 3")),
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
            "area": "RRT vs Race Data AI",
            "metric_value": summary.get("avg_rrt_vs_pf_ai_gap"),
            "priority": "Maintain",
            "evidence": f"RRT is ahead of Race Data AI by {_pct(summary.get('avg_rrt_vs_pf_ai_gap'))}, with {h2h.get('rrt_wins')} RRT wins versus {h2h.get('pf_ai_wins')} Race Data AI wins.",
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
        actions.append({"priority": "High", "action": "Review top-win ranking precision", "reason": f"Top-win strike rate is {_pct(summary.get('avg_top_win_strike_rate'))}.", "next_step": "Compare top-win selections against Race Data AI, winner price bands, track condition, and field size once factor capture is available."})
    if _to_float(summary.get("avg_rrt_vs_pf_ai_gap")) > 0:
        actions.append({"priority": "Medium", "action": "Protect current RRT advantage over Race Data AI", "reason": f"RRT is currently ahead of PF AI by {_pct(summary.get('avg_rrt_vs_pf_ai_gap'))}.", "next_step": "Any future adaptive weighting should be tested against this baseline before production."})
    if base.get("ready_for_learning"):
        actions.append({"priority": "Medium", "action": "Review factor-capture dataset", "reason": "Dataset is large enough for learning analysis and v2.13.0 now automatically updates runner-level scoring factors after results are processed.", "next_step": "Collect completed meetings with factor rows and compare winning runners against each scoring component before recommending specific weight changes."})
    return actions



# ---------------------------------------------------------------------
# v2.19.5 Rolling Historical Performance Leaderboards — RRT Prediction Runs Only
# ---------------------------------------------------------------------

MIN_TRAINER_RUNNERS = 20
MIN_JOCKEY_RUNNERS = 20
MIN_COMBINATION_RUNNERS = 10
MIN_HORSE_RUNS = 2
HISTORICAL_HORSE_LIMIT = 20


def _rank_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"rank": index, **row} for index, row in enumerate(rows, start=1)]


def get_each_way_leaderboards(
    min_runners: int = MIN_TRAINER_RUNNERS,
    limit: int = 10,
) -> Dict[str, Any]:
    """Return win/place leaderboards from all completed runner-factor rows."""
    try:
        totals = fetch_one(
            """
            SELECT
                COUNT(*) AS runner_factor_rows,
                COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS completed_runner_rows,
                COUNT(*) FILTER (WHERE actual_position = 1) AS winner_rows,
                COUNT(*) FILTER (WHERE actual_position BETWEEN 1 AND 3) AS placed_rows,
                COUNT(DISTINCT meeting_id) FILTER (WHERE actual_position IS NOT NULL) AS meeting_count,
                COUNT(DISTINCT CONCAT(meeting_id::TEXT, '|', race_number::TEXT)) FILTER (WHERE actual_position IS NOT NULL) AS race_count,
                COUNT(DISTINCT track) FILTER (WHERE actual_position IS NOT NULL) AS track_count,
                COUNT(DISTINCT meeting_date) FILTER (WHERE actual_position IS NOT NULL) AS date_count,
                (SELECT COUNT(DISTINCT meeting_id) FROM rrt_performance_snapshots) AS prediction_meeting_count
            FROM rrt_runner_factor_snapshots;
            """
        ) or {}

        def entity_query(expression: str, alias: str, minimum: int, result_limit: Optional[int] = None):
            return fetch_all(
                f"""
                SELECT
                    {expression} AS {alias},
                    COUNT(*) AS runner_count,
                    SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END) AS win_count,
                    SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS place_count,
                    ROUND((SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS win_strike_rate,
                    ROUND((SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS place_strike_rate,
                    ROUND(AVG(final_score), 2) AS avg_final_score,
                    ROUND(AVG(confidence), 2) AS avg_confidence
                FROM rrt_runner_factor_snapshots
                WHERE actual_position IS NOT NULL
                  AND {expression} IS NOT NULL
                  AND UPPER({expression}) NOT IN ('N/A', 'UNKNOWN', 'NONE')
                GROUP BY {expression}
                HAVING COUNT(*) >= %s
                ORDER BY place_strike_rate DESC, win_strike_rate DESC, place_count DESC, win_count DESC, runner_count DESC, avg_final_score DESC
                LIMIT %s;
                """,
                (minimum, result_limit if result_limit is not None else limit),
            )

        trainer_expr = "NULLIF(TRIM(factor_json->>'trainer'), '')"
        jockey_expr = "NULLIF(TRIM(factor_json->>'jockey'), '')"
        horse_expr = "COALESCE(NULLIF(TRIM(runner_name), ''), NULLIF(TRIM(factor_json->>'horse_name'), ''), NULLIF(TRIM(factor_json->>'runner'), ''))"

        trainers = entity_query(trainer_expr, "trainer", max(int(min_runners), MIN_TRAINER_RUNNERS))
        jockeys = entity_query(jockey_expr, "jockey", max(int(min_runners), MIN_JOCKEY_RUNNERS))

        # Historical horse performance must be based on distinct actual race starts,
        # not on repeated model-version snapshots for the same horse and race.
        horses = fetch_all(
            f"""
            WITH completed_rows AS (
                SELECT
                    id,
                    meeting_id,
                    meeting_date,
                    race_id,
                    race_number,
                    runner_id,
                    tab_number,
                    updated_at,
                    created_at,
                    {horse_expr} AS horse,
                    {trainer_expr} AS trainer,
                    actual_position,
                    final_score,
                    confidence,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            meeting_id,
                            COALESCE(race_id::TEXT, race_number::TEXT, ''),
                            CASE
                                WHEN runner_id IS NOT NULL AND runner_id > 0
                                    THEN 'ID:' || runner_id::TEXT
                                ELSE 'NAME:' || UPPER(TRIM(COALESCE(
                                    {horse_expr},
                                    ''
                                ))) || '|TAB:' || COALESCE(tab_number::TEXT, '')
                            END
                        ORDER BY
                            updated_at DESC NULLS LAST,
                            created_at DESC NULLS LAST,
                            id DESC
                    ) AS start_snapshot_rank
                FROM rrt_runner_factor_snapshots
                WHERE actual_position IS NOT NULL
                  AND {horse_expr} IS NOT NULL
                  AND UPPER({horse_expr}) NOT IN ('N/A', 'UNKNOWN', 'NONE')
            ),
            distinct_starts AS (
                SELECT
                    meeting_id,
                    meeting_date,
                    race_id,
                    race_number,
                    runner_id,
                    tab_number,
                    horse,
                    trainer,
                    actual_position,
                    final_score,
                    confidence,
                    updated_at,
                    created_at
                FROM completed_rows
                WHERE start_snapshot_rank = 1
            ),
            horse_rollup AS (
                SELECT
                    COALESCE(
                        CASE
                            WHEN runner_id IS NOT NULL AND runner_id > 0
                                THEN 'ID:' || runner_id::TEXT
                            ELSE NULL
                        END,
                        'NAME:' || UPPER(TRIM(horse))
                    ) AS horse_key,
                    MAX(horse) AS horse,
                    COUNT(*) AS runner_count,
                    SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END) AS win_count,
                    SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS place_count,
                    ROUND(
                        (SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END)::NUMERIC
                        / NULLIF(COUNT(*), 0)) * 100,
                        2
                    ) AS win_strike_rate,
                    ROUND(
                        (SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END)::NUMERIC
                        / NULLIF(COUNT(*), 0)) * 100,
                        2
                    ) AS place_strike_rate,
                    ROUND(AVG(final_score), 2) AS avg_final_score,
                    ROUND(AVG(confidence), 2) AS avg_confidence
                FROM distinct_starts
                GROUP BY
                    COALESCE(
                        CASE
                            WHEN runner_id IS NOT NULL AND runner_id > 0
                                THEN 'ID:' || runner_id::TEXT
                            ELSE NULL
                        END,
                        'NAME:' || UPPER(TRIM(horse))
                    )
                HAVING COUNT(*) >= %s
            ),
            latest_trainer AS (
                SELECT DISTINCT ON (
                    COALESCE(
                        CASE
                            WHEN runner_id IS NOT NULL AND runner_id > 0
                                THEN 'ID:' || runner_id::TEXT
                            ELSE NULL
                        END,
                        'NAME:' || UPPER(TRIM(horse))
                    )
                )
                    COALESCE(
                        CASE
                            WHEN runner_id IS NOT NULL AND runner_id > 0
                                THEN 'ID:' || runner_id::TEXT
                            ELSE NULL
                        END,
                        'NAME:' || UPPER(TRIM(horse))
                    ) AS horse_key,
                    trainer
                FROM distinct_starts
                WHERE trainer IS NOT NULL
                  AND UPPER(trainer) NOT IN ('N/A', 'UNKNOWN', 'NONE')
                ORDER BY
                    COALESCE(
                        CASE
                            WHEN runner_id IS NOT NULL AND runner_id > 0
                                THEN 'ID:' || runner_id::TEXT
                            ELSE NULL
                        END,
                        'NAME:' || UPPER(TRIM(horse))
                    ),
                    meeting_date DESC NULLS LAST,
                    updated_at DESC NULLS LAST,
                    created_at DESC NULLS LAST
            )
            SELECT
                hr.horse,
                COALESCE(lt.trainer, 'Not recorded') AS trainer,
                hr.runner_count,
                hr.win_count,
                hr.place_count,
                hr.win_strike_rate,
                hr.place_strike_rate,
                hr.avg_final_score,
                hr.avg_confidence
            FROM horse_rollup hr
            LEFT JOIN latest_trainer lt
              ON lt.horse_key = hr.horse_key
            ORDER BY
                hr.place_strike_rate DESC,
                hr.win_strike_rate DESC,
                hr.place_count DESC,
                hr.win_count DESC,
                hr.runner_count DESC,
                hr.avg_final_score DESC,
                hr.horse ASC
            LIMIT %s;
            """,
            (MIN_HORSE_RUNS, HISTORICAL_HORSE_LIMIT),
        )
        for horse in horses:
            horse["evidence_status"] = "Established" if _to_int(horse.get("runner_count")) >= 5 else "Emerging"

        combinations = fetch_all(
            f"""
            SELECT
                CONCAT({trainer_expr}, ' / ', {jockey_expr}) AS trainer_jockey_combination,
                COUNT(*) AS runner_count,
                SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END) AS win_count,
                SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS place_count,
                ROUND((SUM(CASE WHEN actual_position = 1 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS win_strike_rate,
                ROUND((SUM(CASE WHEN actual_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS place_strike_rate,
                ROUND(AVG(final_score), 2) AS avg_final_score,
                ROUND(AVG(confidence), 2) AS avg_confidence
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL
              AND {trainer_expr} IS NOT NULL
              AND {jockey_expr} IS NOT NULL
              AND UPPER({trainer_expr}) NOT IN ('N/A', 'UNKNOWN', 'NONE')
              AND UPPER({jockey_expr}) NOT IN ('N/A', 'UNKNOWN', 'NONE')
            GROUP BY {trainer_expr}, {jockey_expr}
            HAVING COUNT(*) >= %s
            ORDER BY place_strike_rate DESC, win_strike_rate DESC, place_count DESC, win_count DESC, runner_count DESC, avg_final_score DESC
            LIMIT %s;
            """,
            (MIN_COMBINATION_RUNNERS, limit),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "report": "rolling_historical_performance_leaderboards",
            "leaderboard_version": REPORT_VERSION,
            "generated_at": _now_utc_iso(),
            "minimum_samples": {
                "trainers": max(int(min_runners), MIN_TRAINER_RUNNERS),
                "jockeys": max(int(min_runners), MIN_JOCKEY_RUNNERS),
                "trainer_jockey_combinations": MIN_COMBINATION_RUNNERS,
                "horses": MIN_HORSE_RUNS,
            },
            "limit": limit,
            "historical_horse_limit": HISTORICAL_HORSE_LIMIT,
            "ranking_method": "Trainer, jockey and combination leaderboards use completed runner-factor rows. Historical horses are deduplicated to one row per actual start before win/place rates are calculated.",
            "horse_ranking_note": "This is an aggregated historical horse leaderboard across distinct actual starts. Repeated model-version snapshots for the same meeting, race and runner are counted once. It is separate from the per-meeting Top 20 prediction ranking.",
            "dataset": totals,
            "top_trainers": _rank_rows(trainers),
            "top_jockeys": _rank_rows(jockeys),
            "top_trainer_jockey_combinations": _rank_rows(combinations),
            "top_horses": _rank_rows(horses),
            "note": "Meeting-level performance covers archived RRT prediction meetings. Runner-level leaderboards cover the subset where pre-race RRT runner-factor records and official finishing positions were both stored. This subset grows automatically through native full-field capture. Winners are position 1; places are positions 1-3.",
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report": "rolling_historical_performance_leaderboards",
            "leaderboard_version": REPORT_VERSION,
            "error": str(error),
        }


def _learning_track_condition_audit_from_factor_report(
    factor_effectiveness: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Lightweight Learning Report view of Track Condition.
    Reuses the factor-effectiveness result already calculated for this report,
    avoiding a second full 13-factor analysis pass.
    """
    try:
        track_factor = next(
            (
                item
                for item in (factor_effectiveness.get("factors") or [])
                if str(item.get("factor") or "").strip().lower() == "track_condition"
            ),
            {},
        )
        coverage = fetch_one(
            """
            SELECT
                COUNT(*) AS completed_rows,
                COUNT(track_condition_score) AS scored_rows,
                ROUND(
                    100.0 * COUNT(track_condition_score) / NULLIF(COUNT(*), 0),
                    2
                ) AS scored_pct,
                ROUND(AVG(track_condition_score), 2) AS avg_score,
                ROUND(STDDEV_POP(track_condition_score), 2) AS score_stddev
            FROM rrt_runner_factor_snapshots
            WHERE actual_position IS NOT NULL;
            """
        ) or {}
        return {
            "success": True,
            "analysis_version": REPORT_VERSION,
            "analysis": "track_condition_audit",
            "analysis_only": True,
            "production_model_changed": False,
            "coverage": coverage,
            "factor_effectiveness": track_factor,
            "interaction_logic_added": False,
            "note": (
                "Existing Track Condition measurement is audited as-is. "
                "The Learning Report reuses its already-calculated factor evidence "
                "and does not introduce interaction logic or a production-weight change."
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "analysis_version": REPORT_VERSION,
            "analysis": "track_condition_audit",
            "error": str(error),
        }


def _learning_model_health_from_factor_report(
    factor_effectiveness: Dict[str, Any],
    performance_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Lightweight Learning Report model-health view.
    Reuses the factor-effectiveness result already calculated for this request,
    avoiding another full factor-analysis pass.
    """
    try:
        dataset = factor_effectiveness.get("dataset") or {}
        factors = factor_effectiveness.get("factors") or []

        completed_rows = _to_int(dataset.get("completed_runner_rows"))
        winners = _to_int(dataset.get("winner_rows"))
        placed = _to_int(dataset.get("placed_rows"))
        tracks = _to_int(dataset.get("track_count"))
        dates = _to_int(dataset.get("date_count"))

        checks = {
            "completed_runner_rows": completed_rows >= 1000,
            "winner_rows": winners >= 80,
            "placed_rows": placed >= 250,
            "track_diversity": tracks >= 20,
            "date_diversity": dates >= 7,
        }
        score = round(
            (sum(1 for value in checks.values() if value) / len(checks)) * 100,
            1,
        )
        maturity = (
            "Mature" if score >= 90
            else "Developing" if score >= 60
            else "Early"
        )

        best_factor = factors[0] if factors else None
        weakest_factor = factors[-1] if factors else None

        if maturity == "Early":
            next_action = (
                "Continue collecting automated result updates before changing "
                "production weights. Use early factor rankings for monitoring only."
            )
        elif not best_factor:
            next_action = "Continue collecting factor data."
        elif maturity == "Developing":
            next_action = (
                f"Begin monitoring {best_factor.get('label')} as a candidate for "
                "future weighting review. Do not change production weights until "
                "the dataset reaches mature thresholds."
            )
        elif weakest_factor:
            next_action = (
                f"Review whether {best_factor.get('label')} should be strengthened "
                f"and {weakest_factor.get('label')} should be reduced in a simulator "
                "before production use."
            )
        else:
            next_action = "Dataset is mature enough for simulation-only weight testing."

        return {
            "success": True,
            "provider": "PostgreSQL",
            "analysis_version": REPORT_VERSION,
            "report": "model_health",
            "analysis_only": True,
            "prediction_model_changed": False,
            "model_version": MODEL_VERSION,
            "performance_summary": performance_summary or {},
            "learning_dataset": dataset,
            "readiness": {
                "score": score,
                "maturity": maturity,
                "checks": checks,
                "minimums": {
                    "completed_runner_rows": 1000,
                    "winner_rows": 80,
                    "placed_rows": 250,
                    "track_diversity": 20,
                    "date_diversity": 7,
                },
            },
            "best_factor": best_factor,
            "weakest_factor": weakest_factor,
            "recommended_next_action": next_action,
            "safety_note": (
                "Learning Report model health reuses the factor analysis already "
                "calculated for this request. Production weights can change only "
                "through an authorised Promotion Controller decision."
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "analysis_version": REPORT_VERSION,
            "report": "model_health",
            "error": str(error),
        }


def _learning_no_market_summary() -> Dict[str, Any]:
    """
    Read the latest completed No-Market historical comparison from PostgreSQL.

    The Learning Report never executes the full historical simulation itself.
    The dedicated /api/simulator/no-market-comparison endpoint performs the
    calculation and stores the result; HTML/PDF then read that saved result.
    """
    try:
        row = fetch_one(
            """
            SELECT simulation_json, created_at
            FROM rrt_weight_simulations
            WHERE simulation_group = 'v2.22.1 no-market-analysis'
            ORDER BY created_at DESC
            LIMIT 1;
            """
        ) or {}

        if not row:
            return {
                "success": True,
                "analysis_version": REPORT_VERSION,
                "analysis": "no_market_comparison",
                "analysis_only": True,
                "production_model_changed": False,
                "report_execution": "awaiting_saved_comparison",
                "endpoint": "/api/simulator/no-market-comparison",
                "saved_result_available": False,
                "note": (
                    "No saved No-Market comparison is available yet. Run the "
                    "dedicated No-Market endpoint once; the completed analysis "
                    "will then appear automatically in this Learning Report."
                ),
            }

        payload = row.get("simulation_json") or {}
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)

        current_model = payload.get("current_model") or {}
        no_market_model = payload.get("simulated_model") or {}
        current_metrics = current_model.get("metrics") or {}
        no_market_metrics = no_market_model.get("metrics") or {}
        improvement = payload.get("improvement") or {}
        current_weights = payload.get("current_weights") or {}
        no_market_weights = payload.get("test_weights") or {}
        dataset = payload.get("dataset") or {}
        recommendation = payload.get("recommendation") or {}

        return {
            "success": True,
            "analysis_version": REPORT_VERSION,
            "analysis": "no_market_comparison",
            "analysis_only": True,
            "production_model_changed": False,
            "market_removed": True,
            "report_execution": "latest_saved_dedicated_analysis",
            "endpoint": "/api/simulator/no-market-comparison",
            "saved_result_available": True,
            "saved_at": row.get("created_at"),
            "dataset": dataset,
            "current_weights": current_weights,
            "no_market_weights": no_market_weights,
            "current_metrics": current_metrics,
            "no_market_metrics": no_market_metrics,
            "difference": improvement,
            "recommendation": recommendation,
            "note": (
                "Latest saved analysis from the dedicated No-Market endpoint. "
                "Market is set to 0% and the remaining active production weights "
                "are proportionally normalised. Production weights are unchanged."
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "analysis_version": REPORT_VERSION,
            "analysis": "no_market_comparison",
            "error": str(error),
        }


def _no_market_performance_rows(payload: Dict[str, Any]) -> List[List[Any]]:
    current = payload.get("current_metrics") or {}
    no_market = payload.get("no_market_metrics") or {}
    difference = payload.get("difference") or {}
    metrics = [
        ("Top 1 Win", "top1_win_strike_rate"),
        ("Top 4 Winner Coverage", "top4_winner_coverage_rate"),
        ("Each-Way", "each_way_strike_rate"),
        ("Roughie E/Way", "roughie_strike_rate"),
        ("Overall Accuracy", "overall_accuracy"),
    ]
    return [
        [
            label,
            current.get(key),
            no_market.get(key),
            difference.get(key),
        ]
        for label, key in metrics
    ]


def _no_market_weight_rows(payload: Dict[str, Any]) -> List[List[Any]]:
    current = payload.get("current_weights") or {}
    no_market = payload.get("no_market_weights") or {}
    labels = {
        "last10": "Last 10 Form",
        "win_place": "Win / Place Record",
        "track_record": "Track Record",
        "distance_record": "Distance Record",
        "track_distance": "Track / Distance",
        "track_condition": "Track Condition",
        "trainer": "Trainer",
        "jockey": "Jockey",
        "trainer_jockey": "Trainer / Jockey",
        "barrier": "Barrier",
        "weight": "Weight Carried",
        "market": "Market",
        "speed": "Normalised Speed Rating",
    }
    order = [
        "last10", "win_place", "track_record", "distance_record",
        "track_distance", "track_condition", "trainer", "jockey",
        "trainer_jockey", "barrier", "weight", "market", "speed",
    ]
    return [
        [labels[key], current.get(key), no_market.get(key)]
        for key in order
    ]

def _learning_latest_selection_analysis_cached() -> Dict[str, Any]:
    """
    Return the latest stored Selection Intelligence analysis for reporting only.
    Unlike get_latest_selection_analysis(), this helper never regenerates the
    full Selection Intelligence dataset during an HTML/PDF request.
    """
    try:
        row = fetch_one(
            """
            SELECT analysis_json, generated_at
            FROM rrt_selection_analysis
            ORDER BY generated_at DESC
            LIMIT 1;
            """
        ) or {}

        analysis = row.get("analysis_json") or {}
        if isinstance(analysis, str):
            import json
            analysis = json.loads(analysis)

        if not row:
            return {
                "success": True,
                "provider": "PostgreSQL",
                "selection_intelligence_version": REPORT_VERSION,
                "report": "latest_selection_analysis_cached",
                "analysis": {},
                "generated_at": None,
                "report_execution": "cached_only",
                "note": (
                    "No stored Selection Intelligence analysis is currently available. "
                    "The Learning Report does not regenerate Selection Intelligence "
                    "during page generation."
                ),
            }

        return {
            "success": True,
            "provider": "PostgreSQL",
            "selection_intelligence_version": REPORT_VERSION,
            "report": "latest_selection_analysis_cached",
            "analysis": analysis,
            "generated_at": row.get("generated_at"),
            "report_execution": "cached_only",
            "note": (
                "Learning Report uses the latest stored Selection Intelligence result. "
                "It does not trigger a full Selection Intelligence regeneration."
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "selection_intelligence_version": REPORT_VERSION,
            "report": "latest_selection_analysis_cached",
            "error": str(error),
        }


def _learning_weight_recommendations_from_factor_report(
    factor_effectiveness: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the Learning Report weight-recommendation section from the
    factor-effectiveness result already calculated for this same request.

    This preserves the existing adaptive recommendation thresholds while
    eliminating:
      1) a second full get_factor_effectiveness_report() pass; and
      2) repeated active-weight database reads for every factor.
    """
    try:
        active_row = fetch_one(
            """
            SELECT weights_json
            FROM rrt_model_weight_sets
            WHERE status = 'Active'
            ORDER BY activated_at DESC NULLS LAST, created_at DESC
            LIMIT 1;
            """
        ) or {}

        default_weights = {
            "last10": 14.0,
            "win_place": 8.0,
            "track_record": 7.0,
            "distance_record": 7.0,
            "track_distance": 7.0,
            "track_condition": 7.0,
            "trainer": 6.0,
            "jockey": 6.0,
            "trainer_jockey": 8.0,
            "barrier": 4.0,
            "weight": 2.0,
            "market": 14.0,
            "speed": 10.0,
        }

        raw_weights = active_row.get("weights_json") or {}
        if isinstance(raw_weights, dict) and raw_weights:
            active_weights = {
                key: _to_float(raw_weights.get(key), value)
                for key, value in default_weights.items()
            }
        else:
            active_weights = dict(default_weights)

        dataset = factor_effectiveness.get("dataset") or {}
        dataset_confidence = dataset.get("confidence") or "Low"
        recommendations: List[Dict[str, Any]] = []

        for factor in factor_effectiveness.get("factors") or []:
            key = factor.get("factor")
            label = factor.get("label")
            current_weight = _to_float(active_weights.get(str(key)), 0.0)
            combined = _to_float(factor.get("combined_predictive_score"))
            winner_gap = _to_float(factor.get("winner_gap"))
            place_gap = _to_float(factor.get("place_gap"))
            sample_confidence = factor.get("confidence")

            if dataset_confidence in ["Low", "Early"] or sample_confidence == "Low":
                recommended_weight = current_weight
                direction = "Hold"
                priority = "Low"
                reason = "Dataset is not mature enough for a reliable weight change."
            elif combined >= 0.18 and winner_gap > 5 and place_gap > 3:
                recommended_weight = current_weight + 2.0
                direction = "Increase"
                priority = "High"
                reason = (
                    f"{label} has a strong positive relationship to both winners "
                    "and placegetters."
                )
            elif combined >= 0.10 and (winner_gap > 3 or place_gap > 2):
                recommended_weight = current_weight + 1.0
                direction = "Slight Increase"
                priority = "Medium"
                reason = (
                    f"{label} shows useful positive separation in the completed "
                    "runner dataset."
                )
            elif combined <= -0.08 and winner_gap < 0 and place_gap < 0:
                recommended_weight = max(0.0, current_weight - 2.0)
                direction = "Reduce"
                priority = "Medium"
                reason = (
                    f"{label} is not separating successful runners and may be "
                    "over-weighted."
                )
            elif abs(combined) < 0.05:
                recommended_weight = max(0.0, current_weight - 1.0)
                direction = "Monitor / Possible Reduction"
                priority = "Low"
                reason = (
                    f"{label} has a very weak observed relationship to outcomes."
                )
            else:
                recommended_weight = current_weight
                direction = "Hold"
                priority = "Medium"
                reason = (
                    f"{label} has an observable but not decisive outcome relationship."
                )

            recommendations.append(
                {
                    "factor": key,
                    "label": label,
                    "current_weight": current_weight,
                    "recommended_weight": round(recommended_weight, 2),
                    "change": round(recommended_weight - current_weight, 2),
                    "direction": direction,
                    "priority": priority,
                    "confidence": sample_confidence,
                    "signal_strength": factor.get("signal_strength"),
                    "combined_predictive_score": combined,
                    "winner_gap": winner_gap,
                    "place_gap": place_gap,
                    "reason": reason,
                }
            )

        increase = [item for item in recommendations if _to_float(item.get("change")) > 0]
        reduce = [item for item in recommendations if _to_float(item.get("change")) < 0]
        hold = [item for item in recommendations if _to_float(item.get("change")) == 0]
        net_change = round(
            sum(_to_float(item.get("change")) for item in recommendations),
            2,
        )

        return {
            "success": True,
            "provider": "RRT Predictor",
            "recommendation_version": REPORT_VERSION,
            "report": "weight_recommendations",
            "analysis_only": True,
            "prediction_model_changed": False,
            "dataset": dataset,
            "current_model_weights": active_weights,
            "recommendations": recommendations,
            "summary": {
                "dataset_confidence": dataset_confidence,
                "increase_candidates": len(increase),
                "reduction_candidates": len(reduce),
                "hold_candidates": len(hold),
                "net_recommended_weight_change": net_change,
                "top_increase_candidates": sorted(
                    increase,
                    key=lambda item: _to_float(item.get("change")),
                    reverse=True,
                )[:5],
                "top_reduction_candidates": sorted(
                    reduce,
                    key=lambda item: _to_float(item.get("change")),
                )[:5],
            },
            "report_execution": "reused_factor_effectiveness",
            "safety_note": (
                "Learning Report recommendations reuse the factor-effectiveness "
                "analysis already calculated for this request. Production weights "
                "are unchanged; only the Promotion Controller can authorise a "
                "production change."
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "RRT Predictor",
            "recommendation_version": REPORT_VERSION,
            "report": "weight_recommendations",
            "error": str(error),
        }


def get_learning_recommendations() -> Dict[str, Any]:
    try:
        from promotion_engine import get_promotion_status

        promotion_status = get_promotion_status()
        base = _learning_base()
        tracks = _learning_tracks()
        dates = _learning_dates()

        # One factor-effectiveness pass per report request.
        factor_effectiveness = _align_analysis_metadata(
            get_factor_effectiveness_report()
        )

        best_simulations = get_best_simulations(limit=10)
        speed_calibration = _extract_speed_calibration(
            factor_effectiveness,
            best_simulations,
        )
        weight_recommendations = _apply_speed_report_override(
            _learning_weight_recommendations_from_factor_report(
                factor_effectiveness
            ),
            speed_calibration,
        )

        # v2.22.1 HTML/PDF responsiveness:
        # Freshness is now validated and retained.
        # Track Condition and Model Health reuse the factor analysis already calculated.
        # The expensive No-Market simulation is deferred to its dedicated endpoint.
        freshness_first_up = _align_analysis_metadata(get_freshness_first_up_analysis())
        track_condition_audit = _learning_track_condition_audit_from_factor_report(
            factor_effectiveness
        )
        model_health = _learning_model_health_from_factor_report(
            factor_effectiveness,
            base.get("summary") or {},
        )
        no_market_comparison = _learning_no_market_summary()

        return {
            "success": True,
            "provider": "PostgreSQL",
            "learning_version": LEARNING_VERSION,
            "report": "learning_recommendations",
            "generated_at": _now_utc_iso(),
            "analysis_only": True,
            "prediction_model_changed": False,
            "automatic_weight_changes_enabled": bool(
                promotion_status.get("automatic_weight_changes_enabled")
            ),
            "promotion_mode": promotion_status.get("promotion_mode"),
            "database_schema_version": DATABASE_SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "learning_status": {
                "ready_for_learning": base.get("ready_for_learning"),
                "confidence": base.get("confidence"),
                "minimum_requirements": base.get("minimums"),
                "checks": base.get("checks"),
                "recommendation": _learning_recommendation(
                    base.get("confidence"),
                    bool(base.get("ready_for_learning")),
                ),
            },
            "dataset": base.get("summary"),
            "head_to_head": base.get("head_to_head"),
            "strengths": _learning_strengths(base, tracks, dates),
            "weaknesses": _learning_weaknesses(base, tracks, dates),
            "priority_action_plan": _learning_actions(base),
            "track_sets": tracks,
            "date_sets": dates,
            "each_way_leaderboards": get_each_way_leaderboards(),
            "profile_cache_summary": get_profile_cache_summary(),
            "historical_horses": get_historical_horse_leaderboard(
                limit=20,
                min_starts=5,
            ),
            "historical_trainers": get_strike_rate_leaderboard(
                "trainer",
                limit=20,
                min_starts=100,
                period="last100",
            ),
            "historical_jockeys": get_strike_rate_leaderboard(
                "jockey",
                limit=20,
                min_starts=100,
                period="last100",
            ),
            "factor_effectiveness": factor_effectiveness,
            "weight_recommendations": weight_recommendations,
            "freshness_first_up": freshness_first_up,
            "track_condition_audit": track_condition_audit,
            "no_market_comparison": no_market_comparison,
            "model_health": model_health,
            "simulation_history": get_simulation_history(limit=10),
            "best_simulations": best_simulations,
            "selection_intelligence": _learning_latest_selection_analysis_cached(),
            "speed_calibration": speed_calibration,
            "safety_note": (
                f"This v{REPORT_VERSION} report reflects the active PostgreSQL production "
                f"weight set, including Normalised Speed at 10%. Promotion Controller "
                f"mode is {promotion_status.get('promotion_mode')}. Recommendations "
                "do not directly change production weights; only an authorised "
                "Promotion Controller decision can apply a candidate."
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "learning_version": LEARNING_VERSION,
            "report": "learning_recommendations",
            "error": str(error),
        }

def _html_table(headers: List[str], rows: List[List[Any]]) -> str:
    th = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    trs = []
    for row in rows:
        trs.append("<tr>" + "".join(f"<td>{escape(str(c if c is not None else ''))}</td>" for c in row) + "</tr>")
    return "<table><thead><tr>" + th + "</tr></thead><tbody>" + "".join(trs) + "</tbody></table>"


def _html_audit_panels(dataset: Dict[str, Any]) -> str:
    coverage = [
        ("Meetings", dataset.get("meeting_count")),
        ("Races", dataset.get("race_count")),
        ("Tracks", dataset.get("unique_tracks")),
        ("Dates", dataset.get("unique_dates")),
    ]
    performance = [
        ("Overall", _pct(dataset.get("avg_overall_accuracy"))),
        ("Top Win", _pct(dataset.get("avg_top_win_strike_rate"))),
        ("Each Way", _pct(dataset.get("avg_each_way_strike_rate"))),
        ("Roughie E/W", _pct(dataset.get("avg_roughie_strike_rate"))),
        ("Double", _pct(dataset.get("avg_double_strike_rate"))),
        ("Quadrella", _pct(dataset.get("avg_quaddie_strike_rate"))),
        ("Trifecta", _pct(dataset.get("avg_trifecta_strike_rate")) if dataset.get("avg_trifecta_strike_rate") is not None else "Pending"),
    ]
    def panel(title: str, items: List[Any], css: str) -> str:
        cards = "".join(
            f'<div class="audit-card {css}"><div class="audit-label">{escape(str(label))}</div>'
            f'<div class="audit-value">{escape(str(value if value is not None else ""))}</div></div>'
            for label, value in items
        )
        return f'<div class="audit-panel"><h3>{escape(title)}</h3><div class="audit-grid">{cards}</div></div>'
    return '<div class="audit-wrap">' + panel("Dataset Coverage", coverage, "coverage") + panel("Prediction Performance", performance, "performance") + '</div>'


def _html_selection_depth(summary: Dict[str, Any]) -> str:
    depths = [
        ("Top 1", summary.get("top1_hit_rate"), None, "depth1"),
        ("Top 2", summary.get("top2_hit_rate"), None, "depth2"),
        ("Top 3", summary.get("top3_hit_rate"), None, "depth3"),
        ("Top 4", summary.get("top4_hit_rate"), summary.get("top4_incremental_gain_vs_top3"), "depth4"),
        ("Top 5", summary.get("top5_hit_rate"), summary.get("top5_incremental_gain_vs_top4"), "depth5"),
    ]
    rows = []
    previous = None
    for label, coverage, explicit_gain, css in depths:
        coverage_f = _to_float(coverage) if coverage is not None else None
        if explicit_gain is not None:
            gain = _to_float(explicit_gain)
        elif previous is None or coverage_f is None:
            gain = None
        else:
            gain = round(coverage_f - previous, 2)
        gain_text = "—" if gain is None else f"+{gain:.2f}%"
        cov_text = "Pending" if coverage_f is None else f"{coverage_f:.2f}%"
        emphasis = " <strong>Retail focus</strong>" if label == "Top 3" else ""
        rows.append(
            f'<tr class="{css}"><td><strong>{label}</strong>{emphasis}</td>'
            f'<td class="num"><strong>{cov_text}</strong></td><td class="num">{gain_text}</td></tr>'
        )
        if coverage_f is not None:
            previous = coverage_f
    return (
        '<table class="depth-table"><thead><tr><th>Selection Depth</th><th>Winner Coverage</th>'
        '<th>Incremental Gain</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
        f'<div class="depth-note"><strong>Top 3 vs Top 5:</strong> '
        f'{_pct(summary.get("top5_incremental_gain_vs_top3"))} additional winner coverage is gained by expanding from three to five selections. '
        f'Ranks 4-5 contributed {escape(str(summary.get("ranks4_5_incremental_winners") or 0))} additional winners in the analysed dataset.</div>'
    )


def _analysis_metric_rows(payload: Any, prefix: str = "", depth: int = 0) -> List[List[Any]]:
    """Flatten analysis-only response dictionaries for compact HTML display."""
    rows: List[List[Any]] = []
    if not isinstance(payload, dict):
        return rows
    for key, value in payload.items():
        label = f"{prefix}{key}".replace("_", " ").strip().title()
        if isinstance(value, dict) and depth < 2:
            rows.extend(_analysis_metric_rows(value, prefix=f"{label} — ", depth=depth + 1))
        elif isinstance(value, list):
            rows.append([label, f"{len(value)} records"])
        elif value is not None:
            rows.append([label, value])
    return rows


def _extract_speed_calibration(factor_effectiveness: Dict[str, Any], best_simulations: Dict[str, Any]) -> Dict[str, Any]:
    speed_factor = next((row for row in (factor_effectiveness.get("factors") or []) if str(row.get("factor") or "").strip().lower() == "speed"), {})
    speed_simulations = []
    for row in best_simulations.get("simulations") or []:
        simulation_name = str(row.get("simulation_name") or "")
        factor_tested = str(row.get("factor_tested") or "").strip().lower()
        if factor_tested != "speed" and "speed" not in simulation_name.lower():
            continue

        new_weight = row.get("new_weight")
        if new_weight is None:
            match = re.search(r"speed(?: rating)?\s*\+?(\d+(?:\.\d+)?)", simulation_name, re.IGNORECASE)
            if match:
                new_weight = _to_float(match.group(1))

        improvement = row.get("improvement_json") or {}
        recommendation = row.get("recommendation_json") or {}
        speed_simulations.append({
            "simulation_name": row.get("simulation_name"),
            "new_weight": new_weight,
            "overall_improvement": improvement.get("overall_accuracy") if improvement.get("overall_accuracy") is not None else row.get("overall_improvement"),
            "top_win_improvement": improvement.get("top_win_strike_rate") if improvement.get("top_win_strike_rate") is not None else row.get("top_win_improvement"),
            "each_way_improvement": improvement.get("each_way_strike_rate") if improvement.get("each_way_strike_rate") is not None else row.get("each_way_improvement"),
            "roughie_improvement": improvement.get("roughie_strike_rate") if improvement.get("roughie_strike_rate") is not None else row.get("roughie_improvement"),
            "status": recommendation.get("status") or row.get("status"),
        })
    speed_simulations.sort(key=lambda row: _to_float(row.get("overall_improvement"), -999.0), reverse=True)
    leading = speed_simulations[0] if speed_simulations else {}
    tested_weights = sorted({_to_float(row.get("new_weight")) for row in speed_simulations if row.get("new_weight") is not None})
    return {
        "predictive_rank": speed_factor.get("predictive_rank"),
        "runner_count": speed_factor.get("runner_count"),
        "win_correlation": speed_factor.get("win_correlation"),
        "place_correlation": speed_factor.get("place_correlation"),
        "combined_predictive_score": speed_factor.get("combined_predictive_score"),
        "signal_strength": speed_factor.get("signal_strength"),
        "confidence": speed_factor.get("confidence"),
        "production_weight": 10.0,
        "tested_range": f"{min(tested_weights):g}% to {max(tested_weights):g}%" if tested_weights else "Not available",
        "leading_candidate_weight": leading.get("new_weight"),
        "recommended_calibration_range": f"Active at 10%; continue monitoring new v{REPORT_VERSION} results",
        "production_status": "Active at 10% in the current production weight set; continue live out-of-sample monitoring.",
        "automatic_weight_changes_enabled": False,
        "simulations": speed_simulations,
    }

def _apply_speed_report_override(weight_recommendations: Dict[str, Any], speed_calibration: Dict[str, Any]) -> Dict[str, Any]:
    recommendations = list(weight_recommendations.get("recommendations") or [])
    updated = []
    for row in recommendations:
        item = dict(row)
        factor_key = str(item.get("factor") or item.get("label") or "").strip().lower()
        if factor_key in {"speed", "normalised speed rating", "normalized speed rating"}:
            item.update({
                "current_weight": 10.0,
                "recommended_weight": "Hold at 10%",
                "change": "0",
                "direction": "Production Monitoring",
                "priority": "High",
                "reason": f"Ranked #{speed_calibration.get('predictive_rank')} with a {speed_calibration.get('signal_strength')} signal and High confidence. The historically leading 10% simulator candidate is active in the current production weight set; hold and monitor new out-of-sample results.",
            })
        updated.append(item)
    return {**weight_recommendations, "recommendations": updated, "analysis_only": True, "prediction_model_changed": False, "automatic_weight_changes_enabled": False}


def get_speed_rating_report() -> Dict[str, Any]:
    try:
        totals=fetch_one("""SELECT COUNT(*) AS history_rows,COUNT(DISTINCT runner_id) AS runner_count,COUNT(DISTINCT meeting_id) AS meeting_count,
            ROUND(AVG(normalised_speed_score),2) AS avg_speed_score,MIN(meeting_date) AS first_date,MAX(meeting_date) AS latest_date FROM rrt_runner_speed_history;""") or {}
        outcome=fetch_one("""SELECT ROUND(AVG(speed_score) FILTER(WHERE actual_position=1),2) AS winner_average,
            ROUND(AVG(speed_score) FILTER(WHERE actual_position BETWEEN 1 AND 3),2) AS placed_average,
            ROUND(AVG(speed_score) FILTER(WHERE actual_position>3),2) AS unplaced_average,COUNT(*) FILTER(WHERE speed_score IS NOT NULL) AS analysed_rows
            FROM rrt_runner_factor_snapshots WHERE actual_position IS NOT NULL;""") or {}
        return {"success":True,"speed_version":REPORT_VERSION,"analysis_only":True,"totals":totals,"outcome":outcome,"in_run_used":False}
    except Exception as e: return {"success":False,"speed_version":REPORT_VERSION,"error":str(e)}


def generate_learning_report_html() -> str:
    report = get_learning_recommendations()
    if not report.get("success"):
        return "<html><body><h1>RRT Predictor Learning Report</h1><pre>" + escape(str(report)) + "</pre></body></html>"
    dataset = report.get("dataset") or {}
    status = report.get("learning_status") or {}
    h2h = report.get("head_to_head") or {}
    tracks = report.get("track_sets") or {}
    dates = report.get("date_sets") or {}

    # get_latest_selection_analysis() can return either a saved-analysis wrapper
    # or a freshly regenerated analysis. Normalise both shapes for HTML only.
    selection_response = report.get("selection_intelligence") or {}
    selection_analysis = selection_response.get("analysis") or selection_response
    selection_summary = selection_analysis.get("summary") or {}
    selection_recommendations = selection_analysis.get("recommendations") or []

    ready = "READY" if status.get("ready_for_learning") else "NOT READY"
    def card(label: str, value: Any) -> str:
        return f'<div class="card"><div class="label">{escape(label)}</div><div class="value">{escape(str(value))}</div></div>'
    html = [
        '<!doctype html><html><head><meta charset="utf-8"><title>RRT Predictor Learning Report</title>',
        '<style>body{font-family:Arial,Helvetica,sans-serif;margin:32px;color:#1f2933}h1,h2{color:#0f2f57}h2{border-bottom:2px solid #0f2f57;padding-bottom:6px;margin-top:30px}.subtitle{color:#52606d}.badge{display:inline-block;padding:8px 14px;border-radius:6px;background:#e3fcec;color:#014d40;font-weight:bold;margin-right:8px}.warning{background:#fffbea;color:#8d2b0b}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.card{border:1px solid #d9e2ec;border-radius:8px;padding:14px;background:#f8fafc}.label{color:#627d98;font-size:12px;text-transform:uppercase}.value{font-size:22px;font-weight:bold;color:#102a43}table{width:100%;border-collapse:collapse;margin:14px 0 22px 0;font-size:13px}th{background:#0f2f57;color:white;text-align:left;padding:8px}td{border:1px solid #d9e2ec;padding:8px;vertical-align:top}tr:nth-child(even){background:#f8fafc}.note{background:#f0f4f8;border-left:5px solid #0f2f57;padding:12px 14px;margin-top:20px}.audit-wrap{display:grid;grid-template-columns:1fr 2fr;gap:14px;margin:14px 0 20px}.audit-panel{border:1px solid #d9e2ec;border-radius:8px;padding:12px;background:#f8fafc}.audit-panel h3{margin:0 0 10px;color:#0f2f57}.audit-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.audit-panel:nth-child(2) .audit-grid{grid-template-columns:repeat(4,1fr)}.audit-card{border-radius:6px;padding:10px;border:1px solid #cbd5e1}.audit-card.coverage{background:#eaf2ff}.audit-card.performance{background:#edf9f0}.audit-label{font-size:11px;color:#52606d;text-transform:uppercase}.audit-value{font-size:19px;font-weight:bold;color:#102a43;margin-top:3px}.depth-table td.num{text-align:right}.depth-table tr.depth1{background:#f4f6f8}.depth-table tr.depth2{background:#edf4fb}.depth-table tr.depth3{background:#dff3e4}.depth-table tr.depth4{background:#fff4d6}.depth-table tr.depth5{background:#fde8e8}.depth-note{background:#eef6ff;border-left:5px solid #2474b5;padding:11px 13px;margin:-8px 0 20px}.footer{margin-top:40px;font-size:12px;color:#627d98;border-top:1px solid #d9e2ec;padding-top:12px}@media(max-width:900px){.audit-wrap{grid-template-columns:1fr}.audit-panel:nth-child(2) .audit-grid{grid-template-columns:repeat(2,1fr)}}@media print{.no-print{display:none}table{page-break-inside:avoid}.audit-wrap{grid-template-columns:1fr 2fr}}</style></head><body>',
        '<div class="no-print"><button onclick="window.print()">Print / Save as PDF</button></div>',
        f'<h1>RRT Predictor Learning Report</h1><p class="subtitle">Version {LEARNING_VERSION} | Generated {escape(report.get("generated_at") or "")}</p>',
        f'<span class="badge">{ready}</span><span class="badge">Confidence: {escape(str(status.get("confidence")))}</span><span class="badge warning">Adaptive Control: {escape(str(report.get("promotion_mode") or "unknown").upper())} | Automatic Weight Changes: {"ENABLED" if report.get("automatic_weight_changes_enabled") else "DISABLED"}</span>',
        '<h2>Dataset Audit</h2>',
        _html_audit_panels(dataset),
        '<div class="note"><strong>Selection-depth comparison:</strong> Top 3 / Top 4 / Top 5 winner coverage is shown in the Selection Intelligence section below. Dataset Audit remains focused on compact production and dataset health metrics.</div>',
        '<div class="note"><strong>Trifecta:</strong> v2.22.2 stores the selected five-runner box result. A hit requires all official first three finishers to be contained in the box.</div>',
        f'<div class="note"><strong>Learning Recommendation:</strong> {escape(str(status.get("recommendation")))}</div>',
        '<h2>Current Model Performance</h2>',
        _html_table(['Metric','Value'], [['Readiness Score', ((report.get('model_health') or {}).get('readiness') or {}).get('score')], ['Dataset Maturity', ((report.get('model_health') or {}).get('readiness') or {}).get('maturity')], ['Next Action', (report.get('model_health') or {}).get('recommended_next_action')]]),
        '<h2>Strengths</h2>', _html_table(['Area','Priority','Metric','Evidence'], [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('strengths') or []]),
        '<h2>Weaknesses</h2>', _html_table(['Area','Priority','Metric','Evidence'], [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('weaknesses') or []]),
        '<h2>Priority Action Plan</h2>', _html_table(['Priority','Action','Reason','Next Step'], [[i.get('priority'),i.get('action'),i.get('reason'),i.get('next_step')] for i in report.get('priority_action_plan') or []]),
        '<h2>Strongest Tracks*</h2><div class="note">Track tables require at least 3 recorded RRT prediction meetings per track.</div>', _html_table(['Track','Meetings','Races','Accuracy','RRT v Race Data AI'], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('strong_tracks') or [])[:10]]),
        '<h2>Weakest Tracks*</h2>', _html_table(['Track','Meetings','Races','Accuracy','RRT v Race Data AI'], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('review_tracks') or [])[:10]]),
        '<h2>Recent Daily Performance</h2>', _html_table(['Date','Meetings','Races','Accuracy','RRT v Race Data AI'], [[i.get('meeting_date'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (dates.get('recent_days') or [])[:10]]),
        '<h2>Rolling Historical Performance Leaderboards — RRT Prediction Runs Only</h2>',
        '<div class="note">Meeting-level performance covers archived RRT prediction meetings. Runner-level leaderboards cover the subset where pre-race RRT runner-factor records and official finishing positions were both stored. This subset grows automatically through native full-field capture.</div>',
        _html_table(['Coverage Metric','Value'], [['Archived Prediction Meetings', ((report.get('each_way_leaderboards') or {}).get('dataset') or {}).get('prediction_meeting_count')], ['Runner-Factor Meetings', ((report.get('each_way_leaderboards') or {}).get('dataset') or {}).get('meeting_count')], ['Completed Runner Rows', ((report.get('each_way_leaderboards') or {}).get('dataset') or {}).get('completed_runner_rows')], ['Completed Runner-Factor Races', ((report.get('each_way_leaderboards') or {}).get('dataset') or {}).get('race_count')], ['Unique Tracks', ((report.get('each_way_leaderboards') or {}).get('dataset') or {}).get('track_count')], ['Unique Racing Dates', ((report.get('each_way_leaderboards') or {}).get('dataset') or {}).get('date_count')]]),
        '<h3>Top 10 Trainers*</h3>', _html_table(['Rank','Trainer','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('trainer'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_trainers') or [])[:10]]),
        '<h3>Top 10 Jockeys*</h3>', _html_table(['Rank','Jockey','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('jockey'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_jockeys') or [])[:10]]),
        '<h3>Top 10 Trainer / Jockey Combinations*</h3>', _html_table(['Rank','Combination','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_trainer_jockey_combinations') or [])[:10]]),
        '<div class="note">* Based on completed RRT prediction history only. Track performance is derived from stored RRT meeting performance records. Trainer, jockey and trainer/jockey leaderboards are derived from completed RRT runner-factor records matched to official race results. These are not all-career or whole-of-market historical statistics.</div>',
        '<h3>Top 20 Historical Horse Performance</h3>',
        '<div class="note">Aggregated historical performance across distinct actual race starts. Repeated model-version snapshots for the same horse and race are counted once. The Trainer shown is from the latest completed recorded start. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.</div>',
        (_html_table(['Rank','Horse','Trainer','Status','Runs','Wins','Places','Win %','Place %','Avg Score','Avg Confidence'], [[i.get('rank'),i.get('horse'),i.get('trainer'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in ((report.get('each_way_leaderboards') or {}).get('top_horses') or [])[:20]]) if ((report.get('each_way_leaderboards') or {}).get('top_horses') or []) else '<div class="note">Insufficient historical horse performance data available. A minimum of two distinct completed starts is required before inclusion.</div>'),
        '<h2>Historical Profile Intelligence — Race Data Source</h2>',
        '<div class="note">Independent of RRT Predictions. Historical horse, trainer and jockey profiles are sourced from the connected Race Data Source. RRT-observed leaderboards remain available separately.</div>',
        '<h3>Top 20 Historical Horse Performance</h3>', (_html_table(['Rank','Horse','Trainer','Starts','Wins','Places','Win %','Place %','Last 10'], [[i.get('rank'),i.get('horse'),i.get('trainer'),i.get('starts'),i.get('wins'),i.get('places'),_pct(i.get('win_pct')),_pct(i.get('place_pct')),i.get('last10')] for i in ((report.get('historical_horses') or {}).get('horses') or [])]) if ((report.get('historical_horses') or {}).get('horses') or []) else '<div class="note">No Race Data Source horse profiles cached yet. Run /api/profiles/refresh-meeting.</div>'),
        '<h3>Top 20 Trainer Strike Rate — Last 100</h3>', (_html_table(['Rank','Trainer','Starts','Wins','Places','Win %','Place %','P/L'], [[i.get('rank'),i.get('entity_name'),i.get('starts'),i.get('wins'),i.get('places'),_pct(i.get('win_pct')),_pct(i.get('place_pct')),i.get('last100_pl')] for i in ((report.get('historical_trainers') or {}).get('profiles') or [])]) if ((report.get('historical_trainers') or {}).get('profiles') or []) else '<div class="note">No trainer strike-rate profiles cached yet.</div>'),
        '<h3>Top 20 Jockey Strike Rate — Last 100</h3>', (_html_table(['Rank','Jockey','Starts','Wins','Places','Win %','Place %','P/L'], [[i.get('rank'),i.get('entity_name'),i.get('starts'),i.get('wins'),i.get('places'),_pct(i.get('win_pct')),_pct(i.get('place_pct')),i.get('last100_pl')] for i in ((report.get('historical_jockeys') or {}).get('profiles') or [])]) if ((report.get('historical_jockeys') or {}).get('profiles') or []) else '<div class="note">No jockey strike-rate profiles cached yet.</div>'),
        '<h2>Evidence-Based Factor Analysis</h2>',
        '<div class="note">This section compares completed runner factor scores against actual results. It reports against the active PostgreSQL production weight set. Proposed changes do not alter production directly; they are evaluated and may be applied only through the current Promotion Controller when its configured gates and operating mode authorise promotion.</div>',
        '<h3>Factor Effectiveness Ranking</h3>',
        _html_table(['Rank','Factor','Winner Gap','Place Gap','Win Corr','Place Corr','Signal','Confidence','Recommendation'], [[i.get('predictive_rank'),i.get('label'),i.get('winner_gap'),i.get('place_gap'),i.get('win_correlation'),i.get('place_correlation'),i.get('signal_strength'),i.get('confidence'),(i.get('recommendation') or {}).get('direction')] for i in ((report.get('factor_effectiveness') or {}).get('factors') or [])[:13]]),
        '<h3>Future Adaptive Weight Proposals</h3>',
        _html_table(['Factor','Current','Recommended','Change','Direction','Priority','Reason'], [[i.get('label'),i.get('current_weight'),i.get('recommended_weight'),i.get('change'),i.get('direction'),i.get('priority'),i.get('reason')] for i in ((report.get('weight_recommendations') or {}).get('recommendations') or [])[:13]]),
        '<h3>Model Health</h3>',
        _html_table(['Metric','Value'], [['Readiness Score', ((report.get('model_health') or {}).get('readiness') or {}).get('score')], ['Dataset Maturity', ((report.get('model_health') or {}).get('readiness') or {}).get('maturity')], ['Next Action', (report.get('model_health') or {}).get('recommended_next_action')]]),
        '<h2>Freshness / First-Up Analysis</h2>',
        '<div class="note">Analysis-only evidence. Freshness / first-up information is currently monitored at 0% production weight and cannot directly alter production predictions.</div>',
        _html_table(['Metric','Value'], _analysis_metric_rows(report.get('freshness_first_up') or {})),
        '<h2>Track Condition Audit</h2>',
        '<div class="note">Audit of the existing Track Condition factor against completed runner outcomes. This section does not alter the current Track Condition production weight.</div>',
        _html_table(['Metric','Value'], _analysis_metric_rows(report.get('track_condition_audit') or {})),
        '<h2>No-Market Historical Comparison</h2>',
        '<div class="note">Analysis-only comparison using the latest saved result from /api/simulator/no-market-comparison. Market is removed and the remaining active weights are proportionally normalised. The Learning Report reads the saved result only and does not re-run the historical simulation. Production weights are unchanged.</div>',
        _html_table(
            ['Metric','Current Model %','No-Market %','Difference'],
            _no_market_performance_rows(report.get('no_market_comparison') or {})
        ) if (report.get('no_market_comparison') or {}).get('saved_result_available') else _html_table(
            ['Metric','Value'],
            _analysis_metric_rows(report.get('no_market_comparison') or {})
        ),
        '<h3>No-Market Weight Normalisation</h3>' if (report.get('no_market_comparison') or {}).get('saved_result_available') else '',
        _html_table(
            ['Factor','Current Production %','No-Market Test %'],
            _no_market_weight_rows(report.get('no_market_comparison') or {})
        ) if (report.get('no_market_comparison') or {}).get('saved_result_available') else '',
        '<h2>Historical Weight Simulation</h2>',
        '<div class="note">Historical simulations compare alternative weights and roughie rules against stored completed runner data without changing production weights.</div>',
        _html_table(['Simulation','Factor','Old','New','Change','Runners','Races','Overall +/-','Top Win +/-','Each Way +/-','Roughie +/-','Status'], [[i.get('simulation_name'),i.get('factor_tested'),i.get('old_weight'),i.get('new_weight'),i.get('change_amount'),i.get('dataset_runner_count'),i.get('dataset_race_count'),(i.get('improvement_json') or {}).get('overall_accuracy') or i.get('overall_improvement'),(i.get('improvement_json') or {}).get('top_win_strike_rate') or i.get('top_win_improvement'),(i.get('improvement_json') or {}).get('each_way_strike_rate') or i.get('each_way_improvement'),(i.get('improvement_json') or {}).get('roughie_strike_rate') or i.get('roughie_improvement'),(i.get('recommendation_json') or {}).get('status')] for i in ((report.get('best_simulations') or {}).get('simulations') or [])[:10]]),
        '<h2>Selection Intelligence</h2>',
        '<div class="note">Selection Intelligence v2.22.2 analyses completed native full-field races across Top 1 to Top 5 selection depth, Top 3 versus Top 5 incremental coverage, boundary misses, value/roughie winners, false positives and factor gaps. Its evidence remains analysis-only and feeds the controlled promotion gate.</div>',
        _html_selection_depth(selection_summary),
        _html_table(['Metric','Value'], [
            ['Near Miss Rate', selection_summary.get('near_miss_rate')],
            ['Boundary Miss Rate', selection_summary.get('boundary_miss_rate')],
            ['Roughie-like Winner Rate', selection_summary.get('roughie_like_winner_rate')],
            ['Average False Positives / Race', selection_summary.get('avg_false_positives_per_race')]
        ]),
        _html_table(['Priority','Area','Recommendation','Evidence'], [
            [i.get('priority'), i.get('area'), i.get('recommendation'), i.get('evidence')]
            for i in selection_recommendations[:8]
        ]),
        '<h2>Normalised Speed Rating</h2>',
        '<p>Official race time, distance and beaten margin are used to create a rolling pre-race Speed Rating. Sectionals and in-run positions are not used. Corrected factor-analysis, simulator and selection-intelligence evidence is now available; production weight remains active at 10% in the current production weight set while live monitoring continues.</p>',
        _html_table(['Metric','Value'], [
            ['Predictive Rank', f"#{(report.get('speed_calibration') or {}).get('predictive_rank')}"],
            ['Signal / Confidence', f"{(report.get('speed_calibration') or {}).get('signal_strength')} / {(report.get('speed_calibration') or {}).get('confidence')}"],
            ['Win Correlation', (report.get('speed_calibration') or {}).get('win_correlation')],
            ['Place Correlation', (report.get('speed_calibration') or {}).get('place_correlation')],
            ['Combined Predictive Score', (report.get('speed_calibration') or {}).get('combined_predictive_score')],
            ['Analysed Runner Rows', (report.get('speed_calibration') or {}).get('runner_count')],
            ['Current Production Weight', '10%'],
            ['Simulator Range Tested', (report.get('speed_calibration') or {}).get('tested_range')],
            ['Leading Simulator Candidate', f"{(report.get('speed_calibration') or {}).get('leading_candidate_weight')}%"],
            ['Recommended Calibration Range', (report.get('speed_calibration') or {}).get('recommended_calibration_range')],
            ['Production Status', (report.get('speed_calibration') or {}).get('production_status')],
            ['Automatic Weight Changes', 'Enabled' if report.get('automatic_weight_changes_enabled') else 'Disabled'],
            ['Promotion Controller Mode', str(report.get('promotion_mode') or 'unknown').upper()],
        ]),
        '<h3>Speed Calibration Simulations</h3>',
        _html_table(['Simulation','New Weight','Overall +/-','Top Win +/-','Each Way +/-','Roughie +/-','Status'], [[i.get('simulation_name'),i.get('new_weight'),i.get('overall_improvement'),i.get('top_win_improvement'),i.get('each_way_improvement'),i.get('roughie_improvement'),i.get('status')] for i in ((report.get('speed_calibration') or {}).get('simulations') or [])[:5]]),
        f'<h2>Safety Statement</h2><div class="note">{escape(str(report.get("safety_note")))}</div>',
        f'<div class="footer">RRT Predictor | Backend {REPORT_VERSION} | Model {MODEL_VERSION} | Database Schema {DATABASE_SCHEMA_VERSION} | Generated {escape(report.get("generated_at") or "")}</div>',
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
    story.append(Paragraph(f"Status: {'READY' if status.get('ready_for_learning') else 'NOT READY'} | Confidence: {status.get('confidence')} | Adaptive Control: {'live promotion authorised' if report.get('automatic_weight_changes_enabled') else 'shadow evaluation only'}", styles["BodyText"]))
    story.append(Paragraph("Dataset Audit", styles["RRTHeading"]))
    story.append(t(["Metric","Value"], [
        ["Meetings analysed",dataset.get('meeting_count')],
        ["Races analysed",dataset.get('race_count')],
        ["Unique tracks",dataset.get('unique_tracks')],
        ["Unique dates",dataset.get('unique_dates')],
        ["Overall Accuracy",_pct(dataset.get('avg_overall_accuracy'))],
        ["Top Win",_pct(dataset.get('avg_top_win_strike_rate'))],
        ["Each Way",_pct(dataset.get('avg_each_way_strike_rate'))],
        ["Roughie E/Way",_pct(dataset.get('avg_roughie_strike_rate'))],
        ["Double",_pct(dataset.get('avg_double_strike_rate'))],
        ["Quadrella",_pct(dataset.get('avg_quaddie_strike_rate'))],
        ["Trifecta",_pct(dataset.get("avg_trifecta_strike_rate")) if dataset.get("avg_trifecta_strike_rate") is not None else "Pending history"],
        ["RRT v Race Data AI",_pct(dataset.get('avg_rrt_vs_pf_ai_gap'))],
        ["Date range",f"{dataset.get('first_meeting_date')} to {dataset.get('latest_meeting_date')}"],
        ["Database schema",DATABASE_SCHEMA_VERSION],
        ["Prediction model",MODEL_VERSION]
    ], [7*cm,9*cm]))
    story.append(Paragraph("Trifecta v2.22.2 result history is stored at meeting level. A hit requires all official first three finishers to be contained in the selected five-runner box.", styles["BodyText"]))
    story.append(Paragraph("Learning Recommendation", styles["RRTHeading"])); story.append(Paragraph(escape(str(status.get("recommendation"))), styles["BodyText"]))
    story.append(Paragraph("Current Model Performance", styles["RRTHeading"]))
    story.append(t(["Metric","Value"], [["Overall Accuracy",_pct(dataset.get('avg_overall_accuracy'))],["Top Win",_pct(dataset.get('avg_top_win_strike_rate'))],["Each Way",_pct(dataset.get('avg_each_way_strike_rate'))],["Roughie E/Way",_pct(dataset.get('avg_roughie_strike_rate'))],["Double",_pct(dataset.get('avg_double_strike_rate'))],["Quadrella",_pct(dataset.get('avg_quaddie_strike_rate'))],["Race Data AI Top Win",_pct(dataset.get('avg_pf_ai_top_win_strike_rate'))],["RRT Advantage",_pct(dataset.get('avg_rrt_vs_pf_ai_gap'))],["RRT / Race Data AI / Ties",f"{h2h.get('rrt_wins')} / {h2h.get('pf_ai_wins')} / {h2h.get('ties')}"]], [7*cm,9*cm]))
    for title, rows in [("Strengths", [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('strengths') or []]), ("Weaknesses", [[i.get('area'),i.get('priority'),_pct(i.get('metric_value')) if i.get('metric_value') is not None else '',i.get('evidence')] for i in report.get('weaknesses') or []])]:
        story.append(Paragraph(title, styles["RRTHeading"])); story.append(t(["Area","Priority","Metric","Evidence"], rows, [3.5*cm,2.2*cm,2.2*cm,8.5*cm]))
    story.append(PageBreak())
    story.append(Paragraph("Priority Action Plan", styles["RRTHeading"])); story.append(t(["Priority","Action","Reason","Next Step"], [[i.get('priority'),i.get('action'),i.get('reason'),i.get('next_step')] for i in report.get('priority_action_plan') or []], [2.2*cm,3.8*cm,5*cm,5.6*cm]))
    story.append(Paragraph("Strongest Tracks*", styles["RRTHeading"])); story.append(t(["Track","Meetings","Races","Accuracy","RRT v Race Data AI"], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('strong_tracks') or [])[:10]]))
    story.append(Paragraph("Weakest Tracks*", styles["RRTHeading"])); story.append(t(["Track","Meetings","Races","Accuracy","RRT v Race Data AI"], [[i.get('track'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (tracks.get('review_tracks') or [])[:10]]))
    story.append(Paragraph("Recent Daily Performance", styles["RRTHeading"])); story.append(t(["Date","Meetings","Races","Accuracy","RRT v Race Data AI"], [[i.get('meeting_date'),i.get('meeting_count'),i.get('race_count'),_pct(i.get('avg_overall_accuracy')),_pct(i.get('avg_rrt_vs_pf_ai_gap'))] for i in (dates.get('recent_days') or [])[:10]]))

    leaderboards = report.get("each_way_leaderboards") or {}
    story.append(PageBreak())
    story.append(Paragraph("Rolling Historical Performance Leaderboards — RRT Prediction Runs Only", styles["RRTHeading"]))
    story.append(Paragraph("Meeting-level performance covers archived RRT prediction meetings. Runner-level leaderboards cover the subset where pre-race RRT runner-factor records and official finishing positions were both stored. This subset grows automatically through native full-field capture.", styles["BodyText"]))
    leaderboard_dataset = leaderboards.get("dataset") or {}
    story.append(t(["Coverage Metric","Value"], [["Archived Prediction Meetings", leaderboard_dataset.get("prediction_meeting_count")], ["Runner-Factor Meetings", leaderboard_dataset.get("meeting_count")], ["Completed Runner Rows", leaderboard_dataset.get("completed_runner_rows")], ["Completed Runner-Factor Races", leaderboard_dataset.get("race_count")], ["Unique Tracks", leaderboard_dataset.get("track_count")], ["Unique Racing Dates", leaderboard_dataset.get("date_count")]]))
    story.append(Paragraph("Top 10 Trainers*", styles["RRTHeading"]))
    story.append(t(["Rank","Trainer","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('trainer'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_trainers') or [])[:10]]))
    story.append(Paragraph("Top 10 Jockeys*", styles["RRTHeading"]))
    story.append(t(["Rank","Jockey","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('jockey'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_jockeys') or [])[:10]]))
    story.append(Paragraph("Top 10 Trainer / Jockey Combinations*", styles["RRTHeading"]))
    story.append(t(["Rank","Combination","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"], [[i.get('rank'),i.get('trainer_jockey_combination'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_trainer_jockey_combinations') or [])[:10]]))
    story.append(Paragraph("* Based on completed RRT prediction history only. Track performance is derived from stored RRT meeting performance records. Trainer, jockey and trainer/jockey leaderboards are derived from completed RRT runner-factor records matched to official race results. These are not all-career or whole-of-market historical statistics.", styles["BodyText"]))
    story.append(Paragraph("Top 20 Historical Horse Performance", styles["RRTHeading"]))
    story.append(Paragraph("Aggregated historical performance across distinct actual race starts. Repeated model-version snapshots for the same horse and race are counted once. The Trainer shown is from the latest completed recorded start. This table is separate from the per-meeting Top 20 prediction ranking. Emerging = 2-4 completed runs; Established = 5 or more completed runs.", styles["BodyText"]))
    if leaderboards.get('top_horses'):
        story.append(t(
            ["Rank","Horse","Trainer","Status","Runs","Wins","Places","Win %","Place %","Avg Score","Avg Conf"],
            [[i.get('rank'),i.get('horse'),i.get('trainer'),i.get('evidence_status'),i.get('runner_count'),i.get('win_count'),i.get('place_count'),_pct(i.get('win_strike_rate')),_pct(i.get('place_strike_rate')),i.get('avg_final_score'),i.get('avg_confidence')] for i in (leaderboards.get('top_horses') or [])[:20]],
            [0.7*cm, 2.6*cm, 2.8*cm, 1.6*cm, 0.8*cm, 0.8*cm, 0.9*cm, 1.1*cm, 1.1*cm, 1.3*cm, 1.3*cm],
        ))
    else:
        story.append(Paragraph("Insufficient historical horse performance data available. A minimum of two distinct completed starts is required before inclusion.", styles["BodyText"]))
    story.append(PageBreak())
    story.append(Paragraph("Historical Profile Intelligence — Race Data Source", styles["RRTHeading"]))
    story.append(Paragraph("Independent of RRT Predictions. Historical horse, trainer and jockey profiles are sourced from the connected Race Data Source.", styles["BodyText"]))
    if (report.get("historical_horses") or {}).get("horses"):
        story.append(t(["Rank","Horse","Trainer","Starts","Wins","Places","Win %","Place %"], [[i.get("rank"),i.get("horse"),i.get("trainer"),i.get("starts"),i.get("wins"),i.get("places"),_pct(i.get("win_pct")),_pct(i.get("place_pct"))] for i in (report.get("historical_horses") or {}).get("horses")]))
    if (report.get("historical_trainers") or {}).get("profiles"):
        story.append(Paragraph("Top 20 Trainer Strike Rate — Last 100", styles["RRTHeading"]))
        story.append(t(["Rank","Trainer","Starts","Wins","Places","Win %","Place %"], [[i.get("rank"),i.get("entity_name"),i.get("starts"),i.get("wins"),i.get("places"),_pct(i.get("win_pct")),_pct(i.get("place_pct"))] for i in (report.get("historical_trainers") or {}).get("profiles")]))
    if (report.get("historical_jockeys") or {}).get("profiles"):
        story.append(Paragraph("Top 20 Jockey Strike Rate — Last 100", styles["RRTHeading"]))
        story.append(t(["Rank","Jockey","Starts","Wins","Places","Win %","Place %"], [[i.get("rank"),i.get("entity_name"),i.get("starts"),i.get("wins"),i.get("places"),_pct(i.get("win_pct")),_pct(i.get("place_pct"))] for i in (report.get("historical_jockeys") or {}).get("profiles")]))
    story.append(Paragraph("Evidence-Based Factor Analysis", styles["RRTHeading"]))
    story.append(Paragraph("This section compares completed runner factor scores against actual results. It reports against the active PostgreSQL production weight set. Proposed changes do not alter production directly; they are evaluated and may be applied only through the current Promotion Controller when its configured gates and operating mode authorise promotion.", styles["BodyText"]))
    factor_effectiveness = report.get("factor_effectiveness") or {}
    weight_recommendations = report.get("weight_recommendations") or {}
    model_health = report.get("model_health") or {}
    story.append(Paragraph("Factor Effectiveness Ranking", styles["RRTHeading"]))
    story.append(t(["Rank","Factor","Win Gap","Place Gap","Win Corr","Place Corr","Signal","Conf"], [[i.get('predictive_rank'),i.get('label'),i.get('winner_gap'),i.get('place_gap'),i.get('win_correlation'),i.get('place_correlation'),i.get('signal_strength'),i.get('confidence')] for i in (factor_effectiveness.get('factors') or [])[:13]]))
    story.append(Paragraph("Future Adaptive Weight Proposals", styles["RRTHeading"]))
    story.append(t(["Factor","Current","Rec.","Change","Direction","Priority"], [[i.get('label'),i.get('current_weight'),i.get('recommended_weight'),i.get('change'),i.get('direction'),i.get('priority')] for i in (weight_recommendations.get('recommendations') or [])[:13]]))
    health_readiness = model_health.get("readiness") or {}
    story.append(Paragraph("Model Health", styles["RRTHeading"]))
    story.append(t(["Metric","Value"], [["Readiness Score", health_readiness.get('score')],["Dataset Maturity", health_readiness.get('maturity')],["Best Factor", (model_health.get('best_factor') or {}).get('label')],["Weakest Factor", (model_health.get('weakest_factor') or {}).get('label')],["Next Action", model_health.get('recommended_next_action')]], [5*cm,11*cm]))
    no_market = report.get("no_market_comparison") or {}
    story.append(Paragraph("No-Market Historical Comparison", styles["RRTHeading"]))
    story.append(Paragraph("Analysis-only. Uses the latest saved dedicated No-Market comparison; production weights are unchanged.", styles["BodyText"]))
    if no_market.get("saved_result_available"):
        story.append(t(
            ["Metric","Current Model %","No-Market %","Difference"],
            _no_market_performance_rows(no_market),
            [5.5*cm,3.5*cm,3.5*cm,3.5*cm],
        ))
        story.append(Paragraph("No-Market Weight Normalisation", styles["RRTHeading"]))
        story.append(t(
            ["Factor","Current Production %","No-Market Test %"],
            _no_market_weight_rows(no_market),
            [7*cm,4.5*cm,4.5*cm],
        ))
    else:
        story.append(Paragraph(escape(str(no_market.get("note") or "No saved No-Market comparison available.")), styles["BodyText"]))
    story.append(Paragraph("Safety Statement", styles["RRTHeading"])); story.append(Paragraph(escape(str(report.get("safety_note"))), styles["BodyText"]))
    doc.build(story); buffer.seek(0); return buffer.getvalue()

# ---------------------------------------------------------------------
# v2.22.1 RRT Predictor Systems Report
# ---------------------------------------------------------------------

def get_systems_report() -> Dict[str, Any]:
    """Return the consolidated backend, data, model and autonomy status."""
    try:
        from promotion_engine import get_promotion_status

        counts = fetch_one(
            """
            SELECT
              (SELECT COUNT(*) FROM rrt_meetings) AS meetings,
              (SELECT COUNT(*) FROM rrt_prediction_snapshots) AS prediction_snapshots,
              (SELECT COUNT(*) FROM rrt_results_snapshots) AS results_snapshots,
              (SELECT COUNT(*) FROM rrt_performance_snapshots) AS performance_snapshots,
              (SELECT COUNT(*) FROM rrt_runner_factor_snapshots) AS runner_factor_snapshots,
              (SELECT COUNT(*) FROM rrt_weight_simulations) AS weight_simulations,
              (SELECT COUNT(*) FROM rrt_replay_runs) AS replay_runs,
              (SELECT COUNT(*) FROM rrt_learning_cycles) AS learning_cycles,
              (SELECT COUNT(*) FROM rrt_model_candidates) AS model_candidates,
              (SELECT COUNT(*) FROM rrt_weight_promotion_audit) AS promotion_audits;
            """
        ) or {}
        active = fetch_one(
            """
            SELECT model_version, status, weights_json, source, notes, activated_at,
                   automatic_promotion, promoted_by_cycle_id
            FROM rrt_model_weight_sets
            WHERE status='Active'
            ORDER BY activated_at DESC NULLS LAST, created_at DESC LIMIT 1;
            """
        ) or {}
        rollback = fetch_one(
            """
            SELECT model_version, status, weights_json, source, notes, activated_at
            FROM rrt_model_weight_sets
            WHERE status='Rollback'
            ORDER BY created_at DESC LIMIT 1;
            """
        ) or {}
        native = fetch_one(
            """
            SELECT COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS completed_runner_rows,
                   COUNT(DISTINCT meeting_id) FILTER (WHERE actual_position IS NOT NULL) AS completed_meetings,
                   COUNT(DISTINCT (meeting_id::text || '|' || COALESCE(race_number::text,'')))
                     FILTER (WHERE actual_position IS NOT NULL) AS completed_races,
                   COUNT(*) FILTER (WHERE speed_score IS NOT NULL) AS speed_rows,
                   MIN(meeting_date) AS first_meeting_date,
                   MAX(meeting_date) AS latest_meeting_date
            FROM rrt_runner_factor_snapshots;
            """
        ) or {}
        promotion = get_promotion_status()
        return {
            "success": True,
            "provider": "PostgreSQL",
            "report": "rrt_predictor_systems_report",
            "report_version": REPORT_VERSION,
            "generated_at": _now_utc_iso(),
            "release": {
                "backend_version": REPORT_VERSION,
                "model_release": MODEL_VERSION,
                "database_schema_version": "2.21.0",
                "production_weight_set": active.get("model_version"),
                "promotion_controller_mode": promotion.get("promotion_mode"),
            },
            "architecture": {
                "prediction_engine": "Top 20 Intelligent Ranking Engine",
                "win": "Top 5 displayed from the meeting ranking",
                "each_way": "Distinct Each-Way profile",
                "roughies": "Value Index from meeting ranks 5-20",
                "speed_rating": "Normalised Speed Rating active",
                "native_capture": True,
                "results_processor": True,
                "factor_effectiveness": True,
                "selection_intelligence": True,
                "simulator": True,
                "replay": True,
                "adaptive_learning": True,
                "promotion_controller": True,
            },
            "database_counts": counts,
            "native_learning_dataset": native,
            "active_weight_set": active,
            "rollback_weight_set": rollback,
            "promotion_controller": promotion,
            "operating_state": {
                "predictions_live": True,
                "learning_live": True,
                "shadow_promotion_live": promotion.get("shadow_mode_active"),
                "automatic_live_promotion": promotion.get("automatic_weight_changes_enabled"),
                "production_weights_changed_by_report": False,
            },
            "next_phase": "v2.22.1 autonomous learning is LIVE and validated. Continue unattended results processing, adaptive candidate evaluation and Promotion Controller gating; future production weight changes remain subject to all configured safety gates.",
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "report": "rrt_predictor_systems_report",
            "report_version": REPORT_VERSION,
            "error": str(error),
        }


def generate_systems_report_html() -> str:
    report = get_systems_report()
    if not report.get("success"):
        return f"<html><body><h1>RRT Predictor Systems Report</h1><p>{escape(str(report.get('error')))}</p></body></html>"
    release = report.get("release") or {}
    state = report.get("operating_state") or {}
    counts = report.get("database_counts") or {}
    promotion = report.get("promotion_controller") or {}
    active = report.get("active_weight_set") or {}
    rows = "".join(
        f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>"
        for k, v in counts.items()
    )
    return f"""
    <html><head><title>RRT Predictor Systems Report v2.22.1</title>
    <style>body{{font-family:Arial,sans-serif;margin:32px;color:#222}}table{{border-collapse:collapse;width:100%;margin:12px 0 24px}}td,th{{border:1px solid #bbb;padding:8px;text-align:left}}th{{background:#eee}}.ok{{color:#087830;font-weight:bold}}</style></head>
    <body><h1>RRT Predictor Systems Report</h1>
    <p><strong>Generated:</strong> {escape(str(report.get('generated_at')))}</p>
    <h2>Release</h2><table>
    <tr><th>Backend</th><th>Schema</th><th>Production Weight Set</th><th>Promotion Mode</th></tr>
    <tr><td>{escape(str(release.get('backend_version')))}</td><td>{escape(str(release.get('database_schema_version')))}</td><td>{escape(str(release.get('production_weight_set')))}</td><td>{escape(str(release.get('promotion_controller_mode')))}</td></tr></table>
    <h2>Operating State</h2><table>{''.join(f'<tr><td>{escape(str(k))}</td><td class="ok">{escape(str(v))}</td></tr>' for k,v in state.items())}</table>
    <h2>Database Counts</h2><table><tr><th>Area</th><th>Count</th></tr>{rows}</table>
    <h2>Active Weights</h2><pre>{escape(str(active.get('weights_json') or {}))}</pre>
    <h2>Promotion Controller</h2><pre>{escape(str(promotion))}</pre>
    <h2>Next Phase</h2><p>{escape(str(report.get('next_phase')))}</p></body></html>
    """
