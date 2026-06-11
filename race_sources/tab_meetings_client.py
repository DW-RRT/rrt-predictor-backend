from datetime import datetime
from zoneinfo import ZoneInfo


REGION_TO_COUNTRY = {
    "NSW": "Australia",
    "VIC": "Australia",
    "QLD": "Australia",
    "SA": "Australia",
    "WA": "Australia",
    "TAS": "Australia",
    "NT": "Australia",
    "ACT": "Australia",
    "NZL": "New Zealand",
    "GBR": "United Kingdom",
    "IRL": "Ireland",
    "USA": "United States",
    "CAN": "Canada",
    "FRA": "France",
    "JPN": "Japan",
    "KOR": "South Korea",
    "ZAF": "South Africa",
    "TUR": "Turkey",
    "CHL": "Chile",
}

REGION_TO_TIMEZONE = {
    "NSW": "Australia/Sydney",
    "ACT": "Australia/Sydney",
    "VIC": "Australia/Melbourne",
    "QLD": "Australia/Brisbane",
    "SA": "Australia/Adelaide",
    "WA": "Australia/Perth",
    "TAS": "Australia/Hobart",
    "NT": "Australia/Darwin",
    "NZL": "Pacific/Auckland",
    "GBR": "Europe/London",
    "IRL": "Europe/Dublin",
    "USA": "America/New_York",
    "CAN": "America/Toronto",
    "FRA": "Europe/Paris",
    "JPN": "Asia/Tokyo",
    "KOR": "Asia/Seoul",
    "ZAF": "Africa/Johannesburg",
    "TUR": "Europe/Istanbul",
    "CHL": "America/Santiago",
}

TAB_ACTIVE_MEETINGS = [
    ("Horse", "Coffs Harbour", "NSW"),
    ("Horse", "Pakenham", "VIC"),
    ("Horse", "Townsville", "QLD"),
    ("Horse", "Port Augusta", "SA"),
    ("Horse", "Canberra", "ACT"),
    ("Horse", "Funabashi", "JPN"),
    ("Horse", "Nagoya", "JPN"),
    ("Horse", "Busan Korea", "KOR"),
    ("Horse", "Fairview", "ZAF"),
    ("Horse", "Istanbul", "TUR"),
    ("Horse", "Bursa", "TUR"),
    ("Horse", "Ascot Uk", "GBR"),
    ("Horse", "Market Rasen", "GBR"),
    ("Horse", "Ripon", "GBR"),
    ("Horse", "Chester", "GBR"),
    ("Horse", "Wolverhampton", "GBR"),
    ("Horse", "Ballinrobe", "IRL"),
    ("Horse", "Downpatrick", "IRL"),
    ("Horse", "Lyon Parilly", "FRA"),
    ("Horse", "Strasbourg", "FRA"),
    ("Horse", "Gulfstream Park", "USA"),
    ("Horse", "Aqueduct", "USA"),
    ("Horse", "Woodbine", "CAN"),
    ("Horse", "Laurel Park", "USA"),
    ("Horse", "Riverton", "NZL"),
    ("Horse", "Remington Park", "USA"),
    ("Horse", "Penn National", "USA"),
    ("Horse", "Charles Town", "USA"),
    ("Horse", "Hipodromo Chile", "CHL"),
    ("Horse", "Horseshoe Indianapolis", "USA"),
    ("Horse", "Southwell", "GBR"),
    ("Horse", "Wexford", "IRL"),
    ("Horse", "Redcar", "GBR"),
    ("Horse", "Thistledown", "USA"),

    ("Horse", "Gosford", "NSW"),
    ("Horse", "Caulfield", "VIC"),
    ("Horse", "Gold Coast", "QLD"),
    ("Horse", "Morphettville", "SA"),
    ("Horse", "Ascot", "WA"),
    ("Horse", "Kembla Grange", "NSW"),
    ("Horse", "Tuncurry", "NSW"),
    ("Horse", "Ararat", "VIC"),
    ("Horse", "Ipswich", "QLD"),
    ("Horse", "Toowoomba", "QLD"),
    ("Horse", "Darwin", "NT"),
    ("Horse", "Port Hedland", "WA"),

    ("Harness", "Newcastle", "NSW"),
    ("Harness", "Geelong", "VIC"),
    ("Harness", "Redcliffe", "QLD"),
    ("Harness", "Gloucester Park", "WA"),
    ("Harness", "Charlton", "VIC"),
    ("Harness", "Wagga", "NSW"),
    ("Harness", "Dubbo", "NSW"),
    ("Harness", "Northam", "WA"),
    ("Harness", "Addington", "NZL"),
    ("Harness", "Alexandra Park", "NZL"),
    ("Harness", "Yonkers", "USA"),
    ("Harness", "Flamboro Downs", "CAN"),
    ("Harness", "Hoosier Park", "USA"),
    ("Harness", "Globe Derby", "SA"),
    ("Harness", "Melton", "VIC"),
    ("Harness", "Menangle", "NSW"),
    ("Harness", "Albion Park", "QLD"),
    ("Harness", "Narrogin", "WA"),

    ("Greyhound", "Richmond", "NSW"),
    ("Greyhound", "Geelong", "VIC"),
    ("Greyhound", "Q1 Lakeside", "QLD"),
    ("Greyhound", "Gawler", "SA"),
    ("Greyhound", "Mandurah", "WA"),
    ("Greyhound", "Traralgon", "VIC"),
    ("Greyhound", "The Gardens", "NSW"),
    ("Greyhound", "Bendigo", "VIC"),
    ("Greyhound", "Wagga", "NSW"),
    ("Greyhound", "Kinsley", "GBR"),
    ("Greyhound", "Newcastle Uk", "GBR"),
    ("Greyhound", "Sheffield", "GBR"),
    ("Greyhound", "Sunderland", "GBR"),
    ("Greyhound", "Healesville", "VIC"),
    ("Greyhound", "Goulburn", "NSW"),
    ("Greyhound", "Townsville", "QLD"),
    ("Greyhound", "Manawatu", "NZL"),
    ("Greyhound", "Addington", "NZL"),
    ("Greyhound", "Taree", "NSW"),
    ("Greyhound", "Broken Hill", "NSW"),
]


def clean_text(value):
    return str(value or "").strip()


def normalise_race_type(value):
    text = clean_text(value).lower()

    if text in ["horse", "horses", "horse racing"]:
        return "Horse"

    if text in ["harness", "harness racing"]:
        return "Harness"

    if text in ["greyhound", "greyhounds", "greyhound racing"]:
        return "Greyhound"

    return clean_text(value)


def build_meeting(race_type, track, region):
    country = REGION_TO_COUNTRY.get(region, region)
    timezone = REGION_TO_TIMEZONE.get(region, "Australia/Sydney")

    return {
        "country": country,
        "race_type": race_type,
        "track": track,
        "meeting_name": track,
        "city": track,
        "region": region,
        "timezone": timezone,
        "url": None,
        "source": "TAB manual active meeting seed",
        "is_active_meeting": True,
        "meeting_datetime": datetime.now(ZoneInfo(timezone)).isoformat(),
    }


def deduplicate_meetings(meetings):
    deduped = {}

    for meeting in meetings:
        track = clean_text(meeting.get("track"))
        race_type = clean_text(meeting.get("race_type"))
        country = clean_text(meeting.get("country"))

        key = f"{race_type.lower()}|{country.lower()}|{track.lower()}"

        if key not in deduped:
            deduped[key] = meeting

    return sorted(
        deduped.values(),
        key=lambda item: (
            item.get("country", ""),
            item.get("race_type", ""),
            item.get("track", ""),
        ),
    )


def get_tab_active_meetings(country=None, race_type="Horse"):
    selected_race_type = normalise_race_type(race_type)

    meetings = []

    for item_race_type, track, region in TAB_ACTIVE_MEETINGS:
        if item_race_type != selected_race_type:
            continue

        meeting = build_meeting(item_race_type, track, region)

        if country and meeting["country"].lower() != country.lower():
            continue

        meetings.append(meeting)

    return deduplicate_meetings(meetings)


def get_all_tab_active_meetings():
    meetings = []

    for race_type, track, region in TAB_ACTIVE_MEETINGS:
        meetings.append(build_meeting(race_type, track, region))

    return deduplicate_meetings(meetings)