import shutil
from pathlib import Path
from datetime import datetime

from fastapi import UploadFile, File

from race_data_importer import import_race_data


UPLOAD_FOLDER = Path("../rrt-predictor/data")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

TARGET_FILENAME = "RRT_Predictor_Upload.xlsx"


def upload_database_excel(
    uploaded_file: UploadFile = File(...)
):
    try:
        filename = uploaded_file.filename or ""

        if not filename.lower().endswith(".xlsx"):
            return {
                "success": False,
                "message": "Only .xlsx Excel files are supported.",
            }

        save_path = UPLOAD_FOLDER / TARGET_FILENAME

        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(uploaded_file.file, buffer)

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
            "message": "Excel database uploaded and imported successfully.",
            "uploaded_filename": filename,
            "stored_filename": TARGET_FILENAME,
            "stored_location": str(save_path.resolve()),
            "uploaded_at": datetime.now().isoformat(),
            "meeting_count": len(meetings),
            "race_count": total_races,
            "runner_count": total_runners,
        }

    except Exception as error:
        return {
            "success": False,
            "message": "Excel upload failed.",
            "error": str(error),
        }