from datetime import datetime, UTC


def get_tab_mock_feed():
    return {
        "provider": "TAB",
        "last_updated": datetime.now(UTC).isoformat(),
        "meetings": [
            {
                "meeting_name": "Randwick",
                "country": "Australia",
                "race_type": "Horse",
                "location": "Sydney",
                "timezone": "Australia/Sydney",
                "meeting_date": "2026-05-07",
                "races": [
                    {
                        "race_number": 1,
                        "race_name": "TAB Sprint",
                        "race_time": "13:20",
                        "distance": "1200m",
                        "track_condition": "Good 4",
                        "weather": "Fine",
                        "runners": [
                            {
                                "number": 1,
                                "name": "Fast Horizon",
                                "barrier": 4,
                                "jockey": "J. McDonald",
                                "trainer": "C. Waller",
                                "fixed_odds": 3.2,
                                "form": "1-2-1"
                            },
                            {
                                "number": 2,
                                "name": "Silver Rail",
                                "barrier": 7,
                                "jockey": "T. Clark",
                                "trainer": "G. Waterhouse",
                                "fixed_odds": 5.5,
                                "form": "3-1-4"
                            },
                            {
                                "number": 3,
                                "name": "Track Master",
                                "barrier": 2,
                                "jockey": "J. Collett",
                                "trainer": "B. Baker",
                                "fixed_odds": 8.0,
                                "form": "5-2-2"
                            }
                        ]
                    }
                ]
            },
            {
                "meeting_name": "Menangle",
                "country": "Australia",
                "race_type": "Harness",
                "location": "Sydney",
                "timezone": "Australia/Sydney",
                "meeting_date": "2026-05-07",
                "races": [
                    {
                        "race_number": 1,
                        "race_name": "TAB Harness Mile",
                        "race_time": "18:30",
                        "distance": "1609m",
                        "track_condition": "Fast",
                        "weather": "Clear",
                        "runners": [
                            {
                                "number": 1,
                                "name": "Trotting King",
                                "barrier": 1,
                                "driver": "C. Alford",
                                "trainer": "E. Stewart",
                                "fixed_odds": 2.9,
                                "form": "1-1-2"
                            }
                        ]
                    }
                ]
            }
        ]
    }