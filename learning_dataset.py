from typing import Any, Dict, List, Optional, Tuple
import json

from database import fetch_all, fetch_one

LEARNING_DATASET_VERSION = "2.18.2"
MODEL_VERSION = "2.18.2"


def _int(value: Any, default: int = 0) -> int:
    try:
        return default if value is None else int(value)
    except Exception:
        return default


def _json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}




def _walk_json(value: Any, path: str = "$"):
    """Yield every node in a JSON document with its path."""
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield from _walk_json(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield from _walk_json(child, child_path)


def _looks_like_runner(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    keys = {str(k).lower() for k in item.keys()}
    identity = bool(keys & {"runner", "runner_name", "horse_name", "name", "tab_number", "number", "runner_id"})
    scoring = bool(keys & {"score", "final_score", "confidence", "score_breakdown", "weighted_breakdown", "factor_capture", "market_rank"})
    race_context = bool(keys & {"race_id", "race_number", "race_no", "race"})
    return identity and (scoring or race_context)


def _runner_list_candidates(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for path, value in _walk_json(snapshot):
        if not isinstance(value, list) or not value:
            continue
        dict_items = [item for item in value if isinstance(item, dict)]
        runner_items = [item for item in dict_items if _looks_like_runner(item)]
        if not runner_items:
            continue
        race_keys = set()
        score_rows = 0
        factor_rows = 0
        for item in runner_items:
            race_key = item.get("race_id") or item.get("race_number") or item.get("race_no") or item.get("race")
            if race_key not in (None, ""):
                race_keys.add(str(race_key))
            if any(item.get(key) is not None for key in ("score", "final_score", "confidence", "market_rank")):
                score_rows += 1
            if item.get("score_breakdown") or item.get("weighted_breakdown") or item.get("factor_capture"):
                factor_rows += 1
        candidates.append({
            "path": path,
            "list_count": len(value),
            "runner_count": len(runner_items),
            "race_count": len(race_keys),
            "scored_runner_count": score_rows,
            "factor_runner_count": factor_rows,
            "sample_keys": sorted({str(k) for item in runner_items[:5] for k in item.keys()})[:40],
        })
    return sorted(candidates, key=lambda item: (item.get("runner_count", 0), item.get("scored_runner_count", 0)), reverse=True)


def _top_level_profile(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "top_level_keys": sorted(str(key) for key in snapshot.keys()),
        "has_predictions": isinstance(snapshot.get("predictions"), dict),
        "has_factor_capture": isinstance(snapshot.get("factor_capture"), dict),
        "has_races": isinstance(snapshot.get("races"), list),
        "has_meeting": isinstance(snapshot.get("meeting"), dict),
        "prediction_type": snapshot.get("prediction_type"),
        "model_version": snapshot.get("model_version"),
    }


def _classify_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not snapshot:
        return {"classification": "INVALID", "reason": "Prediction JSON is empty or invalid.", "candidates": []}
    candidates = _runner_list_candidates(snapshot)
    if not candidates:
        return {
            "classification": "UNKNOWN_FORMAT",
            "reason": "No runner-like lists were detected in the stored JSON.",
            "candidates": [],
        }
    best = candidates[0]
    runner_count = _int(best.get("runner_count"))
    race_count = _int(best.get("race_count"))
    scored_count = _int(best.get("scored_runner_count"))
    factor_count = _int(best.get("factor_runner_count"))
    path = str(best.get("path") or "")
    if runner_count >= 8 and race_count >= 2 and scored_count >= max(4, int(runner_count * 0.7)):
        classification = "RECONSTRUCTABLE"
        reason = f"Detected {runner_count} scored runner rows across {race_count} races at {path}."
    elif runner_count >= 8 and factor_count >= max(4, int(runner_count * 0.5)):
        classification = "RECONSTRUCTABLE"
        reason = f"Detected {runner_count} factor-bearing runner rows at {path}."
    elif runner_count >= 8 and (path.endswith('.runners') or '.races' in path):
        classification = "POSSIBLE_FULL_FIELD"
        reason = f"Detected a large runner list ({runner_count}) at {path}, but scoring coverage needs validation."
    else:
        classification = "SELECTED_ONLY"
        reason = f"Largest detected runner list contains {runner_count} rows at {path}; this appears to be selections rather than the full meeting field."
    return {
        "classification": classification,
        "reason": reason,
        "best_candidate": best,
        "candidate_count": len(candidates),
        "candidates": candidates[:10],
    }


def inspect_prediction_archive(limit: int = 1000, include_samples: bool = True) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT meeting_id, model_version, track, meeting_date, prediction_type, prediction_json, created_at
        FROM rrt_prediction_snapshots
        ORDER BY meeting_date, meeting_id
        LIMIT %s;
        """,
        (max(1, min(limit, 10000)),),
    )
    classifications = {
        "RECONSTRUCTABLE": 0,
        "POSSIBLE_FULL_FIELD": 0,
        "SELECTED_ONLY": 0,
        "UNKNOWN_FORMAT": 0,
        "INVALID": 0,
    }
    path_rollup: Dict[str, Dict[str, Any]] = {}
    format_rollup: Dict[str, int] = {}
    inspected: List[Dict[str, Any]] = []
    for row in rows:
        snapshot = _json_object(row.get("prediction_json"))
        classified = _classify_snapshot(snapshot)
        label = classified.get("classification") or "UNKNOWN_FORMAT"
        classifications[label] = classifications.get(label, 0) + 1
        profile = _top_level_profile(snapshot)
        format_key = "|".join(profile.get("top_level_keys") or [])
        format_rollup[format_key] = format_rollup.get(format_key, 0) + 1
        best = classified.get("best_candidate") or {}
        path = best.get("path")
        if path:
            entry = path_rollup.setdefault(path, {"path": path, "snapshot_count": 0, "max_runner_count": 0, "max_race_count": 0, "max_scored_runner_count": 0})
            entry["snapshot_count"] += 1
            entry["max_runner_count"] = max(entry["max_runner_count"], _int(best.get("runner_count")))
            entry["max_race_count"] = max(entry["max_race_count"], _int(best.get("race_count")))
            entry["max_scored_runner_count"] = max(entry["max_scored_runner_count"], _int(best.get("scored_runner_count")))
        item = {
            "meeting_id": row.get("meeting_id"),
            "meeting_date": row.get("meeting_date"),
            "track": row.get("track"),
            "model_version": row.get("model_version"),
            "prediction_type": row.get("prediction_type"),
            "classification": label,
            "reason": classified.get("reason"),
            "top_level_profile": profile,
            "best_candidate": best,
            "candidate_count": classified.get("candidate_count", 0),
        }
        if include_samples:
            item["candidate_samples"] = classified.get("candidates") or []
        inspected.append(item)
    formats = [
        {"format_id": index + 1, "snapshot_count": count, "top_level_keys": key.split("|") if key else []}
        for index, (key, count) in enumerate(sorted(format_rollup.items(), key=lambda pair: pair[1], reverse=True))
    ]
    reconstructable = classifications.get("RECONSTRUCTABLE", 0) + classifications.get("POSSIBLE_FULL_FIELD", 0)
    return {
        "success": True,
        "dataset_version": LEARNING_DATASET_VERSION,
        "report": "prediction_archive_inspection",
        "snapshot_count": len(rows),
        "summary": {
            **classifications,
            "reconstructable_or_possible_count": reconstructable,
            "selected_only_or_unusable_count": classifications.get("SELECTED_ONLY", 0) + classifications.get("UNKNOWN_FORMAT", 0) + classifications.get("INVALID", 0),
            "format_count": len(formats),
        },
        "formats": formats[:20],
        "runner_paths": sorted(path_rollup.values(), key=lambda item: item.get("snapshot_count", 0), reverse=True)[:30],
        "snapshots": inspected,
        "note": "Inspection is read-only. It does not alter prediction snapshots, runner factors, results, replay history or production weights.",
    }


def _prediction_snapshot_profile() -> Dict[str, Any]:
    rows = fetch_all("""
        SELECT meeting_id, model_version, meeting_date, prediction_json
        FROM rrt_prediction_snapshots
        ORDER BY meeting_date, meeting_id;
    """)
    total = len(rows)
    full_field = 0
    selected_only = 0
    empty = 0
    full_field_runner_count = 0
    full_field_race_count = 0
    full_field_meetings = set()
    selected_only_meetings = set()
    for row in rows:
        snapshot = _json_object(row.get("prediction_json"))
        capture = snapshot.get("factor_capture") or {}
        runners = capture.get("runners") or []
        scope = str(capture.get("capture_scope") or "").strip().lower()
        if scope == "full_field" and runners:
            full_field += 1
            full_field_meetings.add(row.get("meeting_id"))
            full_field_runner_count += len(runners)
            full_field_race_count += _int(capture.get("race_count")) or len({(r.get("race_id") or r.get("race_number")) for r in runners if isinstance(r, dict)})
        elif runners or (snapshot.get("predictions") or {}):
            selected_only += 1
            selected_only_meetings.add(row.get("meeting_id"))
        else:
            empty += 1
    return {
        "prediction_snapshot_count": total,
        "full_field_snapshot_count": full_field,
        "selected_only_snapshot_count": selected_only,
        "empty_snapshot_count": empty,
        "full_field_snapshot_meeting_count": len(full_field_meetings),
        "selected_only_snapshot_meeting_count": len(selected_only_meetings),
        "full_field_snapshot_runner_count": full_field_runner_count,
        "full_field_snapshot_race_count": full_field_race_count,
    }


def get_learning_dataset_audit() -> Dict[str, Any]:
    archive = fetch_one("""
        SELECT COUNT(*) AS meeting_count,
               COALESCE(SUM((performance_json->'results_summary'->>'race_count')::INTEGER),0) AS race_count,
               COUNT(DISTINCT track) AS track_count,
               COUNT(DISTINCT meeting_date) AS date_count,
               MIN(meeting_date) AS min_meeting_date,
               MAX(meeting_date) AS max_meeting_date,
               ROUND(AVG(overall_accuracy),2) AS avg_overall_accuracy,
               ROUND(AVG(top_win_strike_rate),2) AS avg_top_win_strike_rate,
               ROUND(AVG(each_way_strike_rate),2) AS avg_each_way_strike_rate,
               ROUND(AVG(top_win_strike_rate - pf_ai_top_win_strike_rate),2) AS avg_rrt_vs_pf_ai_gap
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
    snapshot_profile = _prediction_snapshot_profile()
    missing_prediction_snapshots = max(0, archive_meetings - _int(snapshot_profile.get("prediction_snapshot_count")))
    result_snapshot_count = _int((fetch_one("SELECT COUNT(*) AS count FROM rrt_results_snapshots;") or {}).get("count"))
    missing_result_matches = max(0, archive_meetings - result_snapshot_count)
    return {
        "success": True,
        "dataset_version": LEARNING_DATASET_VERSION,
        "performance_dataset": archive,
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
        "reconstruction": {
            **snapshot_profile,
            "reconstructed_full_field_meetings": valid_meetings,
            "missing_prediction_snapshots": missing_prediction_snapshots,
            "missing_result_matches": missing_result_matches,
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
            "historical_rows_are_never_fabricated": True,
        },
    }


def reconstruct_learning_dataset(limit: int = 1000, dry_run: bool = False) -> Dict[str, Any]:
    """Rebuild full-field factor rows only where the stored prediction snapshot contains them.

    This deliberately does not infer missing runners from result data or selected-runner rows.
    """
    rows = fetch_all("""
        SELECT p.meeting_id, p.model_version, p.track, p.meeting_date, p.prediction_json,
               r.result_json
        FROM rrt_prediction_snapshots p
        LEFT JOIN rrt_results_snapshots r ON r.meeting_id = p.meeting_id
        ORDER BY p.meeting_date, p.meeting_id
        LIMIT %s;
    """, (max(1, min(limit, 10000)),))

    summary = {
        "snapshot_count": len(rows),
        "eligible_full_field_snapshots": 0,
        "reconstructed_meetings": 0,
        "saved_runner_rows": 0,
        "results_matched_meetings": 0,
        "selected_only_excluded": 0,
        "missing_results": 0,
        "invalid_snapshots": 0,
        "errors": [],
    }
    if dry_run:
        for row in rows:
            snapshot = _json_object(row.get("prediction_json"))
            capture = snapshot.get("factor_capture") or {}
            if str(capture.get("capture_scope") or "").lower() == "full_field" and (capture.get("runners") or []):
                summary["eligible_full_field_snapshots"] += 1
                if row.get("result_json"):
                    summary["results_matched_meetings"] += 1
                else:
                    summary["missing_results"] += 1
            elif snapshot.get("predictions"):
                summary["selected_only_excluded"] += 1
            else:
                summary["invalid_snapshots"] += 1
        return {"success": True, "dataset_version": LEARNING_DATASET_VERSION, "dry_run": True, "summary": summary, "audit": get_learning_dataset_audit()}

    from database_manager import save_runner_factor_snapshots, update_runner_factor_results_from_results

    for row in rows:
        try:
            snapshot = _json_object(row.get("prediction_json"))
            capture = snapshot.get("factor_capture") or {}
            runners = capture.get("runners") or []
            if str(capture.get("capture_scope") or "").lower() != "full_field" or not runners:
                if snapshot.get("predictions"):
                    summary["selected_only_excluded"] += 1
                else:
                    summary["invalid_snapshots"] += 1
                continue
            summary["eligible_full_field_snapshots"] += 1
            snapshot["meeting_id"] = snapshot.get("meeting_id") or row.get("meeting_id")
            snapshot["model_version"] = snapshot.get("model_version") or row.get("model_version") or MODEL_VERSION
            snapshot["track"] = snapshot.get("track") or row.get("track")
            snapshot["meeting_date"] = snapshot.get("meeting_date") or row.get("meeting_date")
            saved = save_runner_factor_snapshots(snapshot)
            if saved.get("success"):
                summary["reconstructed_meetings"] += 1
                summary["saved_runner_rows"] += _int(saved.get("saved_count"))
            else:
                summary["errors"].append({"meeting_id": row.get("meeting_id"), "stage": "factor_save", "error": saved.get("error") or saved.get("message")})
            result_json = _json_object(row.get("result_json"))
            if result_json:
                matched = update_runner_factor_results_from_results(result_json)
                if matched.get("success"):
                    summary["results_matched_meetings"] += 1
                else:
                    summary["errors"].append({"meeting_id": row.get("meeting_id"), "stage": "result_match", "error": matched.get("error") or matched.get("message")})
            else:
                summary["missing_results"] += 1
        except Exception as error:
            summary["errors"].append({"meeting_id": row.get("meeting_id"), "stage": "reconstruction", "error": str(error)})

    return {
        "success": len(summary["errors"]) == 0,
        "dataset_version": LEARNING_DATASET_VERSION,
        "dry_run": False,
        "summary": summary,
        "audit": get_learning_dataset_audit(),
        "note": "Only stored full-field pre-race captures were reconstructed. Selected-runner-only history remains archived and excluded from adaptive replay.",
    }


def load_learning_rows(min_meeting_date: Optional[str] = None, max_meeting_date: Optional[str] = None, model_version: Optional[str] = None) -> List[Dict[str, Any]]:
    clauses = ["actual_position IS NOT NULL", "race_number IS NOT NULL", "capture_scope = 'full_field'"]
    params: List[Any] = []
    if min_meeting_date:
        clauses.append("meeting_date >= %s")
        params.append(min_meeting_date)
    if max_meeting_date:
        clauses.append("meeting_date <= %s")
        params.append(max_meeting_date)
    if model_version and model_version not in ("all", "all_full_field_models"):
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
