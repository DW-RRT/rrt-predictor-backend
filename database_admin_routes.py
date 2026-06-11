from pathlib import Path
from datetime import datetime

from race_data_importer import import_race_data
from database_prediction_engine import load_race_database


DATABASE_PATH = Path("race_database.json")


def get_database_status():
    exists = DATABASE_PATH.exists()

    if not exists:
        return {
            "success": False,
            "database_exists": False,
            "message": "race_database.json not found.",
        }

    try:
        data = load_race_database()

        meetings = data.get("meetings", [])

        countries = sorted({
            meeting.get("country")
            for meeting in meetings
            if meeting.get("country")
        })

        race_types = sorted({
            meeting.get("race_type")
            for meeting in meetings
            if meeting.get("race_type")
        })

        total_races = sum(
            len(meeting.get("races", []))
            for meeting in meetings
        )

        total_runners = sum(
            meeting.get("runner_count", 0)
            for meeting in meetings
        )

        modified_time = datetime.fromtimestamp(
            DATABASE_PATH.stat().st_mtime
        ).isoformat()

        return {
            "success": True,
            "database_exists": True,
            "database_path": str(DATABASE_PATH.resolve()),
            "last_modified": modified_time,
            "meeting_count": len(meetings),
            "race_count": total_races,
            "runner_count": total_runners,
            "countries": countries,
            "race_types": race_types,
            "source": "Stored Excel Database",
        }

    except Exception as error:
        return {
            "success": False,
            "database_exists": True,
            "message": "Unable to read database.",
            "error": str(error),
        }


def reimport_database():
    try:
        result = import_race_data()

        meetings = result.get("meetings", [])

        total_races = sum(
            len(meeting.get("races", []))
            for meeting in meetings
        )

        total_runners = sum(
            meeting.get("runner_count", 0)
            for meeting in meetings
        )

        return {
            "success": True,
            "message": "Race database re-imported successfully.",
            "meeting_count": len(meetings),
            "race_count": total_races,
            "runner_count": total_runners,
            "generated_at": result.get("generated_at"),
            "source_file": result.get("source_file"),
            "database_file": str(DATABASE_PATH.resolve()),
        }

    except Exception as error:
        return {
            "success": False,
            "message": "Database re-import failed.",
            "error": str(error),
        }