from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import re


DEFAULT_TIMEZONE = "Australia/Sydney"


def safe_text(value):
    return str(value or "").strip()


def parse_time_token(text):
    if not text:
        return None

    cleaned = safe_text(text).upper().replace(".", ":")

    patterns = [
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        r"\b([1-9]|1[0-2]):([0-5]\d)\s?(AM|PM)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, cleaned)

        if not match:
            continue

        token = match.group(0).replace(" ", "")

        for fmt in ["%H:%M", "%I:%M%p"]:
            try:
                return datetime.strptime(token, fmt).time()
            except Exception:
                pass

    return None


def parse_race_time(race, fallback_timezone=DEFAULT_TIMEZONE):
    timezone_name = race.get("timezone") or fallback_timezone
    timezone = ZoneInfo(timezone_name)

    possible_fields = [
        race.get("race_datetime"),
        race.get("datetime"),
        race.get("start_time"),
        race.get("race_time"),
        race.get("scheduled_time"),
        race.get("time"),
    ]

    for value in possible_fields:
        if not value:
            continue

        text = safe_text(value)

        known_formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M",
        ]

        for fmt in known_formats:
            try:
                parsed = datetime.strptime(text[:19], fmt)
                return parsed.replace(tzinfo=timezone)
            except Exception:
                pass

    meeting_date_text = race.get("meeting_date")
    parsed_time = None

    for value in possible_fields:
        parsed_time = parse_time_token(value)
        if parsed_time:
            break

    if not parsed_time:
        searchable_text = " ".join(
            [
                safe_text(race.get("race_header")),
                safe_text(race.get("race_name")),
                safe_text(race.get("name")),
                safe_text(race.get("race")),
            ]
        )

        parsed_time = parse_time_token(searchable_text)

    if parsed_time and meeting_date_text:
        try:
            meeting_date = datetime.strptime(
                safe_text(meeting_date_text),
                "%Y-%m-%d",
            ).date()

            return datetime.combine(
                meeting_date,
                parsed_time,
            ).replace(tzinfo=timezone)

        except Exception:
            pass

    if parsed_time:
        today = datetime.now(timezone).date()

        return datetime.combine(
            today,
            parsed_time,
        ).replace(tzinfo=timezone)

    return None


def filter_races_current_time_to_end_of_next_day(
    races,
    timezone_name=DEFAULT_TIMEZONE,
):
    fallback_timezone = ZoneInfo(timezone_name)
    now_fallback = datetime.now(fallback_timezone)

    tomorrow = now_fallback.date() + timedelta(days=1)
    fallback_cutoff = datetime.combine(
        tomorrow,
        time(23, 59, 59),
    ).replace(tzinfo=fallback_timezone)

    upcoming = []
    excluded_past = []
    excluded_after_window = []
    excluded_unknown_time = []

    for race in races or []:
        race_timezone_name = race.get("timezone") or timezone_name
        race_timezone = ZoneInfo(race_timezone_name)

        now = datetime.now(race_timezone)
        cutoff = datetime.combine(
            now.date() + timedelta(days=1),
            time(23, 59, 59),
        ).replace(tzinfo=race_timezone)

        race_time = parse_race_time(
            race,
            fallback_timezone=race_timezone_name,
        )

        if race_time is None:
            excluded_unknown_time.append(race)
            continue

        if race_time < now:
            excluded_past.append(race)
            continue

        if race_time > cutoff:
            excluded_after_window.append(race)
            continue

        updated_race = dict(race)
        updated_race["parsed_race_time"] = race_time.isoformat()
        upcoming.append(updated_race)

    return {
        "races": upcoming,
        "included_count": len(upcoming),
        "excluded_past_count": len(excluded_past),
        "excluded_after_window_count": len(excluded_after_window),
        "unknown_time_count": len(excluded_unknown_time),
        "window_start": now_fallback.isoformat(),
        "window_end": fallback_cutoff.isoformat(),
        "message": (
            "Past races excluded using each race's local timezone. "
            "Window runs from current local race time to end of next racing day."
        ),
    }


def filter_races_next_24_hours(races, timezone_name=DEFAULT_TIMEZONE):
    return filter_races_current_time_to_end_of_next_day(
        races,
        timezone_name=timezone_name,
    )