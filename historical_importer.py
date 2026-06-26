import json
from typing import Any, Dict, List, Optional, Tuple

from database import execute_sql, fetch_one
from database_manager import save_performance_snapshot


IMPORTER_VERSION = "2.9.7"


# ---------------------------------------------------------------------
# Sequential historical performance importer
# ---------------------------------------------------------------------
# Purpose:
# - Import RRT historical performance text files into PostgreSQL.
# - Read the file sequentially.
# - Avoid the old balanced-brace parser.
# - Recover cleanly if one meeting block is malformed.
# - Skip duplicates safely.
# - Skip abandoned / pending / null-result meetings so they do not distort
#   adaptive learning.
#
# Expected file format:
#
# ====================================================
# TRACK NAME
# Meeting ID: 123456
# Date: YYYY-MM-DD
# ====================================================
#
# {"success":true, ... one performance JSON object ...}
#
# The JSON object is normally one long line, but this importer also supports
# pretty-printed multi-line JSON objects.
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
# File decoding and debug
# ---------------------------------------------------------------------


def _decode_file_bytes(file_bytes: bytes) -> str:
    """Decode uploaded text safely for Windows/Notepad and UTF-8 files."""
    for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin-1"]:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    return file_bytes.decode("utf-8", errors="replace")


def _build_file_debug_summary(
    file_bytes: bytes,
    filename: str,
    text: str,
) -> Dict[str, Any]:
    lines = text.splitlines()

    return {
        "filename": filename,
        "bytes_received": len(file_bytes),
        "characters": len(text),
        "lines": len(lines),
        "first_200_chars": text[:200],
        "last_500_chars": text[-500:] if text else "",
    }


# ---------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------


def _line_looks_like_json_start(line: str) -> bool:
    return line.lstrip().startswith("{")


def _line_looks_like_meeting_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) == {"="}


def _try_parse_json_object(buffer: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Attempt to parse the current buffer as one JSON object.

    Returns:
        (dict, None) when a complete object is parsed.
        (None, None) when the buffer appears incomplete and should keep growing.
        (None, error_message) when the buffer is invalid and should be discarded.
    """
    candidate = buffer.strip()

    if not candidate:
        return None, None

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        incomplete_markers = [
            "Expecting property name enclosed in double quotes",
            "Expecting value",
            "Expecting ',' delimiter",
            "Unterminated string starting at",
        ]

        if any(marker in error.msg for marker in incomplete_markers):
            return None, None

        return None, (
            f"JSON decode error at line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        )

    if not isinstance(parsed, dict):
        return None, "Parsed JSON value is not an object."

    return parsed, None


def _extract_performance_snapshots_sequential(
    text: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Read historical performance text sequentially and extract JSON objects.

    This method does not scan the whole file with a brace counter.

    Recovery rule:
    If a new meeting separator appears while we are still collecting JSON,
    the current JSON block is marked as malformed and skipped, then parsing
    continues from the next meeting. This prevents one broken meeting from
    swallowing the rest of the file.
    """
    snapshots: List[Dict[str, Any]] = []
    parse_skips: List[Dict[str, Any]] = []

    collecting = False
    buffer_lines: List[str] = []
    start_line_number: Optional[int] = None

    lines = text.splitlines()

    for line_number, line in enumerate(lines, start=1):
        if not collecting:
            if not _line_looks_like_json_start(line):
                continue

            collecting = True
            buffer_lines = [line]
            start_line_number = line_number

        else:
            if _line_looks_like_meeting_separator(line):
                parse_skips.append(
                    {
                        "start_line": start_line_number,
                        "end_line": line_number - 1,
                        "reason": (
                            "malformed or incomplete JSON meeting snapshot; "
                            "new meeting separator found before this snapshot "
                            "could be parsed"
                        ),
                        "preview": "\n".join(buffer_lines)[:500],
                    }
                )

                collecting = False
                buffer_lines = []
                start_line_number = None
                continue

            buffer_lines.append(line)

        buffer = "\n".join(buffer_lines)
        parsed, error = _try_parse_json_object(buffer)

        if parsed is not None:
            snapshots.append(parsed)
            collecting = False
            buffer_lines = []
            start_line_number = None
            continue

        if error is not None:
            parse_skips.append(
                {
                    "start_line": start_line_number,
                    "end_line": line_number,
                    "reason": error,
                    "preview": buffer[:500],
                }
            )
            collecting = False
            buffer_lines = []
            start_line_number = None

    if collecting and buffer_lines:
        parse_skips.append(
            {
                "start_line": start_line_number,
                "end_line": len(lines),
                "reason": (
                    "file ended before the current JSON meeting snapshot "
                    "could be parsed"
                ),
                "preview": "\n".join(buffer_lines)[:500],
            }
        )

    return snapshots, parse_skips


# ---------------------------------------------------------------------
# Validation and duplicate handling
# ---------------------------------------------------------------------


def _has_valid_winners(performance_snapshot: Dict[str, Any]) -> bool:
    results_summary = performance_snapshot.get("results_summary") or {}
    winners = results_summary.get("winners") or []

    if not isinstance(winners, list) or not winners:
        return False

    for winner in winners:
        if not isinstance(winner, dict):
            continue

        runner = winner.get("runner")
        tab_number = winner.get("tab_number")

        if runner and tab_number is not None:
            return True

    return False


def _has_all_null_winners(performance_snapshot: Dict[str, Any]) -> bool:
    results_summary = performance_snapshot.get("results_summary") or {}
    winners = results_summary.get("winners") or []

    if not isinstance(winners, list) or not winners:
        return False

    for winner in winners:
        if not isinstance(winner, dict):
            continue

        if winner.get("runner") or winner.get("tab_number") is not None:
            return False

    return True


def _is_importable_performance_snapshot(item: Dict[str, Any]) -> Tuple[bool, str]:
    if not item.get("success"):
        return False, "success flag is false or missing"

    if not item.get("meeting_id"):
        return False, "meeting_id missing"

    if not item.get("accuracy"):
        return False, "accuracy block missing"

    if not item.get("model_version"):
        return False, "model_version missing"

    if _has_all_null_winners(item):
        return False, (
            "all winners are null; likely abandoned, pending, or no official "
            "results available"
        )

    if not _has_valid_winners(item):
        return False, (
            "valid winners missing; likely incomplete, abandoned, "
            "or pending results"
        )

    return True, "ok"


def _normalise_dedupe_value(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_key(performance_snapshot: Dict[str, Any]) -> Tuple[str, str]:
    return (
        _normalise_dedupe_value(performance_snapshot.get("meeting_id")),
        _normalise_dedupe_value(performance_snapshot.get("model_version")),
    )


def _existing_performance_record(
    meeting_id: Any,
    model_version: Any,
) -> Optional[Dict[str, Any]]:
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


def _import_preview_item(
    item: Dict[str, Any],
    index: int,
    status: str,
    reason: Optional[str] = None,
    existing_record_id: Optional[Any] = None,
) -> Dict[str, Any]:
    accuracy = item.get("accuracy") or {}

    preview = {
        "index": index,
        "meeting_id": item.get("meeting_id"),
        "track": item.get("track"),
        "meeting_date": item.get("meeting_date"),
        "model_version": item.get("model_version"),
        "status": status,
        "overall_accuracy": accuracy.get("overall_accuracy"),
    }

    if reason:
        preview["reason"] = reason

    if existing_record_id is not None:
        preview["existing_record_id"] = existing_record_id

    return preview


def _parse_skip_preview_item(skip: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "index": f"parse_skip_{index}",
        "status": "skipped",
        "reason": skip.get("reason"),
        "start_line": skip.get("start_line"),
        "end_line": skip.get("end_line"),
        "preview": skip.get("preview"),
    }


# ---------------------------------------------------------------------
# Public import functions
# ---------------------------------------------------------------------


def import_historical_performance_text(
    text: str,
    source_name: str = "uploaded_text",
    dry_run: bool = False,
    file_debug: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    snapshots, parse_skips = _extract_performance_snapshots_sequential(text)

    meetings_found = len(snapshots)
    meetings_imported = 0
    meetings_skipped = 0
    errors: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    imported: List[Dict[str, Any]] = []
    seen_keys = set()

    for parse_skip_index, parse_skip in enumerate(parse_skips, start=1):
        meetings_skipped += 1
        skipped.append(_parse_skip_preview_item(parse_skip, parse_skip_index))

    for index, item in enumerate(snapshots, start=1):
        meeting_id = item.get("meeting_id")
        model_version = item.get("model_version")

        is_valid, reason = _is_importable_performance_snapshot(item)

        if not is_valid:
            meetings_skipped += 1
            skipped.append(
                _import_preview_item(
                    item=item,
                    index=index,
                    status="skipped",
                    reason=reason,
                )
            )
            continue

        dedupe_key = _dedupe_key(item)

        if dedupe_key in seen_keys:
            meetings_skipped += 1
            skipped.append(
                _import_preview_item(
                    item=item,
                    index=index,
                    status="skipped",
                    reason="duplicate meeting/model combination inside uploaded file",
                )
            )
            continue

        seen_keys.add(dedupe_key)

        existing = _existing_performance_record(
            meeting_id=meeting_id,
            model_version=model_version,
        )

        if existing:
            meetings_skipped += 1
            skipped.append(
                _import_preview_item(
                    item=item,
                    index=index,
                    status="skipped",
                    reason="duplicate already exists in PostgreSQL",
                    existing_record_id=existing.get("id"),
                )
            )
            continue

        if dry_run:
            imported.append(
                _import_preview_item(
                    item=item,
                    index=index,
                    status="would_import",
                )
            )
            continue

        try:
            _upsert_meeting_from_performance(item)
            save_result = save_performance_snapshot(item)

            if save_result.get("success"):
                meetings_imported += 1
                imported.append(
                    _import_preview_item(
                        item=item,
                        index=index,
                        status="imported",
                    )
                )
            else:
                errors.append(
                    {
                        "index": index,
                        "meeting_id": meeting_id,
                        "track": item.get("track"),
                        "meeting_date": item.get("meeting_date"),
                        "model_version": model_version,
                        "error": (
                            save_result.get("error")
                            or save_result.get("message")
                            or "save_performance_snapshot failed"
                        ),
                    }
                )

        except Exception as error:
            errors.append(
                {
                    "index": index,
                    "meeting_id": meeting_id,
                    "track": item.get("track"),
                    "meeting_date": item.get("meeting_date"),
                    "model_version": model_version,
                    "error": str(error),
                }
            )

    valid_meetings_available = len(imported)

    return {
        "success": len(errors) == 0,
        "provider": "RRT Predictor",
        "importer_version": IMPORTER_VERSION,
        "source_name": source_name,
        "dry_run": dry_run,
        "parser": "sequential_line_reader_json_loads_recovery_skip_bad_meetings",
        "file_debug": file_debug,
        "meetings_found": meetings_found,
        "valid_meetings_available": valid_meetings_available,
        "meetings_imported": meetings_imported,
        "meetings_updated": 0,
        "meetings_skipped": meetings_skipped,
        "parse_skips_count": len(parse_skips),
        "errors_count": len(errors),
        "imported_preview": imported[:30],
        "skipped_preview": skipped[:30],
        "errors_preview": errors[:30],
        "message": (
            "Historical performance import dry run completed. Malformed, duplicate, null-result, and abandoned meetings were safely skipped."
            if dry_run
            else "Historical performance import completed. Malformed, duplicate, null-result, and abandoned meetings were safely skipped."
        ),
    }


def import_historical_performance_file(
    file_bytes: bytes,
    filename: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    text = _decode_file_bytes(file_bytes)
    file_debug = _build_file_debug_summary(
        file_bytes=file_bytes,
        filename=filename,
        text=text,
    )

    print("=" * 60)
    print("Historical Import Debug")
    print(f"Filename: {file_debug['filename']}")
    print(f"Bytes received: {file_debug['bytes_received']}")
    print(f"Characters: {file_debug['characters']}")
    print(f"Lines: {file_debug['lines']}")
    print(f"Last 500 chars:\n{file_debug['last_500_chars']}")
    print("=" * 60)

    return import_historical_performance_text(
        text=text,
        source_name=filename,
        dry_run=dry_run,
        file_debug=file_debug,
    )
