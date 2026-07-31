from typing import Any, Dict, List
import json

from database import execute_sql, fetch_all, fetch_one, postgres_status


SCHEMA_VERSION = "2.19.6"


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
                speed_score NUMERIC(6,2),
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
                weighted_speed NUMERIC(8,4),
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

        execute_sql("ALTER TABLE rrt_runner_factor_snapshots ADD COLUMN IF NOT EXISTS speed_score NUMERIC(6,2);")
        execute_sql("ALTER TABLE rrt_runner_factor_snapshots ADD COLUMN IF NOT EXISTS weighted_speed NUMERIC(8,4);")

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_runner_speed_history (
                id BIGSERIAL PRIMARY KEY,
                meeting_id BIGINT NOT NULL, race_id BIGINT NOT NULL, race_number INTEGER,
                meeting_date DATE, track TEXT, track_condition TEXT, race_class TEXT,
                distance_m INTEGER, official_race_time_seconds NUMERIC(10,4),
                runner_id BIGINT, runner_name TEXT, tab_number INTEGER, position INTEGER,
                margin_lengths NUMERIC(10,3), estimated_runner_time_seconds NUMERIC(10,4),
                average_speed_mps NUMERIC(10,5), normalised_speed_score NUMERIC(6,2),
                source TEXT DEFAULT 'Punting Form Results', created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(meeting_id, race_id, runner_id, tab_number)
            );
            """
        )
        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_runner_speed_profiles (
                runner_id BIGINT PRIMARY KEY, runner_name TEXT, completed_runs INTEGER NOT NULL DEFAULT 0,
                latest_speed_score NUMERIC(6,2), avg_last3_speed_score NUMERIC(6,2),
                avg_last5_speed_score NUMERIC(6,2), best_speed_score NUMERIC(6,2),
                speed_consistency NUMERIC(6,2), latest_run_date DATE, updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        execute_sql("CREATE INDEX IF NOT EXISTS ix_rrt_speed_history_runner ON rrt_runner_speed_history(runner_id, meeting_date DESC);")
        execute_sql("CREATE INDEX IF NOT EXISTS ix_rrt_speed_history_cohort ON rrt_runner_speed_history(distance_m, track_condition, meeting_date);")
        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_speed_backfill_runs (
                id BIGSERIAL PRIMARY KEY,
                batch_id TEXT UNIQUE NOT NULL,
                meeting_limit INTEGER NOT NULL,
                meetings_selected INTEGER NOT NULL DEFAULT 0,
                meetings_processed INTEGER NOT NULL DEFAULT 0,
                runner_rows_saved INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                result_json JSONB NOT NULL DEFAULT '{}'::jsonb
            );
            """
        )
        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_speed_backfill_meetings (
                meeting_id BIGINT PRIMARY KEY,
                result_snapshot_id BIGINT,
                meeting_date DATE,
                outcome TEXT NOT NULL,
                runner_rows_saved INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 1,
                last_batch_id TEXT,
                last_error TEXT,
                processed_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        execute_sql("CREATE INDEX IF NOT EXISTS ix_rrt_speed_backfill_meetings_outcome ON rrt_speed_backfill_meetings(outcome, meeting_date, meeting_id);")
        execute_sql(
            """
            INSERT INTO rrt_speed_backfill_meetings(
                meeting_id, meeting_date, outcome, runner_rows_saved,
                attempt_count, last_batch_id, processed_at, updated_at
            )
            SELECT sh.meeting_id, MAX(sh.meeting_date), 'completed_with_rows', COUNT(*),
                   1, 'pre-2.19.6-migration', NOW(), NOW()
            FROM rrt_runner_speed_history sh
            GROUP BY sh.meeting_id
            ON CONFLICT(meeting_id) DO NOTHING;
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
            CREATE TABLE IF NOT EXISTS rrt_model_weight_sets (
                id SERIAL PRIMARY KEY,
                model_version TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                weights_json JSONB NOT NULL,
                source TEXT,
                notes TEXT,
                activated_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

        execute_sql("ALTER TABLE rrt_model_weight_sets ADD COLUMN IF NOT EXISTS promoted_by_cycle_id TEXT;")
        execute_sql("ALTER TABLE rrt_model_weight_sets ADD COLUMN IF NOT EXISTS promotion_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
        execute_sql("ALTER TABLE rrt_model_weight_sets ADD COLUMN IF NOT EXISTS automatic_promotion BOOLEAN DEFAULT FALSE;")

        execute_sql(
            """
            UPDATE rrt_model_weight_sets
            SET status = 'Rollback'
            WHERE status = 'Active' AND model_version <> '2.19.6';
            """
        )
        execute_sql(
            """
            INSERT INTO rrt_model_weight_sets
                (model_version,status,weights_json,source,notes,activated_at,automatic_promotion)
            VALUES
              ('2.18.4','Archive',%s::jsonb,'RRT Predictor','Earlier calibrated production baseline.',NULL,FALSE),
              ('2.19.5b','Rollback',%s::jsonb,'RRT Predictor','Immediate rollback baseline before v2.19.6 Speed activation.',NULL,FALSE),
              ('2.19.6','Active',%s::jsonb,'RRT Predictor','Normalised Speed active at 10%%; all factor weights rebalanced to 100%%. Automatic promotion remains disabled.',NOW(),FALSE)
            ON CONFLICT (model_version) DO UPDATE SET
              status=EXCLUDED.status,
              weights_json=EXCLUDED.weights_json,
              source=EXCLUDED.source,
              notes=EXCLUDED.notes,
              automatic_promotion=EXCLUDED.automatic_promotion,
              activated_at=CASE WHEN EXCLUDED.status='Active' THEN NOW() ELSE rrt_model_weight_sets.activated_at END;
            """,
            (
                json.dumps({'last10': 15, 'win_place': 9, 'track_record': 8, 'distance_record': 8, 'track_distance': 8, 'track_condition': 8, 'trainer': 7, 'jockey': 7, 'trainer_jockey': 9, 'barrier': 4, 'weight': 3, 'market': 14, 'speed': 0}),
                json.dumps({'last10': 15, 'win_place': 9, 'track_record': 8, 'distance_record': 8, 'track_distance': 8, 'track_condition': 8, 'trainer': 7, 'jockey': 7, 'trainer_jockey': 9, 'barrier': 4, 'weight': 3, 'market': 14, 'speed': 0}),
                json.dumps({'last10': 14, 'win_place': 8, 'track_record': 7, 'distance_record': 7, 'track_distance': 7, 'track_condition': 7, 'trainer': 6, 'jockey': 6, 'trainer_jockey': 8, 'barrier': 4, 'weight': 2, 'market': 14, 'speed': 10}),
            ),
        )

        execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rrt_weight_promotion_audit (
                id SERIAL PRIMARY KEY,
                promotion_id TEXT UNIQUE NOT NULL,
                cycle_id TEXT,
                from_weight_set TEXT,
                to_weight_set TEXT,
                decision TEXT NOT NULL,
                gate_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                previous_weights_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                proposed_weights_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                applied BOOLEAN DEFAULT FALSE,
                rollback_available BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )

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
                "2.19.6",
                "RRT Predictor v2.19.6 production activation of Normalised Speed at 10% with rebalanced 100% factor weights.",
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
                "rrt_model_weight_sets",
                "rrt_weight_promotion_audit",
                "rrt_runner_speed_history",
                "rrt_runner_speed_profiles",
                "rrt_speed_backfill_runs",
                "rrt_speed_backfill_meetings",
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
        weight_set_count = fetch_one("SELECT COUNT(*) AS count FROM rrt_model_weight_sets;")

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
                "model_weight_sets": int((weight_set_count or {}).get("count") or 0),
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
                json.dumps(prediction_snapshot, default=str),
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
    model_version: str = "2.19.6",
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
                json.dumps(results_snapshot, default=str),
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
                json.dumps(performance_snapshot, default=str),
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
                    market_score, speed_score,
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
                    weighted_market, weighted_speed,
                    factor_json
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
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
                    speed_score = EXCLUDED.speed_score,
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
                    weighted_speed = EXCLUDED.weighted_speed,
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
                    breakdown.get("speed_rating"),
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
                    weighted.get("speed_rating"),
                    json.dumps(runner, default=str),
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



def _parse_official_time_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = text.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(text)
    except Exception:
        return None


def _seconds_per_length(distance_m: Any) -> float:
    distance = _safe_float_or_none(distance_m) or 1200.0
    if distance <= 1000: return 0.145
    if distance <= 1400: return 0.155
    if distance <= 1800: return 0.165
    if distance <= 2400: return 0.175
    return 0.185


def save_speed_ratings_from_results(results_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Persist race-time-derived runner speed figures. No sectional or in-run data is used."""
    try:
        meeting_id = results_snapshot.get("meeting_id")
        meeting_date = results_snapshot.get("meeting_date")
        track = results_snapshot.get("track")
        saved = 0
        runners_seen = set()
        for race in results_snapshot.get("races") or []:
            race_id = race.get("race_id")
            distance = _safe_float_or_none(race.get("distance_m"))
            official_seconds = _parse_official_time_seconds(race.get("official_race_time"))
            if not meeting_id or not race_id or not distance or not official_seconds or official_seconds <= 0:
                continue
            spl = _seconds_per_length(distance)
            # Race quality component compares the official pace with existing comparable races.
            cohort = fetch_one("""
                SELECT AVG(official_race_time_seconds) AS avg_time, STDDEV_POP(official_race_time_seconds) AS sd_time
                FROM rrt_runner_speed_history
                WHERE distance_m BETWEEN %s AND %s AND UPPER(COALESCE(track_condition,'')) = UPPER(%s)
                  AND position = 1;
            """, (int(distance)-100, int(distance)+100, race.get("track_condition") or "")) or {}
            avg_time = _safe_float_or_none(cohort.get("avg_time"))
            sd_time = _safe_float_or_none(cohort.get("sd_time"))
            pace_quality = 50.0
            if avg_time and sd_time and sd_time > 0.05:
                pace_quality = max(20.0, min(80.0, 50.0 + ((avg_time - official_seconds) / sd_time) * 10.0))
            for runner in race.get("runners") or []:
                runner_id = runner.get("runner_id")
                tab = runner.get("tab_number")
                margin = _safe_float_or_none(runner.get("margin")) or 0.0
                estimated = official_seconds + max(0.0, margin) * spl
                speed_mps = distance / estimated if estimated > 0 else 0.0
                relative = max(0.0, min(100.0, 100.0 - max(0.0, margin) * 3.0))
                speed_score = round((relative * 0.70) + (pace_quality * 0.30), 2)
                execute_sql("""
                    INSERT INTO rrt_runner_speed_history(
                        meeting_id,race_id,race_number,meeting_date,track,track_condition,race_class,distance_m,
                        official_race_time_seconds,runner_id,runner_name,tab_number,position,margin_lengths,
                        estimated_runner_time_seconds,average_speed_mps,normalised_speed_score
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(meeting_id,race_id,runner_id,tab_number) DO UPDATE SET
                        position=EXCLUDED.position,margin_lengths=EXCLUDED.margin_lengths,
                        estimated_runner_time_seconds=EXCLUDED.estimated_runner_time_seconds,
                        average_speed_mps=EXCLUDED.average_speed_mps,
                        normalised_speed_score=EXCLUDED.normalised_speed_score,updated_at=NOW();
                """, (meeting_id,race_id,race.get("race_number"),meeting_date,track,race.get("track_condition"),
                      race.get("race_class"),int(distance),official_seconds,runner_id,runner.get("runner"),tab,
                      runner.get("position"),margin,estimated,speed_mps,speed_score))
                if runner_id:
                    runners_seen.add(int(runner_id))
                saved += 1
        for runner_id in runners_seen:
            rows = fetch_all("""SELECT runner_name,meeting_date,normalised_speed_score FROM rrt_runner_speed_history
                WHERE runner_id=%s AND normalised_speed_score IS NOT NULL ORDER BY meeting_date DESC, id DESC LIMIT 20;""", (runner_id,))
            scores = [float(r.get("normalised_speed_score")) for r in rows if r.get("normalised_speed_score") is not None]
            if not scores: continue
            avg3 = sum(scores[:3])/len(scores[:3]); avg5 = sum(scores[:5])/len(scores[:5])
            consistency = max(0.0, 100.0 - ((sum((x-avg5)**2 for x in scores[:5])/len(scores[:5]))**0.5)*2.0)
            execute_sql("""INSERT INTO rrt_runner_speed_profiles(runner_id,runner_name,completed_runs,latest_speed_score,
                avg_last3_speed_score,avg_last5_speed_score,best_speed_score,speed_consistency,latest_run_date,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) ON CONFLICT(runner_id) DO UPDATE SET
                runner_name=EXCLUDED.runner_name,completed_runs=EXCLUDED.completed_runs,latest_speed_score=EXCLUDED.latest_speed_score,
                avg_last3_speed_score=EXCLUDED.avg_last3_speed_score,avg_last5_speed_score=EXCLUDED.avg_last5_speed_score,
                best_speed_score=EXCLUDED.best_speed_score,speed_consistency=EXCLUDED.speed_consistency,
                latest_run_date=EXCLUDED.latest_run_date,updated_at=NOW();""",
                (runner_id,rows[0].get("runner_name"),len(scores),scores[0],round(avg3,2),round(avg5,2),max(scores),round(consistency,2),rows[0].get("meeting_date")))
        return {"success":True,"provider":"PostgreSQL","speed_version":"2.19.6","meeting_id":meeting_id,"saved_runner_times":saved,"updated_profiles":len(runners_seen),"in_run_used":False}
    except Exception as error:
        return {"success":False,"provider":"PostgreSQL","speed_version":"2.19.6","error":str(error)}


def backfill_speed_ratings_from_saved_results(limit: int = 5) -> Dict[str, Any]:
    """Process one bounded and resumable batch of saved result meetings.

    Every selected meeting receives a terminal audit outcome. Meetings with no
    eligible official-time data are marked completed_no_eligible_results and are
    not repeatedly selected on later runs. Retryable failures remain visible but
    are not automatically retried by the normal backfill path.
    """
    from datetime import datetime, timezone
    import gc
    import uuid

    meeting_limit = max(1, min(int(limit or 5), 10))
    batch_id = f"speed-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    started = datetime.now(timezone.utc)

    rows = fetch_all(
        """
        SELECT rs.id, rs.meeting_id, rs.meeting_date, rs.result_json
        FROM rrt_results_snapshots rs
        WHERE NOT EXISTS (
            SELECT 1 FROM rrt_speed_backfill_meetings bm
            WHERE bm.meeting_id = rs.meeting_id
        )
        ORDER BY rs.meeting_date ASC NULLS LAST, rs.id ASC
        LIMIT %s;
        """,
        (meeting_limit,),
    )

    processed = 0
    saved = 0
    no_eligible = 0
    failures: List[Dict[str, Any]] = []
    outcomes: List[Dict[str, Any]] = []

    for row in rows:
        meeting_id = row.get("meeting_id")
        payload = row.get("result_json") or {}
        outcome = "failed_terminal"
        row_saved = 0
        error_text = None

        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                raise ValueError("Stored result snapshot is not a JSON object.")

            payload.setdefault("meeting_id", meeting_id)
            payload.setdefault("meeting_date", row.get("meeting_date"))
            result = save_speed_ratings_from_results(payload)

            if not result.get("success"):
                raise RuntimeError(result.get("error") or "Speed Rating processing failed.")

            row_saved = int(result.get("saved_runner_times") or 0)
            if row_saved > 0:
                outcome = "completed_with_rows"
                saved += row_saved
            else:
                outcome = "completed_no_eligible_results"
                no_eligible += 1
            processed += 1

        except (json.JSONDecodeError, ValueError) as error:
            error_text = str(error)
            failures.append({"meeting_id": meeting_id, "outcome": "failed_terminal", "error": error_text})
        except Exception as error:
            outcome = "failed_retryable"
            error_text = str(error)
            failures.append({"meeting_id": meeting_id, "outcome": outcome, "error": error_text})

        execute_sql(
            """
            INSERT INTO rrt_speed_backfill_meetings(
                meeting_id, result_snapshot_id, meeting_date, outcome,
                runner_rows_saved, attempt_count, last_batch_id, last_error,
                processed_at, updated_at
            ) VALUES(%s,%s,%s,%s,%s,1,%s,%s,NOW(),NOW())
            ON CONFLICT(meeting_id) DO UPDATE SET
                result_snapshot_id=EXCLUDED.result_snapshot_id,
                meeting_date=EXCLUDED.meeting_date,
                outcome=EXCLUDED.outcome,
                runner_rows_saved=EXCLUDED.runner_rows_saved,
                attempt_count=rrt_speed_backfill_meetings.attempt_count + 1,
                last_batch_id=EXCLUDED.last_batch_id,
                last_error=EXCLUDED.last_error,
                processed_at=NOW(),
                updated_at=NOW();
            """,
            (meeting_id, row.get("id"), row.get("meeting_date"), outcome, row_saved, batch_id, error_text),
        )
        outcomes.append({"meeting_id": meeting_id, "outcome": outcome, "runner_rows_saved": row_saved})
        payload = None
        gc.collect()

    remaining_row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM rrt_results_snapshots rs
        WHERE NOT EXISTS (
            SELECT 1 FROM rrt_speed_backfill_meetings bm
            WHERE bm.meeting_id = rs.meeting_id
        );
        """
    ) or {}
    remaining = int(remaining_row.get("count") or 0)
    completed = datetime.now(timezone.utc)
    elapsed = round((completed - started).total_seconds(), 3)
    status = "completed" if not failures else "completed_with_failures"

    response = {
        "success": not failures,
        "provider": "PostgreSQL",
        "speed_version": "2.19.6",
        "batch_id": batch_id,
        "status": status,
        "meeting_limit": meeting_limit,
        "meetings_selected": len(rows),
        "meetings_processed": processed,
        "meetings_no_eligible_results": no_eligible,
        "runner_speed_rows_saved": saved,
        "remaining_meetings": remaining,
        "backfill_complete": remaining == 0,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "elapsed_seconds": elapsed,
        "outcomes": outcomes,
        "failures": failures[:20],
        "resumable": True,
        "in_run_used": False,
    }

    execute_sql(
        """
        INSERT INTO rrt_speed_backfill_runs(
            batch_id, meeting_limit, meetings_selected, meetings_processed,
            runner_rows_saved, failure_count, status, started_at, completed_at, result_json
        ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb);
        """,
        (
            batch_id, meeting_limit, len(rows), processed, saved, len(failures),
            status, started, completed, json.dumps(response, default=str),
        ),
    )
    return response



def integrate_speed_ratings_into_factor_snapshots() -> Dict[str, Any]:
    """Populate historical factor rows with leakage-safe pre-race Speed Ratings.

    A runner factor row is enriched only from official-time speed history dated
    strictly before that row's meeting date. Runner ID is the primary join key;
    normalised runner name is used only when the factor row has no runner ID.
    Production weights are not changed and weighted_speed remains zero.
    """
    try:
        before = fetch_one(
            """SELECT COUNT(*) AS total_rows,
                      COUNT(*) FILTER (WHERE speed_score IS NOT NULL) AS populated_rows
               FROM rrt_runner_factor_snapshots;"""
        ) or {}

        execute_sql(
            """
            WITH enriched AS (
                SELECT
                    fs.id,
                    ROUND((
                        COALESCE(s.avg_last3, 50) * 0.55
                      + COALESCE(s.avg_last5, 50) * 0.25
                      + COALESCE(s.best_score, 50) * 0.10
                      + COALESCE(s.consistency, 50) * 0.10
                    )::numeric, 2) AS pre_race_speed_score,
                    s.prior_run_count
                FROM rrt_runner_factor_snapshots fs
                JOIN LATERAL (
                    SELECT
                        COUNT(*)::integer AS prior_run_count,
                        AVG(normalised_speed_score) FILTER (WHERE rn <= 3) AS avg_last3,
                        AVG(normalised_speed_score) AS avg_last5,
                        MAX(normalised_speed_score) AS best_score,
                        GREATEST(0, LEAST(100, 100 - COALESCE(STDDEV_POP(normalised_speed_score), 0) * 2)) AS consistency
                    FROM (
                        SELECT
                            h.normalised_speed_score,
                            ROW_NUMBER() OVER (ORDER BY h.meeting_date DESC, h.id DESC) AS rn
                        FROM rrt_runner_speed_history h
                        WHERE h.normalised_speed_score IS NOT NULL
                          AND h.meeting_date < fs.meeting_date
                          AND (
                                (fs.runner_id IS NOT NULL AND fs.runner_id > 0 AND h.runner_id = fs.runner_id)
                             OR ((fs.runner_id IS NULL OR fs.runner_id <= 0)
                                 AND UPPER(TRIM(COALESCE(h.runner_name, ''))) = UPPER(TRIM(COALESCE(fs.runner_name, ''))))
                          )
                        ORDER BY h.meeting_date DESC, h.id DESC
                        LIMIT 5
                    ) prior_runs
                ) s ON s.prior_run_count > 0
                WHERE fs.actual_position IS NOT NULL
                  AND fs.meeting_date IS NOT NULL
            )
            UPDATE rrt_runner_factor_snapshots fs
            SET speed_score = enriched.pre_race_speed_score,
                weighted_speed = 0,
                factor_json = jsonb_set(
                    jsonb_set(COALESCE(fs.factor_json, '{}'::jsonb),
                              '{score_breakdown,speed_rating}',
                              to_jsonb(enriched.pre_race_speed_score), true),
                    '{speed_integration}',
                    jsonb_build_object(
                        'version', '2.19.6',
                        'method', 'pre_race_official_time_history',
                        'prior_runs_used', enriched.prior_run_count,
                        'leakage_safe', true,
                        'in_run_used', false
                    ), true
                ),
                updated_at = NOW()
            FROM enriched
            WHERE fs.id = enriched.id;
            """
        )

        after = fetch_one(
            """SELECT COUNT(*) AS total_rows,
                      COUNT(*) FILTER (WHERE speed_score IS NOT NULL) AS populated_rows,
                      COUNT(*) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL) AS completed_rows_with_speed,
                      COUNT(DISTINCT meeting_id) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL) AS completed_meetings_with_speed,
                      MIN(meeting_date) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL) AS first_speed_date,
                      MAX(meeting_date) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL) AS latest_speed_date,
                      ROUND(AVG(speed_score) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL), 2) AS avg_pre_race_speed_score
               FROM rrt_runner_factor_snapshots;"""
        ) or {}

        return {
            "success": True,
            "provider": "PostgreSQL",
            "speed_version": "2.19.6",
            "analysis_only": True,
            "prediction_model_changed": False,
            "production_speed_weight": 0,
            "before": before,
            "after": after,
            "rows_enriched_this_request": max(
                0,
                int(after.get("populated_rows") or 0) - int(before.get("populated_rows") or 0),
            ),
            "join_policy": "runner_id_primary_name_fallback_only_when_runner_id_missing",
            "history_cutoff": "strictly_before_meeting_date",
            "leakage_safe": True,
            "in_run_used": False,
        }
    except Exception as error:
        return {
            "success": False,
            "provider": "PostgreSQL",
            "speed_version": "2.19.6",
            "analysis_only": True,
            "error": str(error),
        }


def get_speed_rating_summary() -> Dict[str, Any]:
    totals = fetch_one("""SELECT COUNT(*) AS history_rows,COUNT(DISTINCT runner_id) AS runner_count,
        COUNT(DISTINCT meeting_id) AS meeting_count,COUNT(DISTINCT race_id) AS race_count,
        ROUND(AVG(normalised_speed_score),2) AS avg_speed_score,MIN(meeting_date) AS first_date,MAX(meeting_date) AS latest_date
        FROM rrt_runner_speed_history;""") or {}
    profiles = fetch_one("SELECT COUNT(*) AS profile_count,COUNT(*) FILTER(WHERE completed_runs>=3) AS profiles_with_3_runs FROM rrt_runner_speed_profiles;") or {}
    pending = fetch_one("""SELECT COUNT(*) AS count FROM rrt_results_snapshots rs WHERE NOT EXISTS
        (SELECT 1 FROM rrt_speed_backfill_meetings bm WHERE bm.meeting_id=rs.meeting_id);""") or {}
    outcome_counts = fetch_all("""SELECT outcome, COUNT(*) AS meeting_count, COALESCE(SUM(runner_rows_saved),0) AS runner_rows_saved
        FROM rrt_speed_backfill_meetings GROUP BY outcome ORDER BY outcome;""")
    latest_batch = fetch_one("""SELECT batch_id,meeting_limit,meetings_selected,meetings_processed,runner_rows_saved,
        failure_count,status,started_at,completed_at FROM rrt_speed_backfill_runs ORDER BY id DESC LIMIT 1;""") or {}
    integration = fetch_one("""SELECT COUNT(*) AS factor_rows,
        COUNT(*) FILTER (WHERE actual_position IS NOT NULL) AS completed_factor_rows,
        COUNT(*) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL) AS completed_rows_with_speed,
        COUNT(DISTINCT meeting_id) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL) AS completed_meetings_with_speed,
        ROUND(AVG(speed_score) FILTER (WHERE actual_position IS NOT NULL AND speed_score IS NOT NULL),2) AS avg_pre_race_speed_score
        FROM rrt_runner_factor_snapshots;""") or {}
    remaining = int(pending.get("count") or 0)
    return {"success":True,"speed_version":"2.19.6","analysis_only":True,"totals":totals,"profiles":profiles,"integration":integration,
            "backfill":{"remaining_meetings":remaining,"complete":remaining==0,"latest_batch":latest_batch,
                        "meeting_outcomes":outcome_counts},
            "resumable":True,"in_run_used":False}


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
                ROUND(AVG(market_score), 2) AS avg_market_score,
                ROUND(AVG(speed_score), 2) AS avg_speed_score
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
