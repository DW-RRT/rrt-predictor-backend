from typing import Any, Dict, List, Optional

from database import fetch_all, fetch_one


REPORT_VERSION = "2.10.0"
ANALYTICS_VERSION = "2.10.0"
DATABASE_SCHEMA_VERSION = "2.9.0"
MODEL_VERSION = "2.8.1"


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
