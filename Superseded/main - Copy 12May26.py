from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from race_sources.tab_web_scraper import (
    get_tab_web_racelist,
    get_tab_web_meeting_races,
)

app = FastAPI(
    title="RRT Predictor Backend",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "app": "RRT Predictor Backend",
        "status": "running",
        "source": "TAB Web",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "source": "TAB Web",
    }


@app.get("/api/races")
def api_races(
    country: str = Query("Australia"),
    race_type: str = Query("Horse"),
    domestic_only: bool = Query(False),
):
    data = get_tab_web_racelist(
        country=country,
        race_type=race_type,
        domestic_only=domestic_only,
    )

    return {
        "success": True,
        "provider": data.get("provider"),
        "source": data.get("source"),
        "country": country,
        "race_type": race_type,
        "meeting_count": data.get("meeting_count"),
        "meetings": data.get("meetings"),
        "message": data.get("message"),
        "error": data.get("error"),
    }


@app.get("/api/meeting")
def api_meeting(
    track: str,
    country: str = Query("Australia"),
    race_type: str = Query("Horse"),
):
    data = get_tab_web_meeting_races(
        track=track,
        country=country,
        race_type=race_type,
    )

    return {
        "success": True,
        "provider": data.get("provider"),
        "source": data.get("source"),
        "track": track,
        "country": country,
        "race_type": race_type,
        "meeting": data,
    }


@app.get("/api/predict")
def api_predict(
    track: str,
    race_number: int,
    country: str = Query("Australia"),
    race_type: str = Query("Horse"),
):
    meeting = get_tab_web_meeting_races(
        track=track,
        country=country,
        race_type=race_type,
    )

    if not meeting or not meeting.get("races"):
        return {
            "success": False,
            "message": "Meeting not found.",
        }

    selected_race = None

    for race in meeting.get("races", []):
        if race.get("race_number") == race_number:
            selected_race = race
            break

    if not selected_race:
        return {
            "success": False,
            "message": "Race not found.",
        }

    scratchings = selected_race.get("scratchings", [])

    active_runner_count = max(
        0,
        (selected_race.get("runner_count") or 0)
        - len(scratchings)
    )

    confidence_base = 72

    if meeting.get("track_condition", "").startswith("HVY"):
        confidence_base -= 8

    if meeting.get("track_condition", "").startswith("SOFT"):
        confidence_base -= 4

    if len(scratchings) >= 5:
        confidence_base -= 5

    confidence_base = max(25, min(confidence_base, 95))

    return {
        "success": True,

        "provider": "TAB Web",

        "prediction_type": "Dynamic Prototype",

        "country": meeting.get("country"),

        "state": meeting.get("state"),

        "race_type": race_type,

        "track": meeting.get("meeting_name"),

        "venue_code": meeting.get("venue_code"),

        "meeting_date": meeting.get("date"),

        "timezone": meeting.get("timezone"),

        "race_number": selected_race.get("race_number"),

        "race_name": selected_race.get("race_name"),

        "race_time": selected_race.get("race_time"),

        "race_distance": selected_race.get("race_distance"),

        "track_condition": selected_race.get("track_condition"),

        "weather": selected_race.get("weather"),

        "race_status": selected_race.get("race_status"),

        "runner_count": selected_race.get("runner_count"),

        "active_runner_count": active_runner_count,

        "scratchings": scratchings,

        "scratched_runner_count": len(scratchings),

        "prediction_summary": {
            "meeting_strength": "Moderate",
            "confidence_score": confidence_base,
            "track_bias": (
                "Wet Track Influence"
                if (
                    "SOFT" in (meeting.get("track_condition") or "")
                    or "HVY" in (meeting.get("track_condition") or "")
                )
                else "Neutral"
            ),
            "scratching_impact": (
                "High"
                if len(scratchings) >= 5
                else "Moderate"
                if len(scratchings) >= 2
                else "Low"
            ),
        },

        "predictions": {
            "best_win_bet": {
                "runner": "Pending Runner Enrichment",
                "confidence": confidence_base,
            },

            "best_each_way": {
                "runner": "Pending Runner Enrichment",
                "confidence": max(confidence_base - 6, 20),
            },

            "best_roughie": {
                "runner": "Pending Runner Enrichment",
                "confidence": max(confidence_base - 18, 10),
            },

            "best_double": {
                "legs": [],
                "status": "Awaiting cross-race analysis",
            },

            "best_quaddie": {
                "legs": [],
                "status": "Awaiting full meeting analysis",
            },
        },

        "source": {
            "meetings": "TAB Web",
            "race_times": "TAB Web",
            "scratchings": "TAB Web",
            "weather": "TAB Web",
            "track_condition": "TAB Web",
            "runners": "Racing Australia (next stage)",
            "form": "Racing Australia (next stage)",
        },
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )