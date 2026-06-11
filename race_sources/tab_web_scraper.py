import json
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


TAB_RACING_URL = "https://www.tab.com.au/racing-betting"
TAB_API_BASE = "https://api.beta.tab.com.au/v1/tab-info-service"
AUSTRALIAN_TIMEZONE = "Australia/Sydney"

RACE_TYPE_CODES = {
    "horse": "R",
    "thoroughbred": "R",
    "harness": "H",
    "greyhound": "G",
    "greyhounds": "G",
}

LOCATION_COUNTRY_MAP = {
    "NSW": "Australia",
    "VIC": "Australia",
    "QLD": "Australia",
    "SA": "Australia",
    "WA": "Australia",
    "TAS": "Australia",
    "ACT": "Australia",
    "NT": "Australia",
    "NZ": "New Zealand",
    "GBR": "United Kingdom",
    "UK": "United Kingdom",
    "ENG": "United Kingdom",
    "IRL": "Ireland",
    "USA": "United States",
    "FRA": "France",
    "JPN": "Japan",
    "HKG": "Hong Kong",
    "SGP": "Singapore",
    "ZAF": "South Africa",
    "TUR": "Turkey",
    "UAE": "United Arab Emirates",
    "ARG": "Argentina",
    "CHI": "Chile",
    "BRZ": "Brazil",
}


def clean_text(value):
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def normalise_key(value):
    return clean_text(value).lower()


def get_race_type_code(race_type="Horse"):
    return RACE_TYPE_CODES.get(normalise_key(race_type), "R")


def get_country_from_location(location_code):
    location_code = clean_text(location_code).upper()
    return LOCATION_COUNTRY_MAP.get(location_code, "International")


def parse_tab_datetime(value):
    if not value:
        return None

    try:
        text = str(value).strip()

        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")

        parsed = datetime.fromisoformat(text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))

        return parsed.astimezone(ZoneInfo(AUSTRALIAN_TIMEZONE))

    except Exception:
        return None


def get_current_window():
    now = datetime.now(ZoneInfo(AUSTRALIAN_TIMEZONE))

    end = (
        now.replace(hour=23, minute=59, second=59, microsecond=0)
        + timedelta(days=1)
    )

    return now, end


def build_direct_date_tokens():
    today = datetime.now(ZoneInfo(AUSTRALIAN_TIMEZONE)).date()
    tomorrow = today + timedelta(days=1)

    return [
        "today",
        today.strftime("%Y-%m-%d"),
        tomorrow.strftime("%Y-%m-%d"),
    ]


def direct_fetch_json(url):
    print("TAB DIRECT FETCH:", url)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-AU,en;q=0.9",
            "Origin": "https://www.tab.com.au",
            "Referer": "https://www.tab.com.au/racing-betting",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")

    return json.loads(text or "{}")


def fetch_dates_payload():
    url = f"{TAB_API_BASE}/racing/dates?jurisdiction=NSW"
    return direct_fetch_json(url)


def extract_meeting_links(dates_payload):
    links = []

    for item in dates_payload.get("dates", []) or []:
        meeting_date = item.get("meetingDate")
        meetings_url = item.get("_links", {}).get("meetings")

        if not meeting_date or not meetings_url:
            continue

        if "futures" in meetings_url.lower():
            continue

        links.append({
            "date": meeting_date,
            "url": meetings_url,
        })

    return links


def fetch_direct_meeting_payloads():
    payloads = []

    for token in build_direct_date_tokens():
        url = (
            f"{TAB_API_BASE}/racing/dates/"
            f"{token}/meetings?jurisdiction=NSW"
        )

        try:
            payload = direct_fetch_json(url)

            if isinstance(payload, dict) and isinstance(payload.get("meetings"), list):
                payloads.append(payload)

        except Exception as error:
            print("DIRECT MEETINGS FETCH FAILED:", token, error)

    return payloads


def fetch_meeting_payloads():
    payloads = []

    try:
        dates_payload = fetch_dates_payload()
        links = extract_meeting_links(dates_payload)

        for link in links:
            try:
                payload = direct_fetch_json(link["url"])

                if isinstance(payload, dict) and isinstance(payload.get("meetings"), list):
                    payloads.append(payload)

            except Exception as error:
                print("DATE LINK MEETINGS FETCH FAILED:", error)

    except Exception as error:
        print("DATES PAYLOAD FETCH FAILED:", error)

    if payloads:
        return payloads

    return fetch_direct_meeting_payloads()


def is_supported_race_type(meeting, race_type_code):
    return clean_text(meeting.get("raceType")).upper() == race_type_code


def normalise_scratching(item):
    return {
        "number": item.get("runnerNumber"),
        "name": clean_text(item.get("runnerName")),
        "scratched": True,
        "status": clean_text(item.get("bettingStatus")) or "Scratched",
    }


def normalise_runner(item):
    runner_name = (
        item.get("runnerName")
        or item.get("runnerFullName")
        or item.get("name")
    )

    return {
        "number": item.get("runnerNumber"),
        "name": clean_text(runner_name),
        "horse_name": clean_text(runner_name),
        "form": clean_text(
            item.get("last5Starts")
            or item.get("last6Starts")
            or item.get("form")
        ),
        "trainer": clean_text(
            item.get("trainerName")
            or item.get("trainerFullName")
        ),
        "jockey": clean_text(
            item.get("riderDriverName")
            or item.get("riderDriverFullName")
            or item.get("jockey")
        ),
        "weight": (
            f"{item.get('handicapWeight')}kg"
            if item.get("handicapWeight") is not None
            else None
        ),
        "barrier": item.get("barrierNumber"),
        "scratched": bool(item.get("scratched")),
        "source": "TAB Web",
        "raw": item,
    }


def normalise_race(raw_race, meeting):
    race_number = raw_race.get("raceNumber")
    race_name = clean_text(raw_race.get("raceName"))

    start_dt = parse_tab_datetime(
        raw_race.get("raceStartTime")
        or raw_race.get("startTime")
    )

    race_time = start_dt.strftime("%H:%M") if start_dt else None

    scratchings = [
        normalise_scratching(item)
        for item in raw_race.get("scratchings", []) or []
        if isinstance(item, dict)
    ]

    raw_runners = (
        raw_race.get("runners")
        or raw_race.get("runnerDetails")
        or []
    )

    runners = [
        normalise_runner(item)
        for item in raw_runners
        if isinstance(item, dict)
    ]

    scratched_names = {
        normalise_key(item.get("name"))
        for item in scratchings
        if isinstance(item, dict)
    }

    for runner in runners:
        if normalise_key(runner.get("name")) in scratched_names:
            runner["scratched"] = True

    active_runner_count = len(
        [runner for runner in runners if not runner.get("scratched")]
    )

    return {
        "race_number": race_number,
        "race_header": f"Race {race_number}" if race_number else "Race",
        "race_name": race_name,
        "race_time": race_time,
        "start_time": race_time,
        "race_datetime": start_dt.isoformat() if start_dt else None,
        "timezone": AUSTRALIAN_TIMEZONE,
        "race_status": clean_text(raw_race.get("raceStatus")),
        "race_distance": raw_race.get("raceDistance"),
        "track_condition": clean_text(meeting.get("trackCondition")),
        "weather": clean_text(meeting.get("weatherCondition")),
        "runner_count": len(runners),
        "active_runner_count": active_runner_count,
        "runners": runners,
        "scratchings": scratchings,
        "scratched_runner_count": len(scratchings),
        "source": "TAB Web",
    }


def normalise_meeting(raw_meeting):
    location_code = clean_text(raw_meeting.get("location")).upper()

    races = []

    for raw_race in raw_meeting.get("races", []) or []:
        if not isinstance(raw_race, dict):
            continue

        race = normalise_race(raw_race, raw_meeting)

        if race.get("race_number") and race.get("race_datetime"):
            races.append(race)

    races.sort(key=lambda item: item.get("race_number") or 999)

    return {
        "provider": "TAB Web",
        "source": "TAB Web Direct API",
        "meeting_name": clean_text(raw_meeting.get("meetingName")),
        "track": clean_text(raw_meeting.get("meetingName")),
        "country": get_country_from_location(location_code),
        "state": location_code,
        "date": clean_text(raw_meeting.get("meetingDate")),
        "timezone": AUSTRALIAN_TIMEZONE,
        "race_type_code": clean_text(raw_meeting.get("raceType")),
        "venue_code": clean_text(raw_meeting.get("venueMnemonic")),
        "track_condition": clean_text(raw_meeting.get("trackCondition")),
        "weather": clean_text(raw_meeting.get("weatherCondition")),
        "rail_position": clean_text(raw_meeting.get("railPosition")),
        "race_count": len(races),
        "races": races,
        "url": TAB_RACING_URL,
        "races_link": raw_meeting.get("_links", {}).get("races"),
    }


def filter_meetings_to_window(meetings):
    window_start, window_end = get_current_window()

    filtered_meetings = []

    for meeting in meetings:
        filtered_races = []

        for race in meeting.get("races", []) or []:
            race_dt = parse_tab_datetime(race.get("race_datetime"))

            if race_dt and window_start <= race_dt <= window_end:
                filtered_races.append(race)

        if filtered_races:
            updated = dict(meeting)
            updated["races"] = filtered_races
            updated["race_count"] = len(filtered_races)
            filtered_meetings.append(updated)

    return filtered_meetings


def get_tab_web_racelist(
    country="Australia",
    race_type="Horse",
    domestic_only=False,
):
    selected_country = clean_text(country) or "Australia"
    selected_race_type = clean_text(race_type) or "Horse"

    race_type_code = get_race_type_code(selected_race_type)

    try:
        meeting_payloads = fetch_meeting_payloads()

        meetings = []
        seen = set()

        for meetings_payload in meeting_payloads:
            for raw_meeting in meetings_payload.get("meetings", []) or []:
                if not isinstance(raw_meeting, dict):
                    continue

                if not is_supported_race_type(raw_meeting, race_type_code):
                    continue

                meeting = normalise_meeting(raw_meeting)

                if not meeting.get("meeting_name"):
                    continue

                if not meeting.get("races"):
                    continue

                if domestic_only and meeting.get("country") != "Australia":
                    continue

                key = "|".join([
                    normalise_key(meeting.get("meeting_name")),
                    clean_text(meeting.get("date")),
                    clean_text(meeting.get("race_type_code")),
                ])

                if key in seen:
                    continue

                seen.add(key)
                meetings.append(meeting)

        meetings = filter_meetings_to_window(meetings)

        meetings.sort(
            key=lambda item: (
                item.get("country") or "",
                item.get("date") or "",
                item.get("meeting_name") or "",
            )
        )

        return {
            "provider": "TAB Web",
            "source": "TAB Web Direct API",
            "country": selected_country,
            "race_type": selected_race_type,
            "race_type_code": race_type_code,
            "timezone": AUSTRALIAN_TIMEZONE,
            "period": "current_to_end_of_next_racing_day",
            "meeting_count": len(meetings),
            "meetings": meetings,
            "message": (
                "TAB Web racelist loaded."
                if meetings
                else "No TAB Web race meetings returned."
            ),
        }

    except Exception as error:
        return {
            "provider": "TAB Web",
            "source": "TAB Web Direct API",
            "country": selected_country,
            "race_type": selected_race_type,
            "race_type_code": race_type_code,
            "timezone": AUSTRALIAN_TIMEZONE,
            "period": "current_to_end_of_next_racing_day",
            "meeting_count": 0,
            "meetings": [],
            "error": str(error),
            "message": "TAB Web scraper failed.",
        }


def get_tab_web_meeting_races(
    track,
    country="Australia",
    race_type="Horse",
):
    selected_track = normalise_key(track)

    racelist = get_tab_web_racelist(
        country=country,
        race_type=race_type,
    )

    for meeting in racelist.get("meetings", []) or []:
        meeting_name = normalise_key(meeting.get("meeting_name"))

        if selected_track == meeting_name:
            return meeting

        if selected_track and selected_track in meeting_name:
            return meeting

    return {
        "provider": "TAB Web",
        "source": "TAB Web Direct API",
        "track": track,
        "race_count": 0,
        "races": [],
        "message": "No matching TAB Web meeting found.",
    }


if __name__ == "__main__":
    data = get_tab_web_racelist(
        country="Australia",
        race_type="Horse",
        domestic_only=False,
    )

    print("Provider:", data.get("provider"))
    print("Source:", data.get("source"))
    print("Message:", data.get("message"))
    print("Meeting count:", data.get("meeting_count"))

    if data.get("error"):
        print("Error:", data.get("error"))

    print("\nMeetings:")

    for meeting in data.get("meetings", [])[:40]:
        print(
            meeting.get("country"),
            "|",
            meeting.get("meeting_name"),
            "|",
            meeting.get("state"),
            "|",
            meeting.get("date"),
            "| races:",
            meeting.get("race_count"),
        )