RACE_TIME_OVERRIDES = {
    "toowoomba": {
        1: "17:00",
        2: "17:40",
        3: "18:20",
        4: "19:00",
        5: "19:35",
        6: "20:07",
        7: "20:42",
    },
    "gold coast": {
        1: "12:33",
        2: "13:08",
        3: "13:43",
        4: "14:18",
        5: "14:53",
        6: "15:32",
        7: "16:08",
        8: "16:55",
        9: "17:30",
    },
    "aquis park gold coast": {
        1: "12:33",
        2: "13:08",
        3: "13:43",
        4: "14:18",
        5: "14:53",
        6: "15:32",
        7: "16:08",
        8: "16:55",
        9: "17:30",
    },
    "ascot": {
        1: "13:39",
        2: "14:14",
        3: "14:49",
        4: "15:26",
        5: "16:04",
        6: "16:45",
        7: "17:20",
        8: "18:00",
        9: "18:40",
    },
}


def clean_name(value):
    return str(value or "").strip().lower()


def apply_race_time_overrides(races, track_name, meeting_date, timezone):
    track_key = clean_name(track_name)
    overrides = RACE_TIME_OVERRIDES.get(track_key)

    if not overrides:
        return races

    updated_races = []

    for race in races or []:
        updated_race = dict(race)
        race_number = updated_race.get("race_number")

        try:
            race_number = int(race_number)
        except Exception:
            race_number = None

        if race_number in overrides:
            race_time = overrides[race_number]

            updated_race["race_time"] = race_time
            updated_race["start_time"] = race_time
            updated_race["meeting_date"] = meeting_date
            updated_race["timezone"] = timezone

            if meeting_date:
                updated_race["race_datetime"] = f"{meeting_date}T{race_time}:00"

        updated_races.append(updated_race)

    return updated_races