from typing import Any, Dict, List, Optional, Tuple
from database import fetch_all, fetch_one

LEARNING_DATASET_VERSION = "2.18.0"
MODEL_VERSION = "2.18.0"


def _int(value: Any, default: int = 0) -> int:
    try:
        return default if value is None else int(value)
    except Exception:
        return default


def get_learning_dataset_audit() -> Dict[str, Any]:
    archive = fetch_one("""
        SELECT COUNT(*) AS meeting_count,
               COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER),0) AS race_count,
               COUNT(DISTINCT track) AS track_count,
               COUNT(DISTINCT meeting_date) AS date_count,
               MIN(meeting_date) AS min_meeting_date,
               MAX(meeting_date) AS max_meeting_date
        FROM rrt_performance_snapshots;
    """) or {}
    factors = fetch_one("""
        SELECT COUNT(*) AS runner_count,
               COUNT(DISTINCT meeting_id) AS meeting_count,
               COUNT(DISTINCT (meeting_id, COALESCE(race_id, race_number))) AS race_count,
               COUNT(*) FILTER (WHERE capture_scope = 'full_field') AS full_field_runner_count,
               COUNT(DISTINCT (meeting_id, COALESCE(race_id, race_number))) FILTER (WHERE capture_scope = 'full_field') AS full_field_race_count,
               COUNT(DISTINCT meeting_id) FILTER (WHERE capture_scope = 'full_field') AS full_field_meeting_count,
               MIN(meeting_date) FILTER (WHERE capture_scope = 'full_field') AS min_meeting_date,
               MAX(meeting_date) FILTER (WHERE capture_scope = 'full_field') AS max_meeting_date
        FROM rrt_runner_factor_snapshots
        WHERE actual_position IS NOT NULL;
    """) or {}
    archive_meetings = _int(archive.get("meeting_count"))
    valid_meetings = _int(factors.get("full_field_meeting_count"))
    archive_races = _int(archive.get("race_count"))
    valid_races = _int(factors.get("full_field_race_count"))
    return {
        "success": True,
        "dataset_version": LEARNING_DATASET_VERSION,
        "archive": archive,
        "prediction_comparison": {
            "meeting_count": valid_meetings,
            "race_count": valid_races,
            "runner_count": _int(factors.get("full_field_runner_count")),
            "min_meeting_date": factors.get("min_meeting_date"),
            "max_meeting_date": factors.get("max_meeting_date"),
            "meeting_coverage_pct": round(valid_meetings / archive_meetings * 100, 2) if archive_meetings else 0.0,
            "race_coverage_pct": round(valid_races / archive_races * 100, 2) if archive_races else 0.0,
        },
        "legacy_partial_capture": {
            "runner_count": max(0, _int(factors.get("runner_count")) - _int(factors.get("full_field_runner_count"))),
            "race_count": max(0, _int(factors.get("race_count")) - valid_races),
            "meeting_count": max(0, _int(factors.get("meeting_count")) - valid_meetings),
        },
        "rules": {
            "pre_race_inputs_only": True,
            "official_results_used_as_labels_only": True,
            "full_field_capture_required": True,
            "legacy_selected_runner_rows_excluded": True,
        },
    }


def load_learning_rows(min_meeting_date: Optional[str] = None, max_meeting_date: Optional[str] = None, model_version: Optional[str] = None) -> List[Dict[str, Any]]:
    clauses = [
        "actual_position IS NOT NULL",
        "race_number IS NOT NULL",
        "capture_scope = 'full_field'",
    ]
    params: List[Any] = []
    if min_meeting_date:
        clauses.append("meeting_date >= %s")
        params.append(min_meeting_date)
    if max_meeting_date:
        clauses.append("meeting_date <= %s")
        params.append(max_meeting_date)
    if model_version:
        clauses.append("model_version = %s")
        params.append(model_version)
    return fetch_all(f"""
        SELECT meeting_id, model_version, track, meeting_date, race_id, race_number,
               runner_key, runner_name, tab_number, final_score, confidence,
               market_price, market_rank, prediction_rank, field_size, capture_scope,
               actual_position, actual_price, hit_win, hit_place,
               last10_score, win_place_score, track_record_score,
               distance_record_score, track_distance_record_score,
               track_condition_score, trainer_score, jockey_score,
               trainer_jockey_score, barrier_score, weight_score, market_score,
               factor_json
        FROM rrt_runner_factor_snapshots
        WHERE {' AND '.join(clauses)}
        ORDER BY meeting_date, meeting_id, race_number, prediction_rank NULLS LAST, runner_key;
    """, tuple(params))


def group_learning_rows(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any], List[Dict[str, Any]]]:
    grouped: Dict[Tuple[Any, Any], List[Dict[str, Any]]] = {}
    for row in rows:
        key = (row.get("meeting_id"), row.get("race_id") or row.get("race_number"))
        grouped.setdefault(key, []).append(row)
    return grouped
