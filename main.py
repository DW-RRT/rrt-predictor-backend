from fastapi import FastAPI, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Dict, List, Optional
from datetime import datetime
from urllib.parse import quote
import time

from punting_form_client import (
    get_conditions,
    get_meetings_list,
    simplify_conditions_response,
    simplify_meetings_response,
)

from punting_form_prediction_engine import (
    predict_meeting_from_punting_form,
)

from race_sources.tab_web_scraper import (
    get_tab_web_racelist,
    get_tab_web_meeting_races,
)

from race_sources.racing_australia_client import (
    fetch_racing_australia_meeting,
)

from database_prediction_engine import (
    get_database_countries,
    get_database_race_types,
    get_database_meetings,
    predict_meeting,
)

from database_admin_routes import (
    get_database_status,
    reimport_database,
)

from database_upload_routes import (
    upload_database_excel,
)

app = FastAPI(
    title="RRT Predictor Backend",
    version="2.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------

CACHE_TTL_SECONDS = 300
CACHE: Dict[str, Dict[str, Any]] = {}


def _cache_get(key: str) -> Optional[Any]:
    item = CACHE.get(key)

    if not item:
        return None

    if time.time() - item["created_at"] > CACHE_TTL_SECONDS:
        CACHE.pop(key, None)
        return None

    return item["data"]


def _cache_set(key: str, data: Any) -> None:
    CACHE[key] = {
        "created_at": time.time(),
        "data": data,
    }


# ---------------------------------------------------------------------
# Racing Australia helpers
# ---------------------------------------------------------------------

def _normalise_name(name: Optional[str]) -> str:
    return (
        (name or "")
        .upper()
        .replace(".", "")
        .replace("'", "")
        .replace("’", "")
        .strip()
    )


def _title_track_name(track: str) -> str:
    return " ".join(
        word.capitalize()
        for word in (track or "").replace("-", " ").split()
    )


def _build_racing_australia_form_url(
    meeting_date: Optional[str],
    state: Optional[str],
    track: Optional[str],
) -> Optional[str]:
    if not meeting_date or not state or not track:
        return None

    try:
        dt = datetime.strptime(meeting_date, "%Y-%m-%d")
        date_key = dt.strftime("%Y%b%d")
        track_key = _title_track_name(track)
        key = f"{date_key},{state.upper()},{track_key}"
        encoded_key = quote(key, safe="")
        return f"https://www.racingaustralia.horse/FreeFields/Form.aspx?Key={encoded_key}"
    except Exception:
        return None


def _get_meeting_date(meeting: Dict[str, Any]) -> Optional[str]:
    return (
        meeting.get("date")
        or meeting.get("meeting_date")
        or meeting.get("race_date")
    )


def _get_track_from_meeting(
    meeting: Dict[str, Any],
    fallback_track: str,
) -> str:
    return (
        meeting.get("meeting_name")
        or meeting.get("track")
        or meeting.get("venue_name")
        or fallback_track
    )


def get_racing_australia_enrichment(
    meeting: Dict[str, Any],
    track: str,
) -> Dict[str, Any]:
    meeting_date = _get_meeting_date(meeting)
    state = meeting.get("state")
    meeting_track = _get_track_from_meeting(meeting, track)

    meeting_url = _build_racing_australia_form_url(
        meeting_date=meeting_date,
        state=state,
        track=meeting_track,
    )

    if not meeting_url:
        return {
            "provider": "Racing Australia",
            "success": False,
            "message": "Unable to build Racing Australia meeting URL.",
            "races": [],
        }

    cache_key = f"ra:{meeting_url}"
    cached = _cache_get(cache_key)

    if cached:
        return cached

    try:
        ra_data = fetch_racing_australia_meeting(meeting_url)

        if not isinstance(ra_data, dict):
            ra_data = {
                "provider": "Racing Australia",
                "success": False,
                "message": "Invalid Racing Australia response.",
                "races": [],
            }

        ra_data["success"] = bool(ra_data.get("races"))
        ra_data["generated_url"] = meeting_url

        _cache_set(cache_key, ra_data)
        return ra_data

    except Exception as error:
        return {
            "provider": "Racing Australia",
            "success": False,
            "message": "Racing Australia enrichment failed.",
            "error": str(error),
            "generated_url": meeting_url,
            "races": [],
        }


def _extract_ra_races(ra_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(ra_data, dict):
        return []

    if isinstance(ra_data.get("races"), list):
        return ra_data.get("races", [])

    meeting = ra_data.get("meeting")

    if isinstance(meeting, dict) and isinstance(meeting.get("races"), list):
        return meeting.get("races", [])

    return []


def _normalise_ra_runner(
    runner: Dict[str, Any],
    index: int,
    scratched_names: set,
) -> Dict[str, Any]:
    horse_name = (
        runner.get("name")
        or runner.get("horse_name")
        or runner.get("runner")
    )

    runner_key = _normalise_name(horse_name)

    jockey = runner.get("jockey")

    if isinstance(jockey, str) and jockey.strip().isdigit():
        jockey = None

    return {
        "number": runner.get("number") or runner.get("runner_number") or index + 1,
        "name": horse_name,
        "horse_name": horse_name,
        "form": runner.get("form"),
        "trainer": runner.get("trainer"),
        "jockey": jockey,
        "weight": runner.get("weight"),
        "barrier": runner.get("barrier"),
        "scratched": (
            runner_key in scratched_names
            or bool(runner.get("scratched"))
        ),
        "source": "Racing Australia",
        "raw": runner,
    }


def _merge_tab_and_ra_meeting(
    tab_meeting: Dict[str, Any],
    ra_data: Dict[str, Any],
) -> Dict[str, Any]:
    races = tab_meeting.get("races") or []
    ra_races = _extract_ra_races(ra_data)

    ra_by_race_number = {
        race.get("race_number"): race
        for race in ra_races
        if race.get("race_number") is not None
    }

    merged_races = []

    for tab_race in races:
        race_number = tab_race.get("race_number")
        ra_race = ra_by_race_number.get(race_number, {})

        tab_scratchings = tab_race.get("scratchings") or []

        scratched_names = {
            _normalise_name(s.get("name"))
            for s in tab_scratchings
            if isinstance(s, dict)
        }

        ra_runners = ra_race.get("runners") or []

        merged_runners = [
            _normalise_ra_runner(
                runner=runner,
                index=index,
                scratched_names=scratched_names,
            )
            for index, runner in enumerate(ra_runners)
            if isinstance(runner, dict)
        ]

        if merged_runners:
            runner_count = len(merged_runners)
            active_runner_count = len(
                [r for r in merged_runners if not r.get("scratched")]
            )
        else:
            runner_count = tab_race.get("runner_count") or 0
            active_runner_count = max(
                0,
                runner_count - len(tab_scratchings),
            )

        merged_races.append({
            **tab_race,
            "runners": merged_runners,
            "runner_count": runner_count,
            "active_runner_count": active_runner_count,
            "ra_race_name": ra_race.get("race_name"),
            "ra_race_distance": ra_race.get("race_distance"),
            "enrichment": {
                "tab": True,
                "racing_australia": bool(merged_runners),
            },
        })

    return {
        **tab_meeting,
        "races": merged_races,
        "enriched": bool(ra_races),
        "provider_stack": (
            ["TAB Web", "Racing Australia"]
            if ra_races
            else ["TAB Web"]
        ),
        "racing_australia": {
            "success": bool(ra_races),
            "race_count": len(ra_races),
            "meeting_url": ra_data.get("meeting_url"),
            "generated_url": ra_data.get("generated_url"),
            "message": ra_data.get("message"),
            "error": ra_data.get("error"),
        },
    }


# ---------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------

def _calculate_confidence(
    meeting: Dict[str, Any],
    selected_race: Dict[str, Any],
    scratchings: List[Dict[str, Any]],
) -> int:
    confidence_base = 72

    track_condition = (
        selected_race.get("track_condition")
        or meeting.get("track_condition")
        or ""
    ).upper()

    if track_condition.startswith("HVY") or track_condition.startswith("HEAVY"):
        confidence_base -= 8

    if track_condition.startswith("SOFT"):
        confidence_base -= 4

    if len(scratchings) >= 5:
        confidence_base -= 5

    return max(25, min(confidence_base, 95))


def _parse_weight_kg(weight: Optional[str]) -> Optional[float]:
    if not weight:
        return None

    try:
        cleaned = str(weight).lower().replace("kg", "").strip()
        return float(cleaned)
    except Exception:
        return None


def _score_recent_form(form: Optional[str]) -> int:
    if not form:
        return 0

    form = str(form).lower().replace("x", "")
    recent = form[-5:]

    score = 0

    for result in recent:
        if result == "1":
            score += 8
        elif result == "2":
            score += 6
        elif result == "3":
            score += 4
        elif result in ["4", "5"]:
            score += 2
        elif result in ["6", "7", "8", "9", "0"]:
            score -= 1

    return score


def _score_consistency(form: Optional[str]) -> int:
    if not form:
        return 0

    form = str(form).lower().replace("x", "")
    recent = form[-6:]

    if not recent:
        return 0

    placings = len([r for r in recent if r in ["1", "2", "3"]])

    if placings >= 4:
        return 8

    if placings >= 3:
        return 5

    if placings >= 2:
        return 2

    return 0


def _score_weight(weight: Optional[str]) -> int:
    weight_kg = _parse_weight_kg(weight)

    if weight_kg is None:
        return 0

    if weight_kg <= 54:
        return 5

    if weight_kg <= 56:
        return 3

    if weight_kg <= 58:
        return 1

    if weight_kg >= 61:
        return -3

    return 0


def _score_track_condition(
    track_condition: Optional[str],
    form: Optional[str],
) -> int:
    track = (track_condition or "").upper()
    form_text = str(form or "").lower()

    score = 0

    if "HVY" in track or "HEAVY" in track:
        score -= 3

        if "1" in form_text or "2" in form_text:
            score += 2

    elif "SOFT" in track:
        score -= 1

        if "1" in form_text or "2" in form_text or "3" in form_text:
            score += 2

    elif "GOOD" in track:
        score += 2

    return score


def _score_field_position(index: int, field_size: int) -> int:
    if field_size <= 0:
        return 0

    if index < 3:
        return 2

    if index < 6:
        return 1

    if index >= field_size - 3:
        return -1

    return 0


def _runner_basic_score(
    runner: Dict[str, Any],
    index: int,
    track_condition: Optional[str],
    field_size: int = 0,
) -> int:
    if runner.get("scratched"):
        return 0

    score = 60

    form = runner.get("form")
    weight = runner.get("weight")

    score += _score_recent_form(form)
    score += _score_consistency(form)
    score += _score_weight(weight)
    score += _score_track_condition(track_condition, form)
    score += _score_field_position(index, field_size)

    return max(0, min(score, 99))


def _format_prediction_runner(
    runner: Dict[str, Any],
    confidence_base: int,
    confidence_adjustment: int = 0,
) -> Dict[str, Any]:
    return {
        "number": runner.get("number"),
        "runner": runner.get("name"),
        "horse_name": runner.get("horse_name"),
        "form": runner.get("form"),
        "trainer": runner.get("trainer"),
        "jockey": runner.get("jockey"),
        "weight": runner.get("weight"),
        "score": runner.get("score"),
        "confidence": max(
            10,
            min(95, confidence_base + confidence_adjustment),
        ),
    }


def _rank_basic_predictions(
    selected_race: Dict[str, Any],
    confidence_base: int,
) -> Dict[str, Any]:
    runners = selected_race.get("runners") or []
    track_condition = selected_race.get("track_condition")

    active_runners = [
        r for r in runners
        if r.get("name") and not r.get("scratched")
    ]

    if not active_runners:
        return {
            "top_3_win_bets": [],
            "top_3_each_way_bets": [],
            "top_3_roughies": [],
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
        }

    scored = []

    for index, runner in enumerate(active_runners):
        scored.append({
            **runner,
            "score": _runner_basic_score(
                runner=runner,
                index=index,
                track_condition=track_condition,
                field_size=len(active_runners),
            ),
        })

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)

    top_3_win = scored[:3]
    top_3_each_way = scored[1:4] if len(scored) >= 4 else scored[:3]

    if len(scored) >= 6:
        roughies = scored[-4:-1]
    else:
        roughies = scored[-3:]

    return {
        "top_3_win_bets": [
            _format_prediction_runner(runner, confidence_base, 0)
            for runner in top_3_win
        ],
        "top_3_each_way_bets": [
            _format_prediction_runner(runner, confidence_base, -6)
            for runner in top_3_each_way
        ],
        "top_3_roughies": [
            _format_prediction_runner(runner, confidence_base, -18)
            for runner in roughies
        ],
        "best_win_bet": (
            _format_prediction_runner(top_3_win[0], confidence_base, 0)
            if top_3_win
            else None
        ),
        "best_each_way": (
            _format_prediction_runner(top_3_each_way[0], confidence_base, -6)
            if top_3_each_way
            else None
        ),
        "best_roughie": (
            _format_prediction_runner(roughies[0], confidence_base, -18)
            if roughies
            else None
        ),
    }


def _build_meeting_multis(
    meeting: Dict[str, Any],
) -> Dict[str, Any]:
    races = meeting.get("races") or []

    enriched_races = [
        race for race in races
        if race.get("runners")
    ]

    double_legs = []
    quaddie_legs = []

    for race in enriched_races:
        race_predictions = _rank_basic_predictions(
            selected_race=race,
            confidence_base=70,
        )

        top_win = race_predictions.get("top_3_win_bets") or []

        if not top_win:
            continue

        leg = {
            "race_number": race.get("race_number"),
            "race_name": race.get("race_name"),
            "race_time": race.get("race_time"),
            "selections": top_win[:3],
        }

        double_legs.append(leg)
        quaddie_legs.append(leg)

    return {
        "best_double": {
            "legs": double_legs[:2],
            "status": (
                "Active"
                if len(double_legs) >= 2
                else "Awaiting enough enriched races"
            ),
        },
        "best_quaddie": {
            "legs": quaddie_legs[:4],
            "status": (
                "Active"
                if len(quaddie_legs) >= 4
                else "Awaiting enough enriched races"
            ),
        },
    }


# ---------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------

def _get_tab_racelist_cached(
    country: str,
    race_type: str,
    domestic_only: bool,
) -> Dict[str, Any]:
    cache_key = f"tab_racelist:{country}:{race_type}:{domestic_only}"
    cached = _cache_get(cache_key)

    if cached:
        return cached

    data = get_tab_web_racelist(
        country=country,
        race_type=race_type,
        domestic_only=domestic_only,
    )

    _cache_set(cache_key, data)
    return data


def _get_tab_meeting_cached(
    track: str,
    country: str,
    race_type: str,
) -> Dict[str, Any]:
    cache_key = f"tab_meeting:{country}:{race_type}:{track}"
    cached = _cache_get(cache_key)

    if cached:
        return cached

    data = get_tab_web_meeting_races(
        track=track,
        country=country,
        race_type=race_type,
    )

    _cache_set(cache_key, data)
    return data


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "app": "RRT Predictor Backend",
        "status": "running",
        "source": "Stored Excel Database + TAB Web + Racing Australia",
        "version": "2.5.0",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "source": "RRT Predictor Live Race Data",
        "provider": "Race Data API",
        "version": "2.6.0",
        "cache_ttl_seconds": 300
    }

# ---------------------------------------------------------------------
# Stored Excel Database Routes
# ---------------------------------------------------------------------

@app.get("/api/database-countries")
def api_database_countries():
    countries = get_database_countries()

    return {
        "success": True,
        "source": "RRT Stored Race Database",
        "countries": countries,
        "country_count": len(countries),
    }


@app.get("/api/database-race-types")
def api_database_race_types(country: Optional[str] = Query(None)):
    race_types = get_database_race_types(country=country)

    return {
        "success": True,
        "source": "RRT Stored Race Database",
        "country": country,
        "race_types": race_types,
        "race_type_count": len(race_types),
    }


@app.get("/api/database-races")
def api_database_races(
    country: Optional[str] = Query(None),
    race_type: Optional[str] = Query(None),
):
    meetings = get_database_meetings(
        country=country,
        race_type=race_type,
    )

    return {
        "success": True,
        "provider": "RRT Stored Race Database",
        "source": "Uploaded Excel",
        "country": country,
        "race_type": race_type,
        "meeting_count": len(meetings),
        "meetings": meetings,
    }


@app.get("/api/database-predict")
def api_database_predict(track: str):
    return predict_meeting(track)

@app.get("/api/database-status")
def api_database_status():
    return get_database_status()


@app.post("/api/database-reimport")
def api_database_reimport():
    return reimport_database()

# ---------------------------------------------------------------------
# Database Upload Route
# ---------------------------------------------------------------------

@app.post("/api/database-upload")
async def api_database_upload(
    uploaded_file: UploadFile = File(...)
):
    return upload_database_excel(uploaded_file)

# ---------------------------------------------------------------------
# Original TAB / Racing Australia Routes
# ---------------------------------------------------------------------

@app.get("/api/races")
def api_races(
    country: str = Query("Australia"),
    race_type: str = Query("Horse"),
    domestic_only: bool = Query(False),
):
    data = _get_tab_racelist_cached(
        country=country,
        race_type=race_type,
        domestic_only=domestic_only,
    )

    return {
        "success": not bool(data.get("error")),
        "provider": data.get("provider"),
        "source": data.get("source"),
        "country": country,
        "race_type": race_type,
        "domestic_only": domestic_only,
        "meeting_count": data.get("meeting_count"),
        "meetings": data.get("meetings"),
        "message": data.get("message"),
        "error": data.get("error"),
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
    }


@app.get("/api/meeting")
def api_meeting(
    track: str,
    country: str = Query("Australia"),
    race_type: str = Query("Horse"),
    enrich: bool = Query(True),
):
    tab_meeting = _get_tab_meeting_cached(
        track=track,
        country=country,
        race_type=race_type,
    )

    if not tab_meeting:
        return {
            "success": False,
            "message": "Meeting not found.",
        }

    if not enrich:
        return {
            "success": True,
            "provider": tab_meeting.get("provider"),
            "source": tab_meeting.get("source"),
            "track": track,
            "country": country,
            "race_type": race_type,
            "meeting": tab_meeting,
        }

    ra_data = get_racing_australia_enrichment(
        meeting=tab_meeting,
        track=track,
    )

    merged_meeting = _merge_tab_and_ra_meeting(
        tab_meeting=tab_meeting,
        ra_data=ra_data,
    )

    return {
        "success": True,
        "provider": "TAB Web + Racing Australia",
        "source": "Merged",
        "track": track,
        "country": country,
        "race_type": race_type,
        "meeting": merged_meeting,
    }


@app.get("/api/predict")
def api_predict(
    track: str,
    race_number: int,
    country: str = Query("Australia"),
    race_type: str = Query("Horse"),
    enrich: bool = Query(True),
):
    tab_meeting = _get_tab_meeting_cached(
        track=track,
        country=country,
        race_type=race_type,
    )

    if not tab_meeting or not tab_meeting.get("races"):
        return {
            "success": False,
            "message": "Meeting not found.",
        }

    if enrich:
        ra_data = get_racing_australia_enrichment(
            meeting=tab_meeting,
            track=track,
        )

        meeting = _merge_tab_and_ra_meeting(
            tab_meeting=tab_meeting,
            ra_data=ra_data,
        )
    else:
        meeting = tab_meeting

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

    scratchings = selected_race.get("scratchings") or []
    active_runner_count = selected_race.get("active_runner_count")

    if active_runner_count is None:
        active_runner_count = max(
            0,
            (selected_race.get("runner_count") or 0) - len(scratchings),
        )

    confidence_base = _calculate_confidence(
        meeting=meeting,
        selected_race=selected_race,
        scratchings=scratchings,
    )

    ranked_predictions = _rank_basic_predictions(
        selected_race=selected_race,
        confidence_base=confidence_base,
    )

    meeting_multis = _build_meeting_multis(meeting)

    track_condition = (
        selected_race.get("track_condition")
        or meeting.get("track_condition")
    )

    weather = (
        selected_race.get("weather")
        or meeting.get("weather")
    )

    runners = selected_race.get("runners") or []

    return {
        "success": True,
        "provider": (
            "TAB Web + Racing Australia"
            if runners
            else "TAB Web"
        ),
        "prediction_type": (
            "Runner Enriched Prototype"
            if runners
            else "Dynamic Prototype"
        ),
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
        "track_condition": track_condition,
        "weather": weather,
        "race_status": selected_race.get("race_status"),
        "runner_count": selected_race.get("runner_count"),
        "active_runner_count": active_runner_count,
        "runners": runners,
        "scratchings": scratchings,
        "scratched_runner_count": len(scratchings),
        "prediction_summary": {
            "meeting_strength": "Moderate",
            "confidence_score": confidence_base,
            "track_bias": (
                "Wet Track Influence"
                if (
                    "SOFT" in ((track_condition or "").upper())
                    or "HVY" in ((track_condition or "").upper())
                    or "HEAVY" in ((track_condition or "").upper())
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
            "runner_enrichment": (
                "Active"
                if runners
                else "Pending Racing Australia parser connection"
            ),
            "scoring_model": "Form + track + weight + field position. Jockey/trainer excluded.",
        },
        "predictions": {
            **ranked_predictions,
            **meeting_multis,
        },
        "source": {
            "meetings": "TAB Web",
            "race_times": "TAB Web",
            "scratchings": "TAB Web",
            "weather": "TAB Web",
            "track_condition": "TAB Web",
            "runners": (
                "Racing Australia"
                if runners
                else "Racing Australia pending"
            ),
            "form": (
                "Racing Australia"
                if runners
                else "Racing Australia pending"
            ),
        },
    }

# ---------------------------------------------------------------------
# Punting Form Routes (RRT Predictor v2)
# ---------------------------------------------------------------------

@app.get("/api/punting-form-meetings")
def api_punting_form_meetings(
    meeting_date: str,
):
    try:
        response = get_meetings_list(
            meeting_date=meeting_date
        )

        return simplify_meetings_response(response)

    except Exception as error:
        return {
            "success": False,
            "provider": "Punting Form",
            "error": str(error),
        }



@app.get("/api/punting-form-conditions")
def api_punting_form_conditions():
    try:
        response = get_conditions()
        return simplify_conditions_response(response)

    except Exception as error:
        return {
            "success": False,
            "provider": "Punting Form",
            "error": str(error),
        }


@app.get("/api/punting-form-predict")
def api_punting_form_predict(
    meeting_id: int,
    race_number: int = 0,
    runs: int = 10,
):
    try:
        return predict_meeting_from_punting_form(
            meeting_id=meeting_id,
            race_number=race_number,
            runs=runs,
        )

    except Exception as error:
        return {
            "success": False,
            "provider": "Punting Form",
            "meeting_id": meeting_id,
            "error": str(error),
        }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )