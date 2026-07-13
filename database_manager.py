from typing import Any, Dict, List
import json

from database import execute_sql, fetch_all, fetch_one, postgres_status


SCHEMA_VERSION = "2.18.3"


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
            CREATE TABLE IF NOT EXISTS rrt_runner_factor_snapshots (
                id SERIAL PRIMARY KEY,
                meeting_id BIGINT NOT NULL,
                model_version TEXT,
                track TEXT,
                meeting_date DATE,
                race_id BIGINT,
                race_number INTEGER,
                runner_id BIGINT,
                runner_key TEXT NOT NULL,
                runner_name TEXT,
                tab_number INTEGER,
                final_score NUMERIC(6,2),
                confidence NUMERIC(6,2),
                market_price NUMERIC(10,2),
                market_rank INTEGER,
                last10_score NUMERIC(6,2),
                win_place_score NUMERIC(6,2),
                track_record_score NUMERIC(6,2),
                distance_record_score NUMERIC(6,2),
                track_distance_record_score NUMERIC(6,2),
                track_condition_score NUMERIC(6,2),
                trainer_score NUMERIC(6,2),
                jockey_score NUMERIC(6,2),
                trainer_jockey_score NUMERIC(6,2),
                barrier_score NUMERIC(6,2),
                weight_score NUMERIC(6,2),
                market_score NUMERIC(6,2),
                weighted_last10 NUMERIC(8,4),
                weighted_win_place NUMERIC(8,4),
                weighted_track_record NUMERIC(8,4),
                weighted_distance_record NUMERIC(8,4),
                weighted_track_distance_record NUMERIC(8,4),
                weighted_track_condition NUMERIC(8,4),
                weighted_trainer NUMERIC(8,4),
                weighted_jockey NUMERIC(8,4),
                weighted_trainer_jockey NUMERIC(8,4),
                weighted_barrier NUMERIC(8,4),
                weighted_weight NUMERIC(8,4),
                weighted_market NUMERIC(8,4),
                actual_position INTEGER,
                actual_price NUMERIC(10,2),
                hit_win BOOLEAN,
                hit_place BOOLEAN,
                factor_json JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_rrt_runner_factor_latest
            ON rrt_runner_factor_snapshots (meeting_id, model_version, runner_key);
            """
        )

        # Unique indexes added in Stage 2B.
        execute_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_rrt_prediction_latest
            ON rrt_prediction_snapshots (meeting_id, model_version);
            """
        )

        execute_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_rrt_results_latest
            ON rrt_results_snapshots (meeting_id);
            """
        )

        execute_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_rrt_performance_latest
            ON rrt_performance_snapshots (meeting_id, model_version);
            """
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_weight_simulations (
                id SERIAL PRIMARY KEY,
                simulation_id TEXT UNIQUE NOT NULL,
                simulation_name TEXT,
                simulator_version TEXT,
                model_version TEXT,
                dataset_runner_count INTEGER,
                dataset_race_count INTEGER,
                current_weights_json JSONB,
                test_weights_json JSONB,
                roughie_rules_json JSONB,
                current_metrics_json JSONB,
                simulated_metrics_json JSONB,
                improvement_json JSONB,
                recommendation_json JSONB,
                simulation_json JSONB NOT NULL,
                simulation_group TEXT,
                factor_tested TEXT,
                old_weight NUMERIC,
                new_weight NUMERIC,
                change_amount NUMERIC,
                notes TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )


        execute_sql("ALTER TABLE rrt_weight_simulations ADD COLUMN IF NOT EXISTS simulation_group TEXT;")
        execute_sql("ALTER TABLE rrt_weight_simulations ADD COLUMN IF NOT EXISTS factor_tested TEXT;")
        execute_sql("ALTER TABLE rrt_weight_simulations ADD COLUMN IF NOT EXISTS old_weight NUMERIC;")
        execute_sql("ALTER TABLE rrt_weight_simulations ADD COLUMN IF NOT EXISTS new_weight NUMERIC;")
        execute_sql("ALTER TABLE rrt_weight_simulations ADD COLUMN IF NOT EXISTS change_amount NUMERIC;")

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_replay_runs (
                id SERIAL PRIMARY KEY,
                replay_id TEXT UNIQUE NOT NULL,
                replay_name TEXT,
                replay_version TEXT NOT NULL,
                model_version TEXT,
                min_meeting_date DATE,
                max_meeting_date DATE,
                dataset_runner_count INTEGER,
                dataset_race_count INTEGER,
                dataset_meeting_count INTEGER,
                current_weights_json JSONB,
                replay_weights_json JSONB,
                current_metrics_json JSONB,
                replay_metrics_json JSONB,
                improvement_json JSONB,
                replay_json JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_learning_cycles (
                id SERIAL PRIMARY KEY,
                cycle_id TEXT UNIQUE NOT NULL,
                cycle_name TEXT,
                learning_version TEXT NOT NULL,
                model_version TEXT NOT NULL,
                dataset_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                factor_report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                weight_report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                simulation_report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                selection_report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                recommendations_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                cycle_json JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        # Upgrade existing learning-cycle tables created by earlier v2.18.x builds.
        # CREATE TABLE IF NOT EXISTS does not add newly introduced columns.
        execute_sql("ALTER TABLE rrt_learning_cycles ADD COLUMN IF NOT EXISTS factor_report_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
        execute_sql("ALTER TABLE rrt_learning_cycles ADD COLUMN IF NOT EXISTS weight_report_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
        execute_sql("ALTER TABLE rrt_learning_cycles ADD COLUMN IF NOT EXISTS simulation_report_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
        execute_sql("ALTER TABLE rrt_learning_cycles ADD COLUMN IF NOT EXISTS selection_report_json JSONB NOT NULL DEFAULT '{}'::jsonb;")

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_factor_recommendations (
                id SERIAL PRIMARY KEY,
                cycle_id TEXT NOT NULL,
                factor TEXT NOT NULL,
                current_weight NUMERIC,
                recommended_weight NUMERIC,
                change_amount NUMERIC,
                expected_improvement NUMERIC,
                confidence_pct NUMERIC(6,2),
                status TEXT,
                rationale TEXT,
                recommendation_json JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql(
            """
            CREATE INDEX IF NOT EXISTS ix_rrt_factor_recommendations_cycle
            ON rrt_factor_recommendations (cycle_id);
            """
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_selection_analysis (
                id SERIAL PRIMARY KEY,
                analysis_version TEXT,
                model_version TEXT,
                generated_at TIMESTAMPTZ DEFAULT NOW(),
                dataset_runner_count INTEGER,
                dataset_race_count INTEGER,
                top4_hit_rate NUMERIC(6,2),
                near_miss_rate NUMERIC(6,2),
                boundary_miss_rate NUMERIC(6,2),
                roughie_like_winner_rate NUMERIC(6,2),
                analysis_json JSONB NOT NULL
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
                "2.18.3",
                "RRT Predictor v2.18.3 native full-field capture and adaptive learning integration. Historical learning retained; production weights unchanged automatically.",
                True,
            ),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "schema_version": SCHEMA_VERSION,
            "message": "PostgreSQL schema initialised successfully with duplicate-safe indexes.",
            "tables": [
                "rrt_model_versions",
                "rrt_meetings",
                "rrt_prediction_snapshots",
                "rrt_results_snapshots",
                "rrt_performance_snapshots",
                "rrt_runner_factor_snapshots",
                "rrt_weight_simulations",
                "rrt_selection_analysis",
                "rrt_replay_runs",
                "rrt_learning_cycles",
                "rrt_factor_recommendations",
            ],
            "indexes": [
                "ux_rrt_prediction_latest",
                "ux_rrt_results_latest",
                "ux_rrt_performance_latest",
                "ux_rrt_runner_factor_latest",
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

    indexes = fetch_all(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname LIKE 'ux_rrt_%'
        ORDER BY indexname;
        """
    )

    return {
        **status,
        "schema_version": SCHEMA_VERSION,
        "rrt_tables": [row.get("table_name") for row in tables],
        "rrt_table_count": len(tables),
        "rrt_unique_indexes": [row.get("indexname") for row in indexes],
        "rrt_unique_index_count": len(indexes),
    }


def get_database_summary() -> Dict[str, Any]:
    try:
        meeting_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_meetings;")
        prediction_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_prediction_snapshots;")
        results_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_results_snapshots;")
        performance_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_performance_snapshots;")
        factor_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_runner_factor_snapshots;")
        simulation_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_weight_simulations;")
        selection_analysis_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_selection_analysis;")
        replay_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_replay_runs;")
        learning_cycle_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_learning_cycles;")
        factor_recommendation_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_factor_recommendations;")

        averages = fetch_one(
            """
            SELECT
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate,
                ROUND(AVG(roughie_strike_rate), 2) AS avg_roughie_strike_rate,
                ROUND(AVG(double_strike_rate), 2) AS avg_double_strike_rate,
                ROUND(AVG(quaddie_strike_rate), 2) AS avg_quaddie_strike_rate,
                ROUND(AVG(pf_ai_top_win_strike_rate), 2) AS avg_pf_ai_top_win_strike_rate
            FROM rrt_performance_snapshots;
            """
        )

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
                roughie_strike_rate,
                double_strike_rate,
                quaddie_strike_rate,
                pf_ai_top_win_strike_rate,
                created_at
            FROM rrt_performance_snapshots
            ORDER BY created_at DESC
            LIMIT 10;
            """
        )

        best_tracks = fetch_all(
            """
            SELECT
                track,
                COUNT(*) AS meeting_count,
                ROUND(AVG(overall_accuracy), 2) AS avg_overall_accuracy,
                ROUND(AVG(top_win_strike_rate), 2) AS avg_top_win_strike_rate,
                ROUND(AVG(each_way_strike_rate), 2) AS avg_each_way_strike_rate
            FROM rrt_performance_snapshots
            GROUP BY track
            ORDER BY avg_overall_accuracy DESC
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
                "runner_factor_snapshots": int((factor_count or {}).get("count") or 0),
                "weight_simulations": int((simulation_count or {}).get("count") or 0),
                "selection_analysis": int((selection_analysis_count or {}).get("count") or 0),
                "replay_runs": int((replay_count or {}).get("count") or 0),
                "learning_cycles": int((learning_cycle_count or {}).get("count") or 0),
                "factor_recommendations": int((factor_recommendation_count or {}).get("count") or 0),
            },
            "averages": averages or {},
            "best_tracks": best_tracks,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (meeting_id, model_version)
            DO UPDATE SET
                prediction_type = EXCLUDED.prediction_type,
                provider = EXCLUDED.provider,
                source = EXCLUDED.source,
                track = EXCLUDED.track,
                meeting_date = EXCLUDED.meeting_date,
                track_condition = EXCLUDED.track_condition,
                weather = EXCLUDED.weather,
                eligible_race_count = EXCLUDED.eligible_race_count,
                runner_count = EXCLUDED.runner_count,
                prediction_json = EXCLUDED.prediction_json,
                created_at = NOW();
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
            "message": "Prediction snapshot saved or updated.",
            "meeting_id": meeting_id,
            "duplicate_safe": True,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to save prediction snapshot.",
            "error": str(error),
        }


def load_prediction_snapshot(
    meeting_id: int,
    model_version: str = "2.18.3",
) -> Dict[str, Any]:
    try:
        row = fetch_one(
            """
            SELECT
                meeting_id,
                model_version,
                track,
                meeting_date,
                track_condition,
                weather,
                prediction_json,
                created_at
            FROM rrt_prediction_snapshots
            WHERE meeting_id = %s
              AND model_version = %s
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (
                meeting_id,
                model_version,
            ),
        )

        if not row:
            return {
                "success": False,
                "provider": "PostgreSQL",
                "message": "No stored prediction snapshot found in PostgreSQL.",
                "meeting_id": meeting_id,
                "model_version": model_version,
            }

        prediction_json = row.get("prediction_json") or {}

        if isinstance(prediction_json, str):
            prediction_json = json.loads(prediction_json)

        if not isinstance(prediction_json, dict):
            return {
                "success": False,
                "provider": "PostgreSQL",
                "message": "Stored prediction snapshot is not a valid JSON object.",
                "meeting_id": meeting_id,
                "model_version": model_version,
            }

        prediction_json["meeting_id"] = prediction_json.get("meeting_id") or row.get("meeting_id")
        prediction_json["model_version"] = prediction_json.get("model_version") or row.get("model_version")
        prediction_json["track"] = prediction_json.get("track") or row.get("track")
        prediction_json["meeting_date"] = prediction_json.get("meeting_date") or row.get("meeting_date")
        prediction_json["track_condition"] = prediction_json.get("track_condition") or row.get("track_condition")
        prediction_json["weather"] = prediction_json.get("weather") or row.get("weather")

        return {
            "success": True,
            "provider": "PostgreSQL",
            "message": "Prediction snapshot loaded from PostgreSQL.",
            "meeting_id": meeting_id,
            "model_version": model_version,
            "snapshot": prediction_json,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to load prediction snapshot from PostgreSQL.",
            "meeting_id": meeting_id,
            "model_version": model_version,
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
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (meeting_id)
            DO UPDATE SET
                track = EXCLUDED.track,
                meeting_date = EXCLUDED.meeting_date,
                results_updated = EXCLUDED.results_updated,
                result_json = EXCLUDED.result_json,
                created_at = NOW();
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
            "message": "Results snapshot saved or updated.",
            "meeting_id": meeting_id,
            "duplicate_safe": True,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (meeting_id, model_version)
            DO UPDATE SET
                track = EXCLUDED.track,
                meeting_date = EXCLUDED.meeting_date,
                overall_accuracy = EXCLUDED.overall_accuracy,
                top_win_strike_rate = EXCLUDED.top_win_strike_rate,
                each_way_strike_rate = EXCLUDED.each_way_strike_rate,
                roughie_strike_rate = EXCLUDED.roughie_strike_rate,
                double_strike_rate = EXCLUDED.double_strike_rate,
                quaddie_strike_rate = EXCLUDED.quaddie_strike_rate,
                pf_ai_top_win_strike_rate = EXCLUDED.pf_ai_top_win_strike_rate,
                performance_json = EXCLUDED.performance_json,
                created_at = NOW();
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
            "message": "Performance snapshot saved or updated.",
            "meeting_id": meeting_id,
            "duplicate_safe": True,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to save performance snapshot.",
            "error": str(error),
        }


# ---------------------------------------------------------------------
# Factor Capture - RRT Predictor v2.12.0
# ---------------------------------------------------------------------


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float_or_none(value: Any):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _runner_factor_key(runner: Dict[str, Any]) -> str:
    race_id = str(runner.get("race_id") or "").strip()
    race_number = str(runner.get("race_number") or "").strip()
    runner_id = str(runner.get("runner_id") or "").strip()
    tab_number = str(runner.get("tab_number") or runner.get("number") or "").strip()
    runner_name = str(runner.get("runner") or runner.get("horse_name") or "").upper().strip()

    if runner_id and runner_id != "0":
        return f"runner_id:{runner_id}"

    return f"race:{race_id or race_number}|tab:{tab_number}|name:{runner_name}"



def _extract_runner_factor_rows_from_prediction_snapshot(
    prediction_snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    factor_capture = prediction_snapshot.get("factor_capture") or {}
    direct_rows = factor_capture.get("runners") or []

    if direct_rows:
        return direct_rows

    predictions = prediction_snapshot.get("predictions") or {}
    collected: Dict[str, Dict[str, Any]] = {}

    def add_runner(runner: Any) -> None:
        if not isinstance(runner, dict):
            return

        has_factor_data = bool(
            runner.get("score_breakdown")
            or runner.get("weighted_breakdown")
            or runner.get("factor_capture")
        )

        if not has_factor_data:
            return

        runner_key = runner.get("runner_key") or _runner_factor_key(runner)

        collected[runner_key] = {
            **runner,
            "runner_key": runner_key,
        }

    for category_key in [
        "top_4_win_bets",
        "top_4_each_way_bets",
        "top_4_roughies",
        "top_3_win_bets",
        "top_3_each_way_bets",
        "top_3_roughies",
    ]:
        for runner in predictions.get(category_key) or []:
            add_runner(runner)

    for multi_key in ["best_double", "best_quaddie"]:
        multi = predictions.get(multi_key) or {}

        for leg in multi.get("legs") or []:
            for runner in leg.get("selections") or []:
                add_runner(
                    {
                        **runner,
                        "race_id": runner.get("race_id") or leg.get("race_id"),
                        "race_number": runner.get("race_number") or leg.get("race_number"),
                        "race_name": runner.get("race_name") or leg.get("race_name"),
                        "race_title": runner.get("race_title") or leg.get("race_title"),
                        "distance_m": runner.get("distance_m") or leg.get("distance_m"),
                    }
                )

    return list(collected.values())


def save_runner_factor_snapshots(prediction_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    try:
        meeting_id = prediction_snapshot.get("meeting_id")
        model_version = prediction_snapshot.get("model_version")
        runners = _extract_runner_factor_rows_from_prediction_snapshot(prediction_snapshot)

        if not meeting_id:
            return {
                "success": False,
                "provider": "PostgreSQL",
                "message": "Factor capture skipped: prediction snapshot missing meeting_id.",
            }

        if not runners:
            return {
                "success": True,
                "provider": "PostgreSQL",
                "message": "No runner factor rows available to save after checking factor_capture and prediction selections.",
                "meeting_id": meeting_id,
                "saved_count": 0,
            }

        saved_count = 0

        for runner in runners:
            breakdown = runner.get("score_breakdown") or {}
            weighted = runner.get("weighted_breakdown") or {}
            runner_key = runner.get("runner_key") or _runner_factor_key(runner)

            execute_sql(
                """
                INSERT INTO rrt_runner_factor_snapshots (
                    meeting_id,
                    model_version,
                    track,
                    meeting_date,
                    race_id,
                    race_number,
                    runner_id,
                    runner_key,
                    runner_name,
                    tab_number,
                    final_score,
                    confidence,
                    market_price,
                    market_rank,
                    last10_score,
                    win_place_score,
                    track_record_score,
                    distance_record_score,
                    track_distance_record_score,
                    track_condition_score,
                    trainer_score,
                    jockey_score,
                    trainer_jockey_score,
                    barrier_score,
                    weight_score,
                    market_score,
                    weighted_last10,
                    weighted_win_place,
                    weighted_track_record,
                    weighted_distance_record,
                    weighted_track_distance_record,
                    weighted_track_condition,
                    weighted_trainer,
                    weighted_jockey,
                    weighted_trainer_jockey,
                    weighted_barrier,
                    weighted_weight,
                    weighted_market,
                    factor_json
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (meeting_id, model_version, runner_key)
                DO UPDATE SET
                    track = EXCLUDED.track,
                    meeting_date = EXCLUDED.meeting_date,
                    race_id = EXCLUDED.race_id,
                    race_number = EXCLUDED.race_number,
                    runner_id = EXCLUDED.runner_id,
                    runner_name = EXCLUDED.runner_name,
                    tab_number = EXCLUDED.tab_number,
                    final_score = EXCLUDED.final_score,
                    confidence = EXCLUDED.confidence,
                    market_price = EXCLUDED.market_price,
                    market_rank = EXCLUDED.market_rank,
                    last10_score = EXCLUDED.last10_score,
                    win_place_score = EXCLUDED.win_place_score,
                    track_record_score = EXCLUDED.track_record_score,
                    distance_record_score = EXCLUDED.distance_record_score,
                    track_distance_record_score = EXCLUDED.track_distance_record_score,
                    track_condition_score = EXCLUDED.track_condition_score,
                    trainer_score = EXCLUDED.trainer_score,
                    jockey_score = EXCLUDED.jockey_score,
                    trainer_jockey_score = EXCLUDED.trainer_jockey_score,
                    barrier_score = EXCLUDED.barrier_score,
                    weight_score = EXCLUDED.weight_score,
                    market_score = EXCLUDED.market_score,
                    weighted_last10 = EXCLUDED.weighted_last10,
                    weighted_win_place = EXCLUDED.weighted_win_place,
                    weighted_track_record = EXCLUDED.weighted_track_record,
                    weighted_distance_record = EXCLUDED.weighted_distance_record,
                    weighted_track_distance_record = EXCLUDED.weighted_track_distance_record,
                    weighted_track_condition = EXCLUDED.weighted_track_condition,
                    weighted_trainer = EXCLUDED.weighted_trainer,
                    weighted_jockey = EXCLUDED.weighted_jockey,
                    weighted_trainer_jockey = EXCLUDED.weighted_trainer_jockey,
                    weighted_barrier = EXCLUDED.weighted_barrier,
                    weighted_weight = EXCLUDED.weighted_weight,
                    weighted_market = EXCLUDED.weighted_market,
                    factor_json = EXCLUDED.factor_json,
                    updated_at = NOW();
                """,
                (
                    meeting_id,
                    model_version,
                    prediction_snapshot.get("track"),
                    prediction_snapshot.get("meeting_date"),
                    runner.get("race_id"),
                    runner.get("race_number"),
                    runner.get("runner_id"),
                    runner_key,
                    runner.get("runner") or runner.get("horse_name"),
                    runner.get("tab_number") or runner.get("number"),
                    runner.get("score"),
                    runner.get("confidence"),
                    runner.get("price"),
                    runner.get("market_rank"),
                    breakdown.get("last10_form"),
                    breakdown.get("win_place"),
                    breakdown.get("track_record"),
                    breakdown.get("distance_record"),
                    breakdown.get("track_distance_record"),
                    breakdown.get("track_condition_record"),
                    breakdown.get("trainer"),
                    breakdown.get("jockey"),
                    breakdown.get("trainer_jockey"),
                    breakdown.get("barrier"),
                    breakdown.get("weight"),
                    breakdown.get("market_price"),
                    weighted.get("last10_form"),
                    weighted.get("win_place"),
                    weighted.get("track_record"),
                    weighted.get("distance_record"),
                    weighted.get("track_distance_record"),
                    weighted.get("track_condition_record"),
                    weighted.get("trainer"),
                    weighted.get("jockey"),
                    weighted.get("trainer_jockey"),
                    weighted.get("barrier"),
                    weighted.get("weight"),
                    weighted.get("market_price"),
                    json.dumps(runner),
                ),
            )

            saved_count += 1

        return {
            "success": True,
            "provider": "PostgreSQL",
            "message": "Runner factor snapshots saved or updated.",
            "meeting_id": meeting_id,
            "saved_count": saved_count,
            "duplicate_safe": True,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to save runner factor snapshots.",
            "error": str(error),
        }


def update_runner_factor_results_from_results(
    prediction_snapshot: Dict[str, Any],
    results_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        meeting_id = prediction_snapshot.get("meeting_id")
        model_version = prediction_snapshot.get("model_version")
        races = results_snapshot.get("races") or []
        updated_count = 0

        if not meeting_id:
            return {
                "success": False,
                "provider": "PostgreSQL",
                "message": "Factor result update skipped: missing meeting_id.",
            }

        factor_rows = fetch_all(
            """
            SELECT id, runner_key, race_number, runner_id, tab_number, runner_name
            FROM rrt_runner_factor_snapshots
            WHERE meeting_id = %s
              AND model_version = %s;
            """,
            (
                meeting_id,
                model_version,
            ),
        )

        if not factor_rows:
            return {
                "success": True,
                "provider": "PostgreSQL",
                "message": "No factor rows available for result update.",
                "meeting_id": meeting_id,
                "updated_count": 0,
            }

        results_by_race = {
            str(race.get("race_number") or "").strip(): race
            for race in races
        }

        for row in factor_rows:
            race = results_by_race.get(str(row.get("race_number") or "").strip())

            if not race:
                continue

            matched_result = None
            row_runner_id = str(row.get("runner_id") or "").strip()
            row_tab = str(row.get("tab_number") or "").strip()
            row_name = str(row.get("runner_name") or "").upper().replace(".", "").replace("'", "").replace("’", "").replace("-", " ").strip()

            for runner in race.get("runners") or []:
                result_runner_id = str(runner.get("runner_id") or "").strip()
                result_tab = str(runner.get("tab_number") or "").strip()
                result_name = str(runner.get("runner") or "").upper().replace(".", "").replace("'", "").replace("’", "").replace("-", " ").strip()

                if row_runner_id and row_runner_id != "0" and result_runner_id == row_runner_id:
                    matched_result = runner
                    break

                if row_tab and result_tab == row_tab:
                    matched_result = runner
                    break

                if row_name and result_name == row_name:
                    matched_result = runner
                    break

            if not matched_result:
                continue

            actual_position = matched_result.get("position")
            actual_price = matched_result.get("price")
            hit_win = actual_position == 1
            hit_place = actual_position in [1, 2, 3] if actual_position is not None else False

            execute_sql(
                """
                UPDATE rrt_runner_factor_snapshots
                SET
                    actual_position = %s,
                    actual_price = %s,
                    hit_win = %s,
                    hit_place = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (
                    actual_position,
                    _safe_float_or_none(actual_price),
                    hit_win,
                    hit_place,
                    row.get("id"),
                ),
            )

            updated_count += 1

        return {
            "success": True,
            "provider": "PostgreSQL",
            "message": "Runner factor result fields updated.",
            "meeting_id": meeting_id,
            "updated_count": updated_count,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "message": "Failed to update runner factor results.",
            "error": str(error),
        }


def get_factor_capture_summary() -> Dict[str, Any]:
    try:
        totals = fetch_one(
            """
            SELECT
                COUNT(*) AS runner_factor_rows,
                COUNT(DISTINCT meeting_id) AS meeting_count,
                COUNT(DISTINCT track) AS track_count,
                COUNT(DISTINCT meeting_date) AS date_count,
                COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS runners_with_results,
                ROUND(AVG(final_score), 2) AS avg_final_score,
                ROUND(AVG(confidence), 2) AS avg_confidence
            FROM rrt_runner_factor_snapshots;
            """
        ) or {}

        factor_averages = fetch_one(
            """
            SELECT
                ROUND(AVG(last10_score), 2) AS avg_last10_score,
                ROUND(AVG(win_place_score), 2) AS avg_win_place_score,
                ROUND(AVG(track_record_score), 2) AS avg_track_record_score,
                ROUND(AVG(distance_record_score), 2) AS avg_distance_record_score,
                ROUND(AVG(track_distance_record_score), 2) AS avg_track_distance_record_score,
                ROUND(AVG(track_condition_score), 2) AS avg_track_condition_score,
                ROUND(AVG(trainer_score), 2) AS avg_trainer_score,
                ROUND(AVG(jockey_score), 2) AS avg_jockey_score,
                ROUND(AVG(trainer_jockey_score), 2) AS avg_trainer_jockey_score,
                ROUND(AVG(barrier_score), 2) AS avg_barrier_score,
                ROUND(AVG(weight_score), 2) AS avg_weight_score,
                ROUND(AVG(market_score), 2) AS avg_market_score
            FROM rrt_runner_factor_snapshots;
            """
        ) or {}

        winner_averages = fetch_one(
            """
            SELECT
                COUNT(*) AS winner_count,
                ROUND(AVG(final_score), 2) AS avg_winner_final_score,
                ROUND(AVG(last10_score), 2) AS avg_winner_last10_score,
                ROUND(AVG(track_condition_score), 2) AS avg_winner_track_condition_score,
                ROUND(AVG(trainer_jockey_score), 2) AS avg_winner_trainer_jockey_score,
                ROUND(AVG(barrier_score), 2) AS avg_winner_barrier_score,
                ROUND(AVG(market_score), 2) AS avg_winner_market_score
            FROM rrt_runner_factor_snapshots
            WHERE actual_position = 1;
            """
        ) or {}

        latest = fetch_all(
            """
            SELECT
                meeting_id,
                track,
                meeting_date,
                COUNT(*) AS runner_factor_rows,
                COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS runners_with_results,
                ROUND(AVG(final_score), 2) AS avg_final_score
            FROM rrt_runner_factor_snapshots
            GROUP BY meeting_id, track, meeting_date
            ORDER BY meeting_date DESC, meeting_id DESC
            LIMIT 20;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "schema_version": SCHEMA_VERSION,
            "report": "factor_capture_summary",
            "totals": totals,
            "factor_averages": factor_averages,
            "winner_averages": winner_averages,
            "latest_meetings": latest,
            "capture_scope": "native_full_field",
            "analysis_note": "All eligible future runners are captured natively before results. Historical factor learning remains valid and production weights are unchanged automatically.",
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "schema_version": SCHEMA_VERSION,
            "report": "factor_capture_summary",
            "error": str(error),
        }


# ---------------------------------------------------------------------
# Automatic Results Processor - RRT Predictor v2.13.0
# ---------------------------------------------------------------------


def get_pending_prediction_snapshots_for_results(
    limit: int = 25,
) -> Dict[str, Any]:
    try:
        rows = fetch_all(
            """
            SELECT
                p.meeting_id,
                p.model_version,
                p.track,
                p.meeting_date,
                p.created_at AS prediction_created_at
            FROM rrt_prediction_snapshots p
            LEFT JOIN rrt_performance_snapshots perf
              ON perf.meeting_id = p.meeting_id
             AND perf.model_version = p.model_version
            WHERE perf.id IS NULL
            ORDER BY p.meeting_date ASC NULLS LAST, p.created_at ASC
            LIMIT %s;
            """,
            (limit,),
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "processor_version": "2.13.0",
            "pending_count": len(rows),
            "pending_predictions": rows,
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "processor_version": "2.13.0",
            "message": "Failed to load pending prediction snapshots for automatic results processing.",
            "error": str(error),
        }


def get_results_processor_summary() -> Dict[str, Any]:
    try:
        totals = fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM rrt_prediction_snapshots) AS prediction_snapshots,
                (SELECT COUNT(*) FROM rrt_results_snapshots) AS results_snapshots,
                (SELECT COUNT(*) FROM rrt_performance_snapshots) AS performance_snapshots,
                (
                    SELECT COUNT(*)
                    FROM rrt_prediction_snapshots p
                    LEFT JOIN rrt_performance_snapshots perf
                      ON perf.meeting_id = p.meeting_id
                     AND perf.model_version = p.model_version
                    WHERE perf.id IS NULL
                ) AS pending_performance_snapshots,
                (
                    SELECT COUNT(*)
                    FROM rrt_runner_factor_snapshots
                    WHERE actual_position IS NOT NULL
                ) AS runner_factor_rows_with_results;
            """
        ) or {}

        latest_processed = fetch_all(
            """
            SELECT
                meeting_id,
                track,
                meeting_date,
                model_version,
                overall_accuracy,
                created_at
            FROM rrt_performance_snapshots
            ORDER BY created_at DESC
            LIMIT 10;
            """
        )

        return {
            "success": True,
            "provider": "PostgreSQL",
            "processor_version": "2.13.0",
            "summary": totals,
            "latest_processed": latest_processed,
            "note": "Automatic results processing uses saved PostgreSQL prediction snapshots and is duplicate-safe.",
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "processor_version": "2.13.0",
            "message": "Failed to build results processor summary.",
            "error": str(error),
        }
