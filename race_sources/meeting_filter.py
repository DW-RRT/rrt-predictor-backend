from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs, unquote


DEFAULT_TIMEZONE = "Australia/Sydney"


def safe_text(value):
    return str(value or "").strip()


def clean(value):
    return safe_text(value).lower()


def extract_date_from_racing_australia_url(url):
    """
    Racing Australia URLs include:
    Key=2026May09%2CQLD%2CAquis%20Park%20Gold%20Coast

    This extracts 2026May09 and converts it to a datetime date.
    """

    if not url:
        return None

    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        key_value = query.get("Key", [None])[0]

        if not key_value:
            return None

        decoded = unquote(key_value)
        date_part = decoded.split(",")[0]

        return datetime.strptime(date_part, "%Y%b%d")

    except Exception:
        return None


def parse_meeting_datetime(meeting, timezone_name=DEFAULT_TIMEZONE):
    timezone = ZoneInfo(timezone_name)

    possible_fields = [
        meeting.get("date_time"),
        meeting.get("datetime"),
        meeting.get("meeting_datetime"),
        meeting.get("start_time"),
        meeting.get("race_time"),
        meeting.get("date"),
    ]

    known_formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]

    for value in possible_fields:
        if not value:
            continue

        text = safe_text(value)

        for fmt in known_formats:
            try:
                parsed = datetime.strptime(text[:19], fmt)
                return parsed.replace(tzinfo=timezone)
            except Exception:
                pass

    url_date = extract_date_from_racing_australia_url(meeting.get("url"))

    if url_date:
        return url_date.replace(tzinfo=timezone)

    return None


def normalise_meeting(
    meeting,
    country="Australia",
    race_type="Horse",
    timezone_name=DEFAULT_TIMEZONE,
):
    meeting_name = (
        meeting.get("meeting_name")
        or meeting.get("track")
        or meeting.get("name")
        or meeting.get("venue")
    )

    if not meeting_name:
        return None

    parsed_time = parse_meeting_datetime(meeting, timezone_name)

    return {
        "country": country,
        "race_type": race_type,
        "track": meeting_name,
        "meeting_name": meeting_name,
        "city": meeting.get("city") or meeting.get("location") or meeting_name,
        "timezone": meeting.get("timezone") or timezone_name,
        "url": meeting.get("url"),
        "source": meeting.get("source") or "Racing Australia",
        "is_active_meeting": True,
        "meeting_datetime": parsed_time.isoformat() if parsed_time else None,
    }


def filter_next_24_hours(
    meetings,
    country="Australia",
    race_type="Horse",
    timezone_name=DEFAULT_TIMEZONE,
):
    timezone = ZoneInfo(timezone_name)
    now = datetime.now(timezone)
    cutoff = now + timedelta(hours=24)

    filtered = []

    for meeting in meetings or []:
        parsed_time = parse_meeting_datetime(meeting, timezone_name)

        if parsed_time is None:
            continue

        if now.date() <= parsed_time.date() <= cutoff.date():
            normalised = normalise_meeting(
                meeting,
                country=country,
                race_type=race_type,
                timezone_name=timezone_name,
            )

            if normalised:
                filtered.append(normalised)

    filtered.sort(key=lambda item: clean(item.get("track")))

    return filtered


def find_matching_meeting(meetings, track_name):
    selected = clean(track_name)

    if not selected:
        return None

    for meeting in meetings or []:
        if selected == clean(meeting.get("meeting_name")):
            return meeting
        if selected == clean(meeting.get("track")):
            return meeting

    for meeting in meetings or []:
        meeting_name = clean(meeting.get("meeting_name"))
        track = clean(meeting.get("track"))

        if selected in meeting_name or meeting_name in selected:
            return meeting

        if selected in track or track in selected:
            return meeting

    return None