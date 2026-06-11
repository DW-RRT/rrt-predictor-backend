def normalise_tab_feed(tab_data):
    normalised_meetings = []

    for meeting in tab_data.get("meetings", []):
        normalised_races = []

        for race in meeting.get("races", []):
            normalised_runners = []

            for runner in race.get("runners", []):
                normalised_runners.append({
                    "number": runner.get("number"),
                    "name": runner.get("name"),
                    "barrier": runner.get("barrier"),
                    "jockey_or_driver":
                        runner.get("jockey")
                        or runner.get("driver"),
                    "trainer": runner.get("trainer"),
                    "fixed_odds": runner.get("fixed_odds"),
                    "form": runner.get("form"),
                })

            normalised_races.append({
                "race_number": race.get("race_number"),
                "race_name": race.get("race_name"),
                "race_time": race.get("race_time"),
                "distance": race.get("distance"),
                "track_condition": race.get("track_condition"),
                "weather": race.get("weather"),
                "runners": normalised_runners,
            })

        normalised_meetings.append({
            "provider": "TAB",
            "country": meeting.get("country"),
            "race_type": meeting.get("race_type"),
            "track": meeting.get("meeting_name"),
            "location": meeting.get("location"),
            "timezone": meeting.get("timezone"),
            "meeting_date": meeting.get("meeting_date"),
            "races": normalised_races,
        })

    return {
        "source": "normalised_tab_feed",
        "meetings": normalised_meetings,
    }