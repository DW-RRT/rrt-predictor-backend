import os
from typing import Any, Dict, List, Optional

import requests


PUNTING_FORM_BASE_URL = "https://api.puntingform.com.au"


def get_api_key() -> str:
    api_key = os.getenv("PUNTING_FORM_API_KEY", "").strip()

    if not api_key:
        raise ValueError(
            "Missing PUNTING_FORM_API_KEY. Set it in PowerShell before running the backend."
        )

    return api_key


def make_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    api_key = get_api_key()

    request_params = dict(params or {})
    request_params["apiKey"] = api_key

    url = f"{PUNTING_FORM_BASE_URL}{endpoint}"

    response = requests.get(
        url,
        params=request_params,
        headers={"accept": "application/json"},
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def get_meetings_list(
    meeting_date: str,
    stage: str = "A",
    include_barrier_trials: bool = False,
) -> Dict[str, Any]:
    return make_request(
        "/v2/form/meetingslist",
        {
            "meetingDate": meeting_date,
            "stage": stage,
            "includeBarrierTrials": include_barrier_trials,
        },
    )


def get_meeting_form(
    meeting_id: int,
    race_number: int = 0,
    runs: int = 10,
) -> Dict[str, Any]:
    return make_request(
        "/v2/form/form",
        {
            "meetingId": meeting_id,
            "raceNumber": race_number,
            "runs": runs,
        },
    )


def get_meeting(
    meeting_id: int,
) -> Dict[str, Any]:
    return make_request(
        "/v2/form/meeting",
        {
            "meetingId": meeting_id,
        },
    )


def get_conditions() -> Dict[str, Any]:
    return make_request(
        "/v2/Updates/Conditions",
        {},
    )


def get_meeting_ratings(
    meeting_id: int,
) -> Dict[str, Any]:
    return make_request(
        "/v2/Ratings/MeetingRatings",
        {
            "meetingId": meeting_id,
        },
    )


def get_scratchings() -> Dict[str, Any]:
    return make_request(
        "/v2/Updates/Scratchings",
        {},
    )


def get_results(
    meeting_id: int,
) -> Dict[str, Any]:
    return make_request(
        "/v2/form/results",
        {
            "meetingId": meeting_id,
        },
    )


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _format_track_condition(condition: Any, condition_number: Any) -> str:
    condition = _clean_text(condition)
    condition_number = _clean_text(condition_number)

    if condition and condition_number:
        return f"{condition} {condition_number}"

    return condition or condition_number or "Not currently supplied."


def safe_sort_int(value: Any, default: int = 999) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def simplify_scratchings_response(api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    scratchings: List[Dict[str, Any]] = []

    for item in api_response.get("payLoad") or []:
        scratchings.append(
            {
                "meeting_id": str(item.get("meetingId") or "").strip(),
                "race_id": str(item.get("raceId") or "").strip(),
                "runner_id": str(item.get("runnerId") or "").strip(),
                "meeting_date": item.get("meetingDate"),
                "meeting_date_utc": item.get("meetingDateUTC"),
                "track": _clean_text(item.get("track")),
                "race_no": item.get("raceNo"),
                "tab_no": item.get("tabNo"),
                "time_stamp": item.get("timeStamp"),
                "deduction": item.get("deduction"),
                "country": item.get("country"),
                "code": item.get("code"),
                "raw": item,
            }
        )

    return scratchings


def simplify_results_response(api_response: Dict[str, Any]) -> Dict[str, Any]:
    payload = api_response.get("payLoad") or []

    meetings: List[Dict[str, Any]] = []
    all_race_results: List[Dict[str, Any]] = []

    for meeting in payload:
        race_results: List[Dict[str, Any]] = []

        for race in meeting.get("raceResults") or []:
            runners: List[Dict[str, Any]] = []

            for runner in race.get("runners") or []:
                runners.append(
                    {
                        "position": runner.get("position"),
                        "margin": runner.get("margin"),
                        "tab_number": runner.get("tabNo"),
                        "runner": _clean_text(runner.get("runner")),
                        "runner_id": runner.get("runnerId"),
                        "trainer": _clean_text(runner.get("trainer")),
                        "trainer_id": runner.get("trainerId"),
                        "jockey": _clean_text(runner.get("jockey")),
                        "jockey_id": runner.get("jockeyId"),
                        "barrier": runner.get("barrier"),
                        "original_barrier": runner.get("originalBarrier"),
                        "weight": runner.get("weight"),
                        "weight_total": runner.get("weightTotal"),
                        "weight_allocated": runner.get("weightAllocated"),
                        "weight_adjustment": runner.get("weightAdjustment"),
                        "jockey_claim": runner.get("jockeyClaim"),
                        "price": runner.get("price"),
                        "flucs": runner.get("flucs"),
                        "in_run": runner.get("inRun"),
                        "gear_changes": runner.get("gearChanges"),
                        "stewards_reports": runner.get("stewardsReports"),
                        "form_id": runner.get("formId"),
                        "raw": runner,
                    }
                )

            runners.sort(key=lambda item: safe_sort_int(item.get("position"), 999))

            winner = next(
                (runner for runner in runners if safe_sort_int(runner.get("position"), 999) == 1),
                None,
            )

            placegetters = [
                runner for runner in runners
                if safe_sort_int(runner.get("position"), 999) in [1, 2, 3]
            ]

            simplified_race = {
                "meeting_id": meeting.get("meetingId"),
                "track": _clean_text(meeting.get("track")),
                "track_id": meeting.get("trackId"),
                "meeting_date": meeting.get("meetingDate"),
                "race_id": race.get("raceId"),
                "race_number": race.get("raceNumber"),
                "distance_m": race.get("distance"),
                "race_class": _clean_text(race.get("raceClass")),
                "weight_type": _clean_text(race.get("weightType")),
                "limit_weight": race.get("limitWeight"),
                "track_condition": _clean_text(race.get("trackConditionLabel")),
                "track_condition_code": race.get("trackCondition"),
                "track_condition_number": race.get("trackConditionNumber"),
                "official_race_time": race.get("officialRaceTime"),
                "official_race_time_string": race.get("officialRaceTimeString"),
                "sectional_distance": race.get("sectionalDistance"),
                "official_sectional_time": race.get("officialSectionalTime"),
                "wind_direction": race.get("windDirection"),
                "wind_speed": race.get("windSpeed"),
                "runner_count": len(runners),
                "winner": winner,
                "placegetters": placegetters,
                "runners": runners,
                "raw": race,
            }

            race_results.append(simplified_race)
            all_race_results.append(simplified_race)

        race_results.sort(key=lambda item: safe_sort_int(item.get("race_number"), 999))

        meetings.append(
            {
                "meeting_id": meeting.get("meetingId"),
                "track": _clean_text(meeting.get("track")),
                "track_id": meeting.get("trackId"),
                "meeting_date": meeting.get("meetingDate"),
                "results_updated": meeting.get("resultsUpdated"),
                "race_count": len(race_results),
                "race_results": race_results,
                "raw": meeting,
            }
        )

    return {
        "success": api_response.get("statusCode") == 200,
        "provider": "Punting Form",
        "source": "Punting Form API - Results",
        "meeting_count": len(meetings),
        "race_count": len(all_race_results),
        "meetings": meetings,
        "race_results": all_race_results,
        "raw_status_code": api_response.get("statusCode"),
        "raw_error": api_response.get("error"),
        "time_stamp": api_response.get("timeStamp"),
        "process_time": api_response.get("processTime"),
    }


def simplify_meetings_response(api_response: Dict[str, Any]) -> Dict[str, Any]:
    meetings = []

    for item in api_response.get("payLoad") or []:
        track = item.get("track") or {}

        meetings.append(
            {
                "meeting_id": item.get("meetingId"),
                "track": track.get("name"),
                "track_id": track.get("trackId"),
                "state": track.get("state"),
                "country": track.get("country"),
                "surface": track.get("surface"),
                "location_type": track.get("location"),
                "abbrev": track.get("abbrev"),
                "meeting_date": item.get("meetingDate"),
                "rail_position": item.get("railPosition"),
                "expected_condition": item.get("expectedCondition"),
                "tab_meeting": item.get("tabMeeting"),
                "has_sectionals": item.get("hasSectionals"),
                "form_updated": item.get("formUpdated"),
                "ratings_updated": item.get("ratingsUpdated"),
                "results_updated": item.get("resultsUpdated"),
            }
        )

    return {
        "success": api_response.get("statusCode") == 200,
        "provider": "Punting Form",
        "source": "Punting Form API",
        "meeting_count": len(meetings),
        "meetings": meetings,
        "raw_status_code": api_response.get("statusCode"),
        "raw_error": api_response.get("error"),
    }


def simplify_meeting_response(api_response: Dict[str, Any]) -> Dict[str, Any]:
    payload = api_response.get("payLoad") or {}
    track = payload.get("track") or {}

    races: List[Dict[str, Any]] = []

    for race in payload.get("races") or []:
        races.append(
            {
                "race_id": str(race.get("raceId") or ""),
                "race_number": race.get("number"),
                "race_name": _clean_text(race.get("name")),
                "provider_race_id": race.get("providerRaceId"),
                "distance_m": race.get("distance"),
                "age_restrictions": race.get("ageRestrictions"),
                "jockey_restrictions": race.get("jockeyRestrictions"),
                "weight_type": race.get("weightType"),
                "limit_weight": race.get("limitWeight"),
                "race_class": _clean_text(race.get("raceClass")),
                "prize_money": race.get("prizeMoney"),
                "start_time": race.get("startTime"),
                "start_time_utc": race.get("startTimeUTC"),
                "group": _clean_text(race.get("group")),
                "bonus_scheme": race.get("bonusScheme"),
                "description": _clean_text(race.get("description")),
                "prize_money_breakdown": race.get("prizeMoneyBreakDown"),
                "sex_restrictions": race.get("sexRestrictions"),
                "runner_count": len(race.get("runners") or []),
            }
        )

    races.sort(key=lambda item: safe_sort_int(item.get("race_number"), 999))

    return {
        "success": api_response.get("statusCode") == 200,
        "provider": "Punting Form",
        "source": "Punting Form API - Meeting",
        "meeting_id": payload.get("meetingId"),
        "meeting_date": payload.get("meetingDate"),
        "track": {
            "name": track.get("name"),
            "track_id": track.get("trackId"),
            "location": track.get("location"),
            "state": track.get("state"),
            "country": track.get("country"),
            "abbrev": track.get("abbrev"),
            "surface": track.get("surface"),
        },
        "race_count": len(races),
        "races": races,
        "raw_status_code": api_response.get("statusCode"),
        "raw_error": api_response.get("error"),
        "time_stamp": api_response.get("timeStamp"),
        "process_time": api_response.get("processTime"),
    }


def simplify_form_response(api_response: Dict[str, Any]) -> Dict[str, Any]:
    runners = api_response.get("payLoad") or []

    grouped_races: Dict[str, Dict[str, Any]] = {}
    race_number_by_id: Dict[str, int] = {}

    for runner in runners:
        race_id = str(runner.get("raceId") or "unknown")

        if race_id not in race_number_by_id:
            race_number_by_id[race_id] = len(race_number_by_id) + 1

        inferred_race_number = race_number_by_id[race_id]

        forms = runner.get("forms") or []
        latest_form = forms[0] if forms else {}

        if race_id not in grouped_races:
            grouped_races[race_id] = {
                "race_id": race_id,
                "race_number": inferred_race_number,
                "race_name": latest_form.get("raceName"),
                "distance_m": latest_form.get("distance"),
                "race_class": latest_form.get("raceClass"),
                "track_condition": latest_form.get("trackCondition"),
                "track_condition_number": latest_form.get("trackConditionNumber"),
                "prize_money": latest_form.get("prizeMoney"),
                "runners": [],
            }

        grouped_races[race_id]["runners"].append(
            {
                "runner_id": runner.get("runnerId"),
                "horse_name": runner.get("name"),
                "country": runner.get("country"),
                "age": runner.get("age"),
                "sex": runner.get("sex"),
                "sire": runner.get("sire"),
                "dam": runner.get("dam"),
                "trainer": (runner.get("trainer") or {}).get("fullName"),
                "trainer_id": (runner.get("trainer") or {}).get("trainerId"),
                "jockey": (runner.get("jockey") or {}).get("fullName"),
                "jockey_id": (runner.get("jockey") or {}).get("jockeyId"),
                "barrier": runner.get("barrier"),
                "original_barrier": runner.get("originalBarrier"),
                "tab_number": runner.get("tabNo"),
                "weight_kg": runner.get("weight"),
                "jockey_claim": runner.get("jockeyClaim"),
                "gear_changes": runner.get("gearChanges"),
                "price_sp": runner.get("priceSP"),
                "last10": runner.get("last10"),
                "win_pct": runner.get("winPct"),
                "place_pct": runner.get("placePct"),
                "career_starts": runner.get("careerStarts"),
                "career_wins": runner.get("careerWins"),
                "career_seconds": runner.get("careerSeconds"),
                "career_thirds": runner.get("careerThirds"),
                "prize_money": runner.get("prizeMoney"),
                "track_record": runner.get("trackRecord"),
                "distance_record": runner.get("distanceRecord"),
                "track_distance_record": runner.get("trackDistRecord"),
                "firm_record": runner.get("firmRecord"),
                "good_record": runner.get("goodRecord"),
                "soft_record": runner.get("softRecord"),
                "heavy_record": runner.get("heavyRecord"),
                "first_up_record": runner.get("firstUpRecord"),
                "second_up_record": runner.get("secondUpRecord"),
                "trainer_a2e_career": runner.get("trainerA2E_Career"),
                "jockey_a2e_career": runner.get("jockeyA2E_Career"),
                "trainer_jockey_a2e_career": runner.get("trainerJockeyA2E_Career"),
                "trainer_a2e_last100": runner.get("trainerA2E_Last100"),
                "jockey_a2e_last100": runner.get("jockeyA2E_Last100"),
                "trainer_jockey_a2e_last100": runner.get("trainerJockeyA2E_Last100"),
                "emergencyIndicator": runner.get("emergencyIndicator"),
                "scratched": bool(runner.get("scratched") or runner.get("isScratched")),
                "status": runner.get("status"),
                "historical_forms": forms,
            }
        )

    races = list(grouped_races.values())
    races.sort(key=lambda race: race.get("race_number") or 999)

    return {
        "success": api_response.get("statusCode") == 200,
        "provider": "Punting Form",
        "source": "Punting Form API",
        "race_count": len(races),
        "runner_count": len(runners),
        "races": races,
        "raw_status_code": api_response.get("statusCode"),
        "raw_error": api_response.get("error"),
    }


def simplify_conditions_response(api_response: Dict[str, Any]) -> Dict[str, Any]:
    conditions: List[Dict[str, Any]] = []

    for item in api_response.get("payLoad") or []:
        track_condition = _clean_text(item.get("trackCondition"))
        track_condition_number = _clean_text(item.get("trackConditionNumber"))
        weather = _clean_text(item.get("weather"))

        conditions.append(
            {
                "meeting_id": item.get("meetingId"),
                "meeting_date": item.get("meetingDate"),
                "track": _clean_text(item.get("track")),
                "track_condition": track_condition,
                "track_condition_number": track_condition_number,
                "track_condition_display": _format_track_condition(
                    track_condition,
                    track_condition_number,
                ),
                "weather": weather or "Not currently supplied.",
                "wind": item.get("wind"),
                "wind_direction": item.get("windDirection"),
                "abandoned": bool(item.get("abandonded")),
                "rail": _clean_text(item.get("rail")),
                "penetrometer": _clean_text(item.get("penetrometer")),
                "irrigation": _clean_text(item.get("irrigation")),
                "rainfall": _clean_text(item.get("rainfall")),
                "comment": _clean_text(item.get("comment")),
                "last_update": item.get("lastUpdate"),
            }
        )

    return {
        "success": api_response.get("statusCode") == 200,
        "provider": "Punting Form",
        "source": "Punting Form API - Updates Conditions",
        "condition_count": len(conditions),
        "conditions": conditions,
        "raw_status_code": api_response.get("statusCode"),
        "raw_error": api_response.get("error"),
        "time_stamp": api_response.get("timeStamp"),
        "process_time": api_response.get("processTime"),
    }


def simplify_ratings_response(api_response: Dict[str, Any]) -> Dict[str, Any]:
    ratings: List[Dict[str, Any]] = []

    for item in api_response.get("payLoad") or []:
        ratings.append(
            {
                "meeting_date": item.get("meetingDate"),
                "track": _clean_text(item.get("track")),
                "meeting_id": item.get("meetingId"),
                "race_id": str(item.get("raceId") or ""),
                "runner_id": item.get("runnerId"),
                "race_number": item.get("raceNo"),
                "runner_name": _clean_text(item.get("runnerName")),
                "tab_number": item.get("tabNo"),
                "is_reliable": bool(item.get("isReliable")),
                "barrier": item.get("barrier"),
                "track_condition": item.get("trackCondition"),
                "pf_ai_score": item.get("pfaiScore"),
                "pf_ai_price": item.get("pfaiPrice"),
                "pf_ai_rank": item.get("pfaiRank"),
                "neural_price": item.get("neuralPrice"),
                "neural_price_rank": item.get("neuralPriceRank"),
                "weight_class_rank": item.get("weightClassRank"),
                "weight_class_price": item.get("weightClassPrice"),
                "time_adjusted_weight_class_rank": item.get("timeAdjustedWeightClassRank"),
                "time_adjusted_weight_class_price": item.get("timeAdjustedWeightClassPrice"),
                "class_change": item.get("classChange"),
                "predicted_settle_position": item.get("predictedSettlePostion"),
                "average_historical_settle_position": item.get("averageHistoricalSettlePosition"),
                "run_style": _clean_text(item.get("runStyle")),
                "time_rank": item.get("timeRank"),
                "time_price": item.get("timePrice"),
                "early_time_rank": item.get("earlyTimeRank"),
                "early_time_price": item.get("earlyTimePrice"),
                "last_600_time_rank": item.get("last600TimeRank"),
                "last_600_time_price": item.get("last600TimePrice"),
                "last_400_time_rank": item.get("last400TimeRank"),
                "last_400_time_price": item.get("last400TimePrice"),
                "last_200_time_rank": item.get("last200TimeRank"),
                "last_200_time_price": item.get("last200TimePrice"),
                "raw": item,
            }
        )

    return {
        "success": api_response.get("statusCode") == 200,
        "provider": "Punting Form",
        "source": "Punting Form API - Meeting Ratings",
        "rating_count": len(ratings),
        "ratings": ratings,
        "raw_status_code": api_response.get("statusCode"),
        "raw_error": api_response.get("error"),
        "time_stamp": api_response.get("timeStamp"),
        "process_time": api_response.get("processTime"),
    }
