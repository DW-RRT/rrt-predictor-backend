RACENET_BASE_URL = "https://www.racenet.com.au"


def get_racenet_source_status():
    return {
        "source": "Racenet",
        "base_url": RACENET_BASE_URL,
        "status": "placeholder",
        "message": "Racenet source registered. Racecard/form integration to be implemented next.",
    }


def fetch_racenet_meeting_form(country, race_type, track):
    return {
        "source": "Racenet",
        "country": country,
        "race_type": race_type,
        "track": track,
        "available": False,
        "message": "Racenet form feed not connected yet.",
        "races": [],
    }