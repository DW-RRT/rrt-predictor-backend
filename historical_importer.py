import json
from typing import Any, Dict, List, Optional, Tuple

from database import execute_sql, fetch_one
from database_manager import save_performance_snapshot


IMPORTER_VERSION = "2.9.4"


def _extract_json_objects(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Extract complete top-level JSON objects from a mixed text file.

    The uploaded historical files contain separator headings plus one JSON object
    per completed meeting. This parser ignores all non-JSON text and extracts
    balanced JSON objects beginning with '{' and ending with the matching '}'.
    """
    objects: List[Dict[str, Any]] = []
    errors: List[str] = []

    depth = 0
    start_index: Optional[int] = None
    in_string = False
    escape_next = False

    for index, char in enumerate(text):
        if start_index is None:
            if char == "{":
                start_index = index
                depth = 1
                in_string = False
                escape_next = False
            continue

        if escape_next:
            escape_next = False
            continue

        if char == "\" and in_string:
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0 and start_index is not None:
                json_text = text[start_index:index + 1]

                try:
                    parsed = json.loads(json_text)
                    if isinstance(parsed, dict):
                        objects.append(parsed)
                except Exception as error:
                    errors.append(
                        f"JSON parse error near character {start_index}: {str(error)}"
                    )

                start_index = None

    if start_index is not None:
        errors.append(
            f"Incomplete JSON object starting near character {start_index}."
        )

    return objects, errors


def _has_valid_winners(performance_snapshot: Dict[str, Any]) -> bool:
    results_summary = performance_snapshot.get("results_summary") or {}
    winners = results_summary.get("winners") or []

    if not winners:
        return False

    valid_winner_count = 0

    for winner in winners:
        if not isinstance(winner, dict):
            continue

        if winner.get("runner") and winner.get("tab_number") is not None:
            valid_winner_count += 1

    return valid_winner_count > 0


def _is_importable_performance_snapshot(item: Dict[str, Any]) -> Tuple[bool, str]:
    if not item.get("success"):
        return False, "success flag is false or missing"

    if not item.get("meeting_id"):
        return False, "meeting_id missing"

    if not item.get("accuracy"):
        return False, "accuracy block missing"

    if not item.get("model_version"):
        return False, "model_version missing"

    if not _has_valid_winners(item):
        return False, "valid winners missing; likely incomplete or abandoned results"

    return True, "ok"


def _upsert_meeting_from_performance(performance_snapshot: Dict[str, Any]) -> None:
    execute_sql(
        """
        INSERT INTO rrt_meetings (
            meeting_id,
            meeting_date,
            track,
            provider
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (meeting_id)
        DO UPDATE SET
            meeting_date = EXCLUDED.meeting_date,
            track = EXCLUDED.track,
            provider = EXCLUDED.provider,
            updated_at = NOW();
        """,
        (
            performance_snapshot.get("meeting_id"),
            performance_snapshot.get("meeting_date"),
            performance_snapshot.get("track"),
            performance_snapshot.get("provider") or "Punting Form",
        ),
    )


def _existing_performance_record(meeting_id: Any, model_version: Any) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT id, meeting_id, model_version, created_at
        FROM rrt_performance_snapshots
        WHERE meeting_id = %s
          AND model_version = %s;
        """,
        (
            meeting_id,
            model_version,
        ),
    )


def import_historical_performance_text(
    text: str,
    source_name: str = "uploaded_text",
    dry_run: bool = False,
) -> Dict[str, Any]:
    objects, parse_errors = _extract_json_objects(text)

    meetings_found = len(objects)
    meetings_imported = 0
    meetings_updated = 0
    meetings_skipped = 0
    errors: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    imported: List[Dict[str, Any]] = []

    seen_keys = set()

    for index, item in enumerate(objects, start=1):
        meeting_id = item.get("meeting_id")
        model_version = item.get("model_version")

        is_valid, reason = _is_importable_performance_snapshot(item)

        if not is_valid:
            meetings_skipped += 1
            skipped.append(
                {
                    "index": index,
                    "meeting_id": meeting_id,
                    "track": item.get("track"),
                    "meeting_date": item.get("meeting_date"),
                    "reason": reason,
                }
            )
            continue

        dedupe_key = (str(meeting_id), str(model_version))

        if dedupe_key in seen_keys:
            meetings_skipped += 1
            skipped.append(
                {
                    "index": index,
                    "meeting_id": meeting_id,
                    "track": item.get("track"),
                    "meeting_date": item.get("meeting_date"),
                    "reason": "duplicate meeting/model combination inside uploaded file",
                }
            )
            continue

        seen_keys.add(dedupe_key)

        existing = _existing_performance_record(
            meeting_id=meeting_id,
            model_version=model_version,
        )

        if dry_run:
            imported.append(
                {
                    "meeting_id": meeting_id,
                    "track": item.get("track"),
                    "meeting_date": item.get("meeting_date"),
                    "model_version": model_version,
                    "status": "would_update" if existing else "would_import",
                    "overall_accuracy": (item.get("accuracy") or {}).get("overall_accuracy"),
                }
            )
            continue

        try:
            _upsert_meeting_from_performance(item)
            save_result = save_performance_snapshot(item)

            if save_result.get("success"):
                if existing:
                    meetings_updated += 1
                    status = "updated"
                else:
                    meetings_imported += 1
                    status = "imported"

                imported.append(
                    {
                        "meeting_id": meeting_id,
                        "track": item.get("track"),
                        "meeting_date": item.get("meeting_date"),
                        "model_version": model_version,
                        "status": status,
                        "overall_accuracy": (item.get("accuracy") or {}).get("overall_accuracy"),
                    }
                )
            else:
                errors.append(
                    {
                        "index": index,
                        "meeting_id": meeting_id,
                        "track": item.get("track"),
                        "error": save_result.get("error") or save_result.get("message"),
                    }
                )

        except Exception as error:
            errors.append(
                {
                    "index": index,
                    "meeting_id": meeting_id,
                    "track": item.get("track"),
                    "error": str(error),
                }
            )

    for parse_error in parse_errors:
        errors.append(
            {
                "type": "parse_error",
                "error": parse_error,
            }
        )

    return {
        "success": len(errors) == 0,
        "provider": "RRT Predictor",
        "importer_version": IMPORTER_VERSION,
        "source_name": source_name,
        "dry_run": dry_run,
        "meetings_found": meetings_found,
        "meetings_imported": meetings_imported,
        "meetings_updated": meetings_updated,
        "meetings_skipped": meetings_skipped,
        "errors_count": len(errors),
        "parse_errors_count": len(parse_errors),
        "imported_preview": imported[:20],
        "skipped_preview": skipped[:20],
        "errors_preview": errors[:20],
        "message": (
            "Historical performance import dry run completed."
            if dry_run
            else "Historical performance import completed."
        ),
    }


def import_historical_performance_file(
    file_bytes: bytes,
    filename: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    text = file_bytes.decode("utf-8", errors="replace")

    return import_historical_performance_text(
        text=text,
        source_name=filename,
        dry_run=dry_run,
    )
