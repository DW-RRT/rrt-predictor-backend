import re
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from zoneinfo import ZoneInfo


BASE_API_URL = "https://api.beta.tab.com.au/v1/tab-info-service"

AUSTRALIAN_TIMEZONE = "Australia/Sydney"

RACE_TYPE_CODES = {
    "horse": "R",
    "thoroughbred": "R",
    "harness": "H",
    "greyhound": "G",
    "greyhounds": "G",
}

TAB_JURISDICTIONS = ["NSW"]


def clean_text(value):
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def normalise_key(value):
    return clean_text(value).lower()


def get_race_type_code(race_type="Horse"):
    return RACE_TYPE_CODES.get(normalise_key(race_type), "R")


def build_session():
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Origin": "https://www.tab.com.au",
        "Referer": "https://www.tab.com.au/",
    })
    return session


def request_json(session, url, params=None):
    print("Requesting:", url, params or {})

    response = session.get(
        url,
        params=params or {},
        timeout=(10, 45),
        allow_redirects=True,
    )

    print("Status:", response.status_code)
    print("Final URL:", response.url)
    print("Content-Type:", response.headers.get("content-type"))

    response.raise_for_status()
    return response.json()

def get_date_tokens():
    now = datetime.now(ZoneInfo(AUSTRALIAN_TIMEZONE))
    today = now.date()
    tomorrow = today + timedelta(days=1)

    return [
        today.isoformat(),
        tomorrow.isoformat(),
    ]


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, dict):
        for key in [
            "startTime",
            "advertisedStartTime",
            "advertisedStart",
            "dateTime",
            "time",
        ]:
            parsed = parse_datetime(value.get(key))
            if parsed:
                return parsed

        seconds = value.get("seconds")
        if seconds is not None:
            try:
                return datetime.fromtimestamp(
                    int(seconds),
                    tz=ZoneInfo("UTC"),
                ).astimezone(ZoneInfo(AUSTRALIAN_TIMEZONE))
            except Exception:
                return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                int(value),
                tz=ZoneInfo("UTC"),
            ).astimezone(ZoneInfo(AUSTRALIAN_TIMEZONE))
        except Exception:
            return None

    text = clean_text(value)

    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")

        parsed = datetime.fromisoformat(text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(AUSTRALIAN_TIMEZONE))

        return parsed.astimezone(ZoneInfo(AUSTRALIAN_TIMEZONE))

    except Exception:
        return None


def extract_advertised_start(race):
    for key in [
        "advertisedStart",
        "advertisedStartTime",
        "startTime",
        "raceStartTime",
        "jumpTime",
    ]:
        parsed = parse_datetime(race.get(key))
        if parsed:
            return parsed

    return None


def extract_meeting_name(meeting):
    for key in [
        "meetingName",
        "venueName",
        "trackName",
        "location",
        "name",
    ]:
        value = clean_text(meeting.get(key))
        if value:
            return value

    return ""


def extract_meeting_country(meeting):
    for key in ["country", "countryCode", "region", "state"]:
        value = clean_text(meeting.get(key))
        if value:
            return value

    return ""


def is_australian_meeting(meeting):
    text = " ".join([
        clean_text(meeting.get("country")),
        clean_text(meeting.get("countryCode")),
        clean_text(meeting.get("region")),
        clean_text(meeting.get("state")),
        extract_meeting_name(meeting),
    ]).lower()

    foreign_markers = [
        "nz",
        "new zealand",
        "jpn",
        "japan",
        "usa",
        "united states",
        "uk",
        "ireland",
        "france",
        "south africa",
        "hong kong",
        "singapore",
        "korea",
        "chile",
        "argentina",
    ]

    return not any(marker in text for marker in foreign_markers)


def extract_races_from_meeting(meeting):
    for key in ["races", "raceList", "events"]:
        races = meeting.get(key)
        if isinstance(races, list):
            return races

    return []


def extract_race_number(race):
    for key in ["raceNumber", "number", "raceNo"]:
        value = race.get(key)

        try:
            return int(value)
        except Exception:
            pass

    for key in ["raceName", "name", "raceTitle"]:
        text = clean_text(race.get(key))
        match = re.search(r"\bR(?:ACE)?\s*0?(\d{1,2})\b", text, re.I)

        if match:
            return int(match.group(1))

    return None


def extract_race_name(race):
    for key in ["raceName", "name", "raceTitle"]:
        value = clean_text(race.get(key))
        if value:
            return value

    race_number = extract_race_number(race)

    if race_number:
        return f"Race {race_number}"

    return ""


def extract_runner_number(runner):
    for key in [
        "runnerNumber",
        "number",
        "runnerNo",
        "saddleNumber",
        "boxNumber",
    ]:
        value = runner.get(key)

        try:
            return int(value)
        except Exception:
            pass

    return None


def extract_runner_name(runner):
    for key in [
        "runnerName",
        "name",
        "horseName",
        "greyhoundName",
        "competitorName",
    ]:
        value = clean_text(runner.get(key))
        if value:
            return value

    return ""


def is_runner_scratched(runner):
    scratch_keys = [
        "scratched",
        "isScratched",
        "scratching",
        "isScratching",
        "withdrawn",
        "isWithdrawn",
    ]

    for key in scratch_keys:
        value = runner.get(key)

        if isinstance(value, bool):
            return value

        if isinstance(value, str) and value.strip().lower() in [
            "true",
            "yes",
            "scratched",
            "withdrawn",
        ]:
            return True

    status_text = " ".join([
        clean_text(runner.get("status")),
        clean_text(runner.get("runnerStatus")),
        clean_text(runner.get("bettingStatus")),
    ]).lower()

    return "scratch" in status_text or "withdraw" in status_text


def extract_runners(payload):
    possible_lists = []

    if isinstance(payload, dict):
        for key in [
            "runners",
            "runnerList",
            "competitors",
            "selections",
            "propositions",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                possible_lists.append(value)

        race = payload.get("race")
        if isinstance(race, dict):
            for key in [
                "runners",
                "runnerList",
                "competitors",
                "selections",
                "propositions",
            ]:
                value = race.get(key)
                if isinstance(value, list):
                    possible_lists.append(value)

    for runner_list in possible_lists:
        runners = []

        for runner in runner_list:
            if not isinstance(runner, dict):
                continue

            runner_name = extract_runner_name(runner)

            if not runner_name:
                continue

            runners.append({
                "number": extract_runner_number(runner),
                "name": runner_name,
                "scratched": is_runner_scratched(runner),
            })

        if runners:
            runners.sort(
                key=lambda item: (
                    item.get("number") is None,
                    item.get("number") or 999,
                    item.get("name") or "",
                )
            )
            return runners

    return []


def build_race_detail_url(date_token, race_type_code, meeting_name, race_name):
    encoded_meeting = quote(meeting_name, safe="")
    encoded_race = quote(race_name, safe="")

    return (
        f"{BASE_API_URL}/racing/dates/{date_token}"
        f"/meetings/{race_type_code}/{encoded_meeting}"
        f"/races/{encoded_race}"
    )


def fetch_race_detail(
    session,
    date_token,
    race_type_code,
    meeting_name,
    race,
    jurisdiction,
):
    race_name = extract_race_name(race)

    if not meeting_name or not race_name:
        return {}

    url = build_race_detail_url(
        date_token=date_token,
        race_type_code=race_type_code,
        meeting_name=meeting_name,
        race_name=race_name,
    )

    try:
        return request_json(
            session,
            url,
            params={
                "jurisdiction": jurisdiction,
                "fixedOdds": "true",
            },
        )
    except Exception:
        return {}


def fetch_tab_meetings_for_date(
    session,
    date_token,
    race_type_code,
    jurisdiction,
):
    url = f"{BASE_API_URL}/racing/dates/{date_token}/meetings"

    payload = request_json(
        session,
        url,
        params={
            "jurisdiction": jurisdiction,
        },
    )

    meetings = []

    if isinstance(payload, list):
        raw_meetings = payload
    elif isinstance(payload, dict):
        raw_meetings = (
            payload.get("meetings")
            or payload.get("raceMeetings")
            or payload.get("data")
            or []
        )
    else:
        raw_meetings = []

    for meeting in raw_meetings:
        if not isinstance(meeting, dict):
            continue

        meeting_race_type = (
            clean_text(meeting.get("raceType"))
            or clean_text(meeting.get("meetingType"))
            or clean_text(meeting.get("code"))
        ).upper()

        if meeting_race_type and meeting_race_type != race_type_code:
            continue

        meetings.append(meeting)

    return meetings


def normalise_race(
    session,
    date_token,
    race_type_code,
    meeting_name,
    raw_race,
    jurisdiction,
):
    race_number = extract_race_number(raw_race)
    race_name = extract_race_name(raw_race)
    start_datetime = extract_advertised_start(raw_race)

    race_detail = fetch_race_detail(
        session=session,
        date_token=date_token,
        race_type_code=race_type_code,
        meeting_name=meeting_name,
        race=raw_race,
        jurisdiction=jurisdiction,
    )

    runners = extract_runners(race_detail) or extract_runners(raw_race)

    return {
        "race_number": race_number,
        "race_header": race_name or (
            f"Race {race_number}" if race_number else "Race"
        ),
        "race_time": (
            start_datetime.strftime("%H:%M")
            if start_datetime
            else None
        ),
        "start_time": (
            start_datetime.strftime("%H:%M")
            if start_datetime
            else None
        ),
        "race_datetime": (
            start_datetime.isoformat()
            if start_datetime
            else None
        ),
        "timezone": AUSTRALIAN_TIMEZONE,
        "runner_count": len(runners),
        "runners": runners,
        "source": "TAB",
    }


def normalise_meeting(
    session,
    date_token,
    race_type_code,
    raw_meeting,
    jurisdiction,
):
    meeting_name = extract_meeting_name(raw_meeting)
    raw_races = extract_races_from_meeting(raw_meeting)

    races = []

    for raw_race in raw_races:
        if not isinstance(raw_race, dict):
            continue

        normalised = normalise_race(
            session=session,
            date_token=date_token,
            race_type_code=race_type_code,
            meeting_name=meeting_name,
            raw_race=raw_race,
            jurisdiction=jurisdiction,
        )

        if normalised.get("race_number"):
            races.append(normalised)

    races.sort(
        key=lambda item: (
            item.get("race_number") is None,
            item.get("race_number") or 999,
        )
    )

    return {
        "provider": "TAB",
        "meeting_name": meeting_name,
        "track": meeting_name,
        "country": "Australia",
        "date": date_token,
        "timezone": AUSTRALIAN_TIMEZONE,
        "jurisdiction": jurisdiction,
        "race_count": len(races),
        "races": races,
        "url": (
            f"https://www.tab.com.au/racing/meetings/"
            f"{date_token}/{race_type_code}/{quote(meeting_name)}"
        ),
    }


def meeting_dedupe_key(meeting):
    return "|".join([
        normalise_key(meeting.get("meeting_name")),
        clean_text(meeting.get("date")),
        clean_text(meeting.get("race_count")),
    ])


def filter_current_to_end_of_next_day(meetings):
    now = datetime.now(ZoneInfo(AUSTRALIAN_TIMEZONE))
    end = (
        now
        .replace(hour=23, minute=59, second=59, microsecond=0)
        + timedelta(days=1)
    )

    filtered_meetings = []

    for meeting in meetings:
        races = []

        for race in meeting.get("races", []) or []:
            race_datetime = parse_datetime(race.get("race_datetime"))

            if not race_datetime:
                races.append(race)
                continue

            if now <= race_datetime <= end:
                races.append(race)

        if races:
            updated = dict(meeting)
            updated["races"] = races
            updated["race_count"] = len(races)
            filtered_meetings.append(updated)

    return filtered_meetings


def get_tab_racelist(country="Australia", race_type="Horse"):
    selected_country = clean_text(country) or "Australia"
    selected_race_type = clean_text(race_type) or "Horse"

    if selected_country.lower() != "australia":
        return {
            "provider": "TAB",
            "source": "TAB",
            "country": selected_country,
            "race_type": selected_race_type,
            "meeting_count": 0,
            "meetings": [],
            "message": "TAB racelist client currently supports Australia only.",
        }

    race_type_code = get_race_type_code(selected_race_type)
    session = build_session()

    meetings = []
    seen = set()
    errors = []

    for date_token in get_date_tokens():
        for jurisdiction in TAB_JURISDICTIONS:
            try:
                raw_meetings = fetch_tab_meetings_for_date(
                    session=session,
                    date_token=date_token,
                    race_type_code=race_type_code,
                    jurisdiction=jurisdiction,
                )

                for raw_meeting in raw_meetings:
                    if not is_australian_meeting(raw_meeting):
                        continue

                    meeting = normalise_meeting(
                        session=session,
                        date_token=date_token,
                        race_type_code=race_type_code,
                        raw_meeting=raw_meeting,
                        jurisdiction=jurisdiction,
                    )

                    if not meeting.get("meeting_name"):
                        continue

                    if not meeting.get("races"):
                        continue

                    key = meeting_dedupe_key(meeting)

                    if key in seen:
                        continue

                    seen.add(key)
                    meetings.append(meeting)

            except Exception as error:
                errors.append({
                    "date": date_token,
                    "jurisdiction": jurisdiction,
                    "error": str(error),
                })

    meetings = filter_current_to_end_of_next_day(meetings)

    meetings.sort(
        key=lambda item: (
            item.get("date") or "",
            item.get("meeting_name") or "",
        )
    )

    return {
        "provider": "TAB",
        "source": "TAB",
        "country": selected_country,
        "race_type": selected_race_type,
        "race_type_code": race_type_code,
        "timezone": AUSTRALIAN_TIMEZONE,
        "period": "current_to_end_of_next_racing_day",
        "meeting_count": len(meetings),
        "meetings": meetings,
        "errors": errors,
        "message": (
            "TAB racelist loaded."
            if meetings
            else "No TAB race meetings returned."
        ),
    }


def get_tab_meeting_races(track, country="Australia", race_type="Horse"):
    selected_track = normalise_key(track)
    racelist = get_tab_racelist(country=country, race_type=race_type)

    for meeting in racelist.get("meetings", []) or []:
        meeting_name = normalise_key(meeting.get("meeting_name"))

        if selected_track == meeting_name:
            return meeting

        if selected_track and selected_track in meeting_name:
            return meeting

    return {
        "provider": "TAB",
        "source": "TAB",
        "track": track,
        "race_count": 0,
        "races": [],
        "message": "No matching TAB meeting found.",
    }


if __name__ == "__main__":
    import json

    data = get_tab_racelist(country="Australia", race_type="Horse")

    print("TAB meetings:", data.get("meeting_count"))
    print("Message:", data.get("message"))
    print("Errors:")
    print(json.dumps(data.get("errors", []), indent=2))

    print("\nFirst meetings:")
    for meeting in data.get("meetings", [])[:10]:
        print(
            meeting.get("meeting_name"),
            meeting.get("date"),
            "races:",
            meeting.get("race_count"),
        )