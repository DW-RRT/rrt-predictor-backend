from typing import Any, Dict

from database import fetch_all, fetch_one


REPORT_VERSION = "2.9.3"


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
                "rrt_wins": int((rrt_wins or {}).get("count") or 0),
                "pf_ai_wins": int((pf_ai_wins or {}).get("count") or 0),
                "ties": int((ties or {}).get("count") or 0),
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
