MEETING_ALIASES = {
    "gold coast": [
        "Aquis Park Gold Coast",
        "Gold Coast",
    ],
    "pakenham": [
        "Southside Pakenham",
        "Pakenham",
    ],
    "ballarat": [
        "Sportsbet-Ballarat",
        "Ballarat",
    ],
    "gladstone": [
        "Sportsbet Gladstone",
        "Gladstone",
    ],
    "bowen": [
        "Sportsbet Bowen",
        "Bowen",
    ],
    "longreach": [
        "Sportsbet Longreach",
        "Longreach",
    ],
}


def clean_name(value):
    return str(value or "").strip().lower()


def get_possible_meeting_names(track_name):
    cleaned = clean_name(track_name)

    names = [track_name]

    if cleaned in MEETING_ALIASES:
        names.extend(MEETING_ALIASES[cleaned])

    return list(dict.fromkeys(names))