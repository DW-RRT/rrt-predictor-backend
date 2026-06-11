from datetime import datetime, UTC


def make_race(
    race_number,
    race_name,
    race_time,
    distance,
    track_condition,
    weather,
    runners,
):
    return {
        "race_number": race_number,
        "race_name": race_name,
        "race_time": race_time,
        "distance": distance,
        "track_condition": track_condition,
        "weather": weather,
        "runners": runners,
    }


def make_runner(number, name, odds):
    return {
        "number": number,
        "name": name,
        "odds": odds,
    }


def make_track(
    track,
    city,
    timezone,
    meeting_date,
    track_condition,
    weather,
    race_name_prefix,
    race_time,
    distance,
):
    return {
        "track": track,
        "city": city,
        "timezone": timezone,
        "meeting_date": meeting_date,
        "races": [
            make_race(
                1,
                f"{race_name_prefix} Sprint",
                race_time,
                distance,
                track_condition,
                weather,
                [
                    make_runner(1, "Sample Runner A", 3.2),
                    make_runner(2, "Sample Runner B", 5.5),
                    make_runner(3, "Sample Runner C", 9.0),
                ],
            ),
            make_race(
                2,
                f"{race_name_prefix} Classic",
                "14:05",
                "1600m",
                track_condition,
                weather,
                [
                    make_runner(1, "Fast Horizon", 4.0),
                    make_runner(2, "Silver Track", 6.5),
                    make_runner(3, "Rail Runner", 8.0),
                ],
            ),
        ],
    }


def make_harness_track(track, city, timezone, meeting_date):
    return {
        "track": track,
        "city": city,
        "timezone": timezone,
        "meeting_date": meeting_date,
        "races": [
            make_race(
                1,
                "Harness Mile",
                "18:30",
                "1609m",
                "Fast",
                "Clear",
                [
                    make_runner(1, "Trotting King", 3.4),
                    make_runner(2, "Pacing Star", 5.2),
                    make_runner(3, "Gate Speed", 7.0),
                ],
            )
        ],
    }


def make_greyhound_track(track, city, timezone, meeting_date):
    return {
        "track": track,
        "city": city,
        "timezone": timezone,
        "meeting_date": meeting_date,
        "races": [
            make_race(
                1,
                "Greyhound Dash",
                "19:10",
                "520m",
                "Good",
                "Clear",
                [
                    make_runner(1, "Box Speed", 2.9),
                    make_runner(2, "Rail Flyer", 4.8),
                    make_runner(3, "Late Charger", 8.5),
                ],
            )
        ],
    }


def get_mock_races():
    meeting_date = "2026-05-07"

    return {
        "source": "mock",
        "last_updated": datetime.now(UTC).isoformat(),
        "countries": [
            {
                "country": "Australia",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Randwick", "Sydney", "Australia/Sydney", meeting_date, "Good 4", "Fine", "Randwick", "13:20", "1200m"),
                            make_track("Flemington", "Melbourne", "Australia/Melbourne", meeting_date, "Soft 5", "Cloudy", "Flemington", "12:45", "1000m"),
                            make_track("Ascot", "Perth", "Australia/Perth", meeting_date, "Good 4", "Fine", "Ascot", "13:00", "1400m"),
                        ],
                    },
                    {
                        "race_type": "Harness",
                        "tracks": [
                            make_harness_track("Menangle", "Sydney", "Australia/Sydney", meeting_date),
                            make_harness_track("Gloucester Park", "Perth", "Australia/Perth", meeting_date),
                        ],
                    },
                    {
                        "race_type": "Greyhound",
                        "tracks": [
                            make_greyhound_track("Wentworth Park", "Sydney", "Australia/Sydney", meeting_date),
                            make_greyhound_track("Sandown Park", "Melbourne", "Australia/Melbourne", meeting_date),
                        ],
                    },
                ],
            },
            {
                "country": "Canada",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Woodbine", "Toronto", "America/Toronto", meeting_date, "Fast", "Fine", "Woodbine", "13:10", "1200m"),
                        ],
                    },
                    {
                        "race_type": "Harness",
                        "tracks": [
                            make_harness_track("Woodbine Mohawk Park", "Milton", "America/Toronto", meeting_date),
                        ],
                    },
                ],
            },
            {
                "country": "China",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Conghua Racecourse", "Guangzhou", "Asia/Shanghai", meeting_date, "Good", "Fine", "Conghua", "14:00", "1200m"),
                        ],
                    },
                ],
            },
            {
                "country": "France",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Longchamp", "Paris", "Europe/Paris", meeting_date, "Good", "Cloudy", "Longchamp", "13:35", "1600m"),
                            make_track("Chantilly", "Chantilly", "Europe/Paris", meeting_date, "Soft", "Showers", "Chantilly", "14:10", "1400m"),
                        ],
                    },
                    {
                        "race_type": "Harness",
                        "tracks": [
                            make_harness_track("Vincennes", "Paris", "Europe/Paris", meeting_date),
                        ],
                    },
                ],
            },
            {
                "country": "Hong Kong",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Sha Tin", "Hong Kong", "Asia/Hong_Kong", meeting_date, "Good", "Fine", "Sha Tin", "13:00", "1200m"),
                            make_track("Happy Valley", "Hong Kong", "Asia/Hong_Kong", meeting_date, "Good", "Humid", "Happy Valley", "19:15", "1200m"),
                        ],
                    },
                ],
            },
            {
                "country": "India",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Mahalaxmi", "Mumbai", "Asia/Kolkata", meeting_date, "Good", "Warm", "Mahalaxmi", "14:30", "1400m"),
                            make_track("Bangalore Turf Club", "Bengaluru", "Asia/Kolkata", meeting_date, "Good", "Fine", "Bangalore", "15:00", "1200m"),
                        ],
                    },
                ],
            },
            {
                "country": "Ireland",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Curragh", "County Kildare", "Europe/Dublin", meeting_date, "Yielding", "Cloudy", "Curragh", "13:25", "1600m"),
                            make_track("Leopardstown", "Dublin", "Europe/Dublin", meeting_date, "Good", "Showers", "Leopardstown", "14:00", "1400m"),
                        ],
                    },
                ],
            },
            {
                "country": "Japan",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Tokyo Racecourse", "Tokyo", "Asia/Tokyo", meeting_date, "Firm", "Fine", "Tokyo", "13:15", "1600m"),
                            make_track("Hanshin Racecourse", "Takarazuka", "Asia/Tokyo", meeting_date, "Firm", "Fine", "Hanshin", "14:00", "1400m"),
                        ],
                    },
                ],
            },
            {
                "country": "New Zealand",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Ellerslie", "Auckland", "Pacific/Auckland", meeting_date, "Dead 5", "Showers", "Ellerslie", "15:00", "1200m"),
                            make_track("Riccarton Park", "Christchurch", "Pacific/Auckland", meeting_date, "Good 4", "Fine", "Riccarton", "13:40", "1400m"),
                        ],
                    },
                    {
                        "race_type": "Harness",
                        "tracks": [
                            make_harness_track("Addington Raceway", "Christchurch", "Pacific/Auckland", meeting_date),
                        ],
                    },
                    {
                        "race_type": "Greyhound",
                        "tracks": [
                            make_greyhound_track("Manukau Stadium", "Auckland", "Pacific/Auckland", meeting_date),
                        ],
                    },
                ],
            },
            {
                "country": "Singapore",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Kranji", "Singapore", "Asia/Singapore", meeting_date, "Good", "Humid", "Kranji", "18:00", "1200m"),
                        ],
                    },
                ],
            },
            {
                "country": "South Africa",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Kenilworth", "Cape Town", "Africa/Johannesburg", meeting_date, "Good", "Fine", "Kenilworth", "13:30", "1200m"),
                            make_track("Turffontein", "Johannesburg", "Africa/Johannesburg", meeting_date, "Good", "Clear", "Turffontein", "14:15", "1600m"),
                        ],
                    },
                ],
            },
            {
                "country": "United Arab Emirates",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Meydan", "Dubai", "Asia/Dubai", meeting_date, "Fast", "Clear", "Meydan", "18:45", "1600m"),
                        ],
                    },
                ],
            },
            {
                "country": "United Kingdom",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Ascot", "Berkshire", "Europe/London", meeting_date, "Good", "Cloudy", "Ascot UK", "13:50", "1200m"),
                            make_track("Newmarket", "Suffolk", "Europe/London", meeting_date, "Good to Soft", "Cloudy", "Newmarket", "14:20", "1600m"),
                            make_track("Epsom Downs", "Surrey", "Europe/London", meeting_date, "Good", "Fine", "Epsom", "15:00", "2400m"),
                        ],
                    },
                    {
                        "race_type": "Greyhound",
                        "tracks": [
                            make_greyhound_track("Towcester", "Northamptonshire", "Europe/London", meeting_date),
                        ],
                    },
                ],
            },
            {
                "country": "United States",
                "race_types": [
                    {
                        "race_type": "Horse",
                        "tracks": [
                            make_track("Churchill Downs", "Louisville", "America/Kentucky/Louisville", meeting_date, "Fast", "Fine", "Churchill", "13:20", "1200m"),
                            make_track("Santa Anita Park", "Arcadia", "America/Los_Angeles", meeting_date, "Fast", "Clear", "Santa Anita", "14:00", "1600m"),
                            make_track("Belmont Park", "New York", "America/New_York", meeting_date, "Fast", "Cloudy", "Belmont", "13:45", "1400m"),
                        ],
                    },
                    {
                        "race_type": "Harness",
                        "tracks": [
                            make_harness_track("The Meadowlands", "East Rutherford", "America/New_York", meeting_date),
                        ],
                    },
                    {
                        "race_type": "Greyhound",
                        "tracks": [
                            make_greyhound_track("Wheeling Island", "Wheeling", "America/New_York", meeting_date),
                        ],
                    },
                ],
            },
        ],
    }