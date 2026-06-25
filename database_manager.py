from typing import Any, Dict
import json

from database import execute_sql, fetch_all, fetch_one, postgres_status


SCHEMA_VERSION = "2.9.0"


def init_postgres_schema() -> Dict[str, Any]:
    try:
        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_model_versions (
                id SERIAL PRIMARY KEY,
                version TEXT UNIQUE NOT NULL,
                description TEXT,
                active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_meetings (
                id SERIAL PRIMARY KEY,
                meeting_id BIGINT UNIQUE NOT NULL,
                meeting_date DATE,
                track TEXT,
                country TEXT,
                state TEXT,
                race_type TEXT DEFAULT 'Horse',
                track_condition TEXT,
                weather TEXT,
                provider TEXT DEFAULT 'Punting Form',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_prediction_snapshots (
                id SERIAL PRIMARY KEY,
                meeting_id BIGINT NOT NULL,
                model_version TEXT,
                prediction_type TEXT,
                provider TEXT,
                source TEXT,
                track TEXT,
                meeting_date DATE,
                track_condition TEXT,
                weather TEXT,
                eligible_race_count INTEGER,
                runner_count INTEGER,
                prediction_json JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_results_snapshots (
                id SERIAL PRIMARY KEY,
                meeting_id BIGINT NOT NULL,
                track TEXT,
                meeting_date DATE,
                results_updated TIMESTAMPTZ,
                result_json JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_performance_snapshots (
                id SERIAL PRIMARY KEY,
                meeting_id BIGINT NOT NULL,
                track TEXT,
                meeting_date DATE,
                model_version TEXT,
                overall_accuracy NUMERIC(6,2),
                top_win_strike_rate NUMERIC(6,2),
                each_way_strike_rate NUMERIC(6,2),
                roughie_strike_rate NUMERIC(6,2),
                double_strike_rate NUMERIC(6,2),
                quaddie_strike_rate NUMERIC(6,2),
                pf_ai_top_win_strike_rate NUMERIC(6,2),
                performance_json JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            INSERT INTO rrt_model_versions (version, description, active)
            VALUES (%s, %s, %s)
            ON CONFLICT (version)
            DO UPDATE SET
                description = EXCLUDED.description,
                active = EXCLUDED.active;
            """,
            (
                SCHEMA_VERSION,
                "RRT Predictor v2.9.0 PostgreSQL foundation. No adaptive weighting active yet.",
                True,
            ),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "schema_version": SCHEMA_VERSION,
            "message": "PostgreSQL schema initialised successfully.",
            "tables": [
                "rrt_model_versions",
                "rrt_meetings",
                "rrt_prediction_snapshots",
                "rrt_results_snapshots",
                "rrt_performance_snapshots",
            ],
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "schema_version": SCHEMA_VERSION,
            "error": str(error),
        }


def get_postgres_status() -> Dict[str, Any]:
    status = postgres_status()

    if not status.get("success"):
        return status

    tables = fetch_all(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'rrt_%'
        ORDER BY table_name;
        """
    )

    return {
        **status,
        "schema_version": SCHEMA_VERSION,
        "rrt_tables": [row.get("table_name") for row in tables],
        "rrt_table_count": len(tables),
    }


def get_database_summary() -> Dict[str, Any]:
    try:
        meeting_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_meetings;")
        prediction_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_prediction_snapshots;")
        results_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_results_snapshots;")
        performance_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_performance_snapshots;")

        latest_performance = fetch_all(
            """
            SELECT
                meeting_id,
                track,
                meeting_date,
                model_version,
                overall_accuracy,
                top_win_strike_rate,
                each_way_strike_rate,
                pf_ai_top_win_strike_rate,
                created_at
            FROM rrt_performance_snapshots
            ORDER BY created_at DESC
            LIMIT 10;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "schema_version": SCHEMA_VERSION,
            "counts": {
                "meetings": int((meeting_count or {}).get("count") or 0),
                "prediction_snapshots": int((prediction_count or {}).get("count") or 0),
                "results_snapshots": int((results_count or {}).get("count") or 0),
                "performance_snapshots": int((performance_count or {}).get("count") or 0),
            },
            "latest_performance": latest_performance,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "schema_version": SCHEMA_VERSION,
            "error": str(error),
        }


def save_prediction_snapshot(prediction_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    try:
        meeting_id = prediction_snapshot.get("meeting_id")

        if not meeting_id:
            return {
                "success": False,
                "message": "Prediction snapshot missing meeting_id.",
            }

        execute_sql(
            """
            INSERT INTO rrt_meetings (
                meeting_id,
                meeting_date,
                track,
                track_condition,
                weather,
                provider
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_id)
            DO UPDATE SET
                meeting_date = EXCLUDED.meeting_date,
                track = EXCLUDED.track,
                track_condition = EXCLUDED.track_condition,
                weather = EXCLUDED.weather,
                provider = EXCLUDED.provider,
                updated_at = NOW();
            """,
            (
                meeting_id,
                prediction_snapshot.get("meeting_date"),
                prediction_snapshot.get("track"),
                prediction_snapshot.get("track_condition"),
                prediction_snapshot.get("weather"),
                prediction_snapshot.get("provider") or "Punting Form",
            ),
        )

        execute_sql(
            """
            INSERT INTO rrt_prediction_snapshots (
                meeting_id,
                model_version,
                prediction_type,
                provider,
                source,
                track,
                meeting_date,
                track_condition,
                weather,
                eligible_race_count,
                runner_count,
                prediction_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb);
            """,
            (
                meeting_id,
                prediction_snapshot.get("model_version"),
                prediction_snapshot.get("prediction_type"),
                prediction_snapshot.get("provider"),
                prediction_snapshot.get("source"),
                prediction_snapshot.get("track"),
                prediction_snapshot.get("meeting_date"),
                prediction_snapshot.get("track_condition"),
                prediction_snapshot.get("weather"),
                prediction_snapshot.get("eligible_race_count"),
                prediction_snapshot.get("runner_count"),
                json.dumps(prediction_snapshot),
            ),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "message": "Prediction snapshot saved.",
            "meeting_id": meeting_id,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to save prediction snapshot.",
            "error": str(error),
        }


def save_results_snapshot(results_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    try:
        meeting_id = results_snapshot.get("meeting_id")

        if not meeting_id:
            return {
                "success": False,
                "message": "Results snapshot missing meeting_id.",
            }

        execute_sql(
            """
            INSERT INTO rrt_results_snapshots (
                meeting_id,
                track,
                meeting_date,
                results_updated,
                result_json
            )
            VALUES (%s, %s, %s, %s, %s::jsonb);
            """,
            (
                meeting_id,
                results_snapshot.get("track"),
                results_snapshot.get("meeting_date"),
                results_snapshot.get("results_updated"),
                json.dumps(results_snapshot),
            ),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "message": "Results snapshot saved.",
            "meeting_id": meeting_id,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to save results snapshot.",
            "error": str(error),
        }


def save_performance_snapshot(performance_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    try:
        meeting_id = performance_snapshot.get("meeting_id")
        accuracy = performance_snapshot.get("accuracy") or {}
        pf_ai = performance_snapshot.get("pf_ai_comparison") or {}
        pf_ai_top_win = pf_ai.get("pf_ai_top_4_win") or {}

        if not meeting_id:
            return {
                "success": False,
                "message": "Performance snapshot missing meeting_id.",
            }

        execute_sql(
            """
            INSERT INTO rrt_performance_snapshots (
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
                performance_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb);
            """,
            (
                meeting_id,
                performance_snapshot.get("track"),
                performance_snapshot.get("meeting_date"),
                performance_snapshot.get("model_version"),
                accuracy.get("overall_accuracy"),
                (accuracy.get("top_4_win") or {}).get("strike_rate"),
                (accuracy.get("top_4_each_way") or {}).get("strike_rate"),
                (accuracy.get("top_4_roughies") or {}).get("strike_rate"),
                (accuracy.get("best_double") or {}).get("strike_rate"),
                (accuracy.get("best_quaddie") or {}).get("strike_rate"),
                pf_ai_top_win.get("strike_rate"),
                json.dumps(performance_snapshot),
            ),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "message": "Performance snapshot saved.",
            "meeting_id": meeting_id,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to save performance snapshot.",
            "error": str(error),
        }
