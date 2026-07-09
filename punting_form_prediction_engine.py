from typing import Any, Dict, List, Optional

from punting_form_client import (
    get_conditions,
    get_meeting,
    get_meeting_form,
    get_meeting_ratings,
    get_scratchings,
    simplify_conditions_response,
    simplify_form_response,
    simplify_meeting_response,
    simplify_ratings_response,
    simplify_scratchings_response,

)


MODEL_VERSION = "2.8.1"
PREDICTION_TYPE = "RRT Predictor v2.15.0 - Punting Form Weighted Model v1.3 + Factor Capture + Roughie Refinement"

SCORING_WEIGHTS = {
    "recent_form_last10": 0.15,
    "win_place": 0.08,
    "track_record": 0.08,
    "distance_record": 0.09,
    "track_distance_record": 0.09,
    "track_condition_record": 0.12,
    "trainer_a2e": 0.10,
    "jockey_a2e": 0.08,
    "trainer_jockey_a2e_combo": 0.12,
    "barrier": 0.04,
    "weight_carried": 0.02,
    "market_price": 0.03,
}

PF_AI_STRATEGY = {
    "active": False,
    "weight": 0.00,
    "status": "Monitoring only",
    "purpose": "PF AI values are merged and reported for comparison, but not used in RRT scoring.",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(value, maximum))


def normalise_text(value: Any) -> str:
    return (
        str(value or "")
        .upper()
        .replace(".", "")
        .replace("'", "")
        .replace("’", "")
        .replace("-", " ")
        .strip()
    )


def normalise_date(value: Any) -> str:
    text = str(value or "").strip()

    if "T" in text:
        return text.split("T")[0]

    return text[:10]


def record_score(record: Optional[Dict[str, Any]]) -> float:
    if not record:
        return 50.0

    starts = safe_int(record.get("starts"), 0)
    wins = safe_int(record.get("firsts"), 0)
    seconds = safe_int(record.get("seconds"), 0)
    thirds = safe_int(record.get("thirds"), 0)

    if starts <= 0:
        return 50.0

    win_rate = wins / starts
    place_rate = (wins + seconds + thirds) / starts

    return clamp((win_rate * 70) + (place_rate * 30))


def score_last10(last10: Any) -> float:
    text = str(last10 or "").strip().lower().replace("x", "")

    if not text:
        return 50.0

    results = [char for char in text if char.isdigit()]
    recent = results[-6:]

    if not recent:
        return 50.0

    score = 50.0

    for index, result in enumerate(recent):
        recency_multiplier = 1 + (index * 0.06)

        if result == "1":
            score += 9 * recency_multiplier
        elif result == "2":
            score += 7 * recency_multiplier
        elif result == "3":
            score += 5 * recency_multiplier
        elif result in ["4", "5"]:
            score += 2 * recency_multiplier
        elif result in ["6", "7"]:
            score -= 1.5 * recency_multiplier
        elif result in ["8", "9", "0"]:
            score -= 3 * recency_multiplier

    return clamp(score)


def score_price(price_sp: Any) -> float:
    price = safe_float(price_sp, 0)

    if price <= 0:
        return 50.0
    if price <= 2:
        return 100.0
    if price <= 3:
        return 92.0
    if price <= 5:
        return 82.0
    if price <= 8:
        return 70.0
    if price <= 12:
        return 58.0
    if price <= 20:
        return 45.0
    if price <= 40:
        return 32.0

    return 20.0


def score_barrier(barrier: Any, field_size: int) -> float:
    barrier_number = safe_int(barrier, 0)

    if barrier_number <= 0:
        return 50.0

    if field_size <= 8:
        if 1 <= barrier_number <= 4:
            return 85.0
        if barrier_number <= 6:
            return 70.0
        return 55.0

    if 2 <= barrier_number <= 6:
        return 85.0
    if barrier_number in [1, 7, 8]:
        return 72.0
    if 9 <= barrier_number <= 12:
        return 55.0

    return 38.0


def score_weight(weight_kg: Any) -> float:
    weight = safe_float(weight_kg, 56.0)

    if weight <= 52:
        return 88.0
    if weight <= 54:
        return 80.0
    if weight <= 56:
        return 70.0
    if weight <= 58:
        return 60.0
    if weight <= 60:
        return 48.0

    return 36.0


def score_a2e(record: Optional[Dict[str, Any]]) -> float:
    if not record:
        return 50.0

    a2e = safe_float(record.get("a2E"), 0)
    strike_rate = safe_float(record.get("strikeRate"), 0)
    runners = safe_int(record.get("runners"), 0)

    if runners <= 0:
        return 50.0

    a2e_score = clamp(a2e * 50, 0, 100)
    strike_score = clamp(strike_rate * 3, 0, 100)
    sample_confidence = clamp(runners / 100, 0.25, 1.0)

    return clamp(((a2e_score * 0.6) + (strike_score * 0.4)) * sample_confidence)


def score_win_place(win_pct: Any, place_pct: Any) -> float:
    win = safe_float(win_pct, 0)
    place = safe_float(place_pct, 0)

    return clamp((win * 0.65) + (place * 0.35))


def get_track_condition_record(runner: Dict[str, Any], track_condition: str) -> Dict[str, Any]:
    condition = str(track_condition or "").upper()

    if condition.startswith("G"):
        return runner.get("good_record") or {}
    if condition.startswith("S"):
        return runner.get("soft_record") or {}
    if condition.startswith("H"):
        return runner.get("heavy_record") or {}
    if condition.startswith("F"):
        return runner.get("firm_record") or {}
    if condition.startswith("SYN"):
        return runner.get("synthetic_record") or {}

    return {}


def is_barrier_trial_race(race: Dict[str, Any]) -> bool:
    race_name = str(race.get("race_name") or "").lower()
    race_class = str(race.get("race_class") or "").lower()

    return "barrier trial" in race_name or "barrier trial" in race_class


def is_valid_runner(runner: Dict[str, Any]) -> bool:
    name = str(runner.get("horse_name") or "").strip()

    if not name:
        return False

    if runner.get("emergencyIndicator") is True:
        return False

    if runner.get("scratched") is True:
        return False

    return True


def _rating_payload_from_runner(runner: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pf_ai_score": runner.get("pf_ai_score"),
        "pf_ai_price": runner.get("pf_ai_price"),
        "pf_ai_rank": runner.get("pf_ai_rank"),
        "is_reliable": runner.get("rating_is_reliable"),
        "run_style": runner.get("run_style"),
        "predicted_settle_position": runner.get("predicted_settle_position"),
        "time_rank": runner.get("time_rank"),
        "early_time_rank": runner.get("early_time_rank"),
        "last_600_time_rank": runner.get("last_600_time_rank"),
        "last_400_time_rank": runner.get("last_400_time_rank"),
        "last_200_time_rank": runner.get("last_200_time_rank"),
        "class_change": runner.get("class_change"),
    }


def _runner_factor_key(
    runner: Dict[str, Any],
    race: Optional[Dict[str, Any]] = None,
) -> str:
    race = race or {}
    race_id = str(race.get("race_id") or runner.get("race_id") or "").strip()
    race_number = str(race.get("race_number") or runner.get("race_number") or "").strip()
    runner_id = str(runner.get("runner_id") or "").strip()
    tab_number = str(runner.get("tab_number") or runner.get("number") or "").strip()
    runner_name = normalise_text(runner.get("horse_name") or runner.get("runner"))

    if runner_id and runner_id != "0":
        return f"runner_id:{runner_id}"

    return f"race:{race_id or race_number}|tab:{tab_number}|name:{runner_name}"


def build_weighted_breakdown(score_breakdown: Dict[str, Any]) -> Dict[str, float]:
    weighted = {
        "last10_form": safe_float(score_breakdown.get("last10_form")) * SCORING_WEIGHTS["recent_form_last10"],
        "win_place": safe_float(score_breakdown.get("win_place")) * SCORING_WEIGHTS["win_place"],
        "track_record": safe_float(score_breakdown.get("track_record")) * SCORING_WEIGHTS["track_record"],
        "distance_record": safe_float(score_breakdown.get("distance_record")) * SCORING_WEIGHTS["distance_record"],
        "track_distance_record": safe_float(score_breakdown.get("track_distance_record")) * SCORING_WEIGHTS["track_distance_record"],
        "track_condition_record": safe_float(score_breakdown.get("track_condition_record")) * SCORING_WEIGHTS["track_condition_record"],
        "trainer": safe_float(score_breakdown.get("trainer")) * SCORING_WEIGHTS["trainer_a2e"],
        "jockey": safe_float(score_breakdown.get("jockey")) * SCORING_WEIGHTS["jockey_a2e"],
        "trainer_jockey": safe_float(score_breakdown.get("trainer_jockey")) * SCORING_WEIGHTS["trainer_jockey_a2e_combo"],
        "barrier": safe_float(score_breakdown.get("barrier")) * SCORING_WEIGHTS["barrier"],
        "weight": safe_float(score_breakdown.get("weight")) * SCORING_WEIGHTS["weight_carried"],
        "market_price": safe_float(score_breakdown.get("market_price")) * SCORING_WEIGHTS["market_price"],
    }

    return {
        key: round(value, 4)
        for key, value in weighted.items()
    }


def build_factor_capture_runner(runner: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "runner_key": runner.get("runner_key"),
        "race_id": runner.get("race_id"),
        "race_number": runner.get("race_number"),
        "race_name": runner.get("race_name"),
        "race_title": runner.get("race_title"),
        "distance_m": runner.get("distance_m"),
        "track_condition": runner.get("track_condition"),
        "runner_id": runner.get("runner_id"),
        "tab_number": runner.get("tab_number"),
        "number": runner.get("tab_number"),
        "runner": runner.get("horse_name"),
        "horse_name": runner.get("horse_name"),
        "trainer": runner.get("trainer"),
        "jockey": runner.get("jockey"),
        "barrier": runner.get("barrier"),
        "weight": runner.get("weight_kg"),
        "last10": runner.get("last10"),
        "price": runner.get("price"),
        "market_rank": runner.get("market_rank"),
        "score": runner.get("score"),
        "confidence": runner.get("confidence"),
        "score_breakdown": runner.get("score_breakdown"),
        "weighted_breakdown": runner.get("weighted_breakdown"),
        "scoring_weights": SCORING_WEIGHTS,
        "pf_ai": runner.get("pf_ai") or _rating_payload_from_runner(runner),
        "pf_ai_strategy": runner.get("pf_ai_strategy") or PF_AI_STRATEGY,
    }




def score_runner(
    runner: Dict[str, Any],
    race: Dict[str, Any],
    field_size: int,
) -> Dict[str, Any]:
    track_condition = race.get("track_condition") or ""

    last10_score = score_last10(runner.get("last10"))
    win_place_score = score_win_place(runner.get("win_pct"), runner.get("place_pct"))
    track_score = record_score(runner.get("track_record"))
    distance_score = record_score(runner.get("distance_record"))
    track_distance_score = record_score(runner.get("track_distance_record"))
    condition_score = record_score(get_track_condition_record(runner, track_condition))

    trainer_score = (
        score_a2e(runner.get("trainer_a2e_last100")) * 0.65
        + score_a2e(runner.get("trainer_a2e_career")) * 0.35
    )

    jockey_score = (
        score_a2e(runner.get("jockey_a2e_last100")) * 0.65
        + score_a2e(runner.get("jockey_a2e_career")) * 0.35
    )

    trainer_jockey_score = (
        score_a2e(runner.get("trainer_jockey_a2e_last100")) * 0.70
        + score_a2e(runner.get("trainer_jockey_a2e_career")) * 0.30
    )

    barrier_score = score_barrier(runner.get("barrier"), field_size)
    weight_score = score_weight(runner.get("weight_kg"))
    market_score = score_price(runner.get("price_sp"))

    final_score = (
        last10_score * SCORING_WEIGHTS["recent_form_last10"]
        + win_place_score * SCORING_WEIGHTS["win_place"]
        + track_score * SCORING_WEIGHTS["track_record"]
        + distance_score * SCORING_WEIGHTS["distance_record"]
        + track_distance_score * SCORING_WEIGHTS["track_distance_record"]
        + condition_score * SCORING_WEIGHTS["track_condition_record"]
        + trainer_score * SCORING_WEIGHTS["trainer_a2e"]
        + jockey_score * SCORING_WEIGHTS["jockey_a2e"]
        + trainer_jockey_score * SCORING_WEIGHTS["trainer_jockey_a2e_combo"]
        + barrier_score * SCORING_WEIGHTS["barrier"]
        + weight_score * SCORING_WEIGHTS["weight_carried"]
        + market_score * SCORING_WEIGHTS["market_price"]
    )

    final_score = round(clamp(final_score), 1)

    confidence = round(
        clamp(
            35
            + ((final_score - 40) * 1.25)
            + ((trainer_jockey_score - 50) * 0.08)
            + ((condition_score - 50) * 0.06),
            20,
            95,
        ),
        1,
    )

    price = safe_float(runner.get("price_sp"), 0)

    score_breakdown = {
        "last10_form": round(last10_score, 1),
        "win_place": round(win_place_score, 1),
        "track_record": round(track_score, 1),
        "distance_record": round(distance_score, 1),
        "track_distance_record": round(track_distance_score, 1),
        "track_condition_record": round(condition_score, 1),
        "trainer": round(trainer_score, 1),
        "jockey": round(jockey_score, 1),
        "trainer_jockey": round(trainer_jockey_score, 1),
        "barrier": round(barrier_score, 1),
        "weight": round(weight_score, 1),
        "market_price": round(market_score, 1),
    }

    weighted_breakdown = build_weighted_breakdown(score_breakdown)

    return {
        **runner,
        "runner_key": _runner_factor_key(runner, race),
        "race_id": race.get("race_id"),
        "race_name": race.get("race_name"),
        "race_number": race.get("race_number"),
        "race_label": f"Race {race.get('race_number')}",
        "race_title": f"Race {race.get('race_number')} – {race.get('race_name')}",
        "distance_m": race.get("distance_m"),
        "track_condition": race.get("track_condition"),
        "score": final_score,
        "confidence": confidence,
        "price": price,
        "market_rank": None,
        "pf_ai": _rating_payload_from_runner(runner),
        "pf_ai_strategy": PF_AI_STRATEGY,
        "score_breakdown": score_breakdown,
        "weighted_breakdown": weighted_breakdown,
        "factor_capture": {
            "runner_key": _runner_factor_key(runner, race),
            "raw_component_scores": score_breakdown,
            "weighted_component_scores": weighted_breakdown,
            "final_score": final_score,
            "confidence": confidence,
            "scoring_weights": SCORING_WEIGHTS,
        },
    }


def assign_market_ranks(scored_runners: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    priced = [
        runner for runner in scored_runners
        if safe_float(runner.get("price"), 0) > 0
    ]

    priced_sorted = sorted(priced, key=lambda item: safe_float(item.get("price"), 9999))

    price_rank = {
        id(runner): index + 1
        for index, runner in enumerate(priced_sorted)
    }

    for runner in scored_runners:
        runner["market_rank"] = price_rank.get(id(runner), 99)

    return scored_runners


def format_reason(runner: Dict[str, Any], category: str = "standard") -> str:
    breakdown = runner.get("score_breakdown") or {}
    reasons = []

    if category == "roughie":
        if safe_int(runner.get("market_rank"), 99) >= 6:
            reasons.append("outside the main market but still rates competitively")
        if safe_float(runner.get("price"), 0) >= 7:
            reasons.append("available at a value roughie price")

    if safe_float(breakdown.get("last10_form")) >= 70:
        reasons.append("strong recent form profile")

    if safe_float(breakdown.get("track_condition_record")) >= 65:
        reasons.append("suited to the track condition")

    if safe_float(breakdown.get("distance_record")) >= 65:
        reasons.append("positive distance record")

    if safe_float(breakdown.get("trainer_jockey")) >= 65:
        reasons.append("strong trainer/jockey profile")

    if safe_float(breakdown.get("barrier")) >= 80:
        reasons.append("favourable barrier")

    if safe_float(breakdown.get("market_price")) >= 80 and category != "roughie":
        reasons.append("well supported in the market")

    if not reasons:
        reasons.append("balanced profile across the RRT scoring model")

    return ", ".join(reasons).capitalize() + "."


def format_runner(runner: Dict[str, Any], category: str = "standard") -> Dict[str, Any]:
    return {
        "number": runner.get("tab_number"),
        "runner": runner.get("horse_name"),
        "horse_name": runner.get("horse_name"),
        "trainer": runner.get("trainer"),
        "jockey": runner.get("jockey"),
        "barrier": runner.get("barrier"),
        "weight": runner.get("weight_kg"),
        "price": runner.get("price"),
        "market_rank": runner.get("market_rank"),
        "last10": runner.get("last10"),
        "score": runner.get("score"),
        "confidence": runner.get("confidence"),

        "race_id": runner.get("race_id"),
        "race_name": runner.get("race_name"),
        "race_number": runner.get("race_number"),
        "race_label": runner.get("race_label"),
        "race_title": runner.get("race_title"),

        "distance_m": runner.get("distance_m"),
        "reason": format_reason(runner, category=category),
        "score_breakdown": runner.get("score_breakdown"),
        "weighted_breakdown": runner.get("weighted_breakdown"),
        "factor_capture": runner.get("factor_capture"),
        "runner_key": runner.get("runner_key"),
        "runner_id": runner.get("runner_id"),
        "tab_number": runner.get("tab_number"),
        "pf_ai": runner.get("pf_ai") or _rating_payload_from_runner(runner),
        "pf_ai_strategy": runner.get("pf_ai_strategy") or PF_AI_STRATEGY,
    }


def score_race(race: Dict[str, Any]) -> List[Dict[str, Any]]:
    if is_barrier_trial_race(race):
        return []

    runners = [
        runner for runner in race.get("runners", [])
        if is_valid_runner(runner)
    ]

    scored = [
        score_runner(runner, race, len(runners))
        for runner in runners
    ]

    scored = assign_market_ranks(scored)

    return sorted(scored, key=lambda item: item.get("score", 0), reverse=True)


def select_roughies(
    all_ranked: List[Dict[str, Any]],
    excluded: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    excluded_ids = {
        f"{runner.get('race_id')}|{runner.get('tab_number')}|{runner.get('horse_name')}"
        for runner in excluded
    }

    roughies = []

    for runner in all_ranked:
        runner_id = f"{runner.get('race_id')}|{runner.get('tab_number')}|{runner.get('horse_name')}"

        if runner_id in excluded_ids:
            continue

        market_rank = safe_int(runner.get("market_rank"), 99)
        score = safe_float(runner.get("score"), 0)
        price = safe_float(runner.get("price"), 0)

        if price > 0 and price >= 7 and market_rank >= 5 and score >= 50:
            roughies.append(runner)

    return sorted(
        roughies,
        key=lambda item: (
            safe_float(item.get("score"), 0),
            safe_float(item.get("price"), 0),
        ),
        reverse=True,
    )[:4]


def build_multis(races: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked_races = []

    for race in races:
        ranked = score_race(race)

        if not ranked:
            continue

        ranked_races.append(
            {
                "race_id": race.get("race_id"),
                "race_number": race.get("race_number"),
                "race_label": f"Race {race.get('race_number')}",
                "race_name": race.get("race_name"),
                "race_title": f"Race {race.get('race_number')} – {race.get('race_name')}",
                "distance_m": race.get("distance_m"),
                "selections": [
                    format_runner(runner)
                    for runner in ranked[:3]
                ],
            }
        )

    return {
        "best_double": {
            "legs": ranked_races[:2],
            "status": "Active" if len(ranked_races) >= 2 else "Awaiting enough eligible races",
        },
        "best_quaddie": {
            "legs": ranked_races[:4],
            "status": "Active" if len(ranked_races) >= 4 else "Awaiting enough eligible races",
        },
    }


def get_meeting_track_from_form_data(form_data: Dict[str, Any]) -> str:
    races = form_data.get("races") or []

    for race in races:
        historical_forms = []

        for runner in race.get("runners") or []:
            historical_forms.extend(runner.get("historical_forms") or [])

        for form in historical_forms:
            track = form.get("track") or form.get("trackName")

            if track:
                return str(track)

    return ""


def get_meeting_date_from_form_data(form_data: Dict[str, Any]) -> str:
    races = form_data.get("races") or []

    for race in races:
        historical_forms = []

        for runner in race.get("runners") or []:
            historical_forms.extend(runner.get("historical_forms") or [])

        for form in historical_forms:
            date_value = (
                form.get("meetingDate")
                or form.get("raceDate")
                or form.get("date")
            )

            if date_value:
                return normalise_date(date_value)

    return ""


def fetch_condition_for_meeting(
    meeting_id: Optional[int],
    form_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        raw_conditions = get_conditions()
        simplified = simplify_conditions_response(raw_conditions)
        conditions = simplified.get("conditions") or []

        meeting_id_int = safe_int(meeting_id, 0)

        if meeting_id_int > 0:
            for condition in conditions:
                if safe_int(condition.get("meeting_id"), 0) == meeting_id_int:
                    return {
                        **condition,
                        "matched_by": "meeting_id",
                        "conditions_success": simplified.get("success"),
                    }

        form_track = get_meeting_track_from_form_data(form_data or {})
        form_date = get_meeting_date_from_form_data(form_data or {})

        normalised_form_track = normalise_text(form_track)
        normalised_form_date = normalise_date(form_date)

        if normalised_form_track and normalised_form_date:
            for condition in conditions:
                if (
                    normalise_text(condition.get("track")) == normalised_form_track
                    and normalise_date(condition.get("meeting_date")) == normalised_form_date
                ):
                    return {
                        **condition,
                        "matched_by": "track_and_date",
                        "conditions_success": simplified.get("success"),
                    }

        return {
            "track_condition_display": "Not currently supplied.",
            "weather": "Not currently supplied.",
            "matched_by": "not_matched",
            "conditions_success": simplified.get("success"),
        }

    except Exception as error:
        return {
            "track_condition_display": "Not currently supplied.",
            "weather": "Not currently supplied.",
            "matched_by": "conditions_error",
            "conditions_success": False,
            "error": str(error),
        }


def fetch_ratings_for_meeting(
    meeting_id: Optional[int],
) -> Dict[str, Any]:
    try:
        meeting_id_int = safe_int(meeting_id, 0)

        if meeting_id_int <= 0:
            return {
                "success": False,
                "ratings": [],
                "rating_count": 0,
                "matched_by": "invalid_meeting_id",
            }

        raw_ratings = get_meeting_ratings(meeting_id_int)
        simplified = simplify_ratings_response(raw_ratings)

        return {
            **simplified,
            "matched_by": "meeting_id",
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "Punting Form",
            "source": "Punting Form API - Meeting Ratings",
            "ratings": [],
            "rating_count": 0,
            "matched_by": "ratings_error",
            "error": str(error),
        }



def fetch_scratchings_for_meeting(
    meeting_id: Optional[int],
) -> Dict[str, Any]:
    try:
        meeting_id_text = str(safe_int(meeting_id, 0))

        if meeting_id_text == "0":
            return {
                "success": False,
                "provider": "Punting Form",
                "source": "Punting Form API - Updates Scratchings",
                "scratchings": [],
                "scratching_count": 0,
                "matched_by": "invalid_meeting_id",
            }

        raw_scratchings = get_scratchings()
        all_scratchings = simplify_scratchings_response(raw_scratchings)

        meeting_scratchings = [
            scratching for scratching in all_scratchings
            if str(scratching.get("meeting_id") or "").strip() == meeting_id_text
        ]

        return {
            "success": raw_scratchings.get("statusCode") == 200,
            "provider": "Punting Form",
            "source": "Punting Form API - Updates Scratchings",
            "scratchings": meeting_scratchings,
            "scratching_count": len(meeting_scratchings),
            "all_scratchings_count": len(all_scratchings),
            "matched_by": "meeting_id",
            "raw_status_code": raw_scratchings.get("statusCode"),
            "raw_error": raw_scratchings.get("error"),
            "time_stamp": raw_scratchings.get("timeStamp"),
            "process_time": raw_scratchings.get("processTime"),
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "Punting Form",
            "source": "Punting Form API - Updates Scratchings",
            "scratchings": [],
            "scratching_count": 0,
            "matched_by": "scratchings_error",
            "error": str(error),
        }


def build_scratchings_indexes(
    scratchings: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    by_runner_id: Dict[str, Dict[str, Any]] = {}
    by_race_tab: Dict[str, Dict[str, Any]] = {}
    by_race_number_tab: Dict[str, Dict[str, Any]] = {}

    for scratching in scratchings:
        runner_id = str(scratching.get("runner_id") or "").strip()
        race_id = str(scratching.get("race_id") or "").strip()
        race_number = str(scratching.get("race_no") or "").strip()
        tab_number = str(scratching.get("tab_no") or "").strip()

        if runner_id and runner_id != "0":
            by_runner_id[runner_id] = scratching

        if race_id and race_id != "0" and tab_number:
            by_race_tab[f"{race_id}|{tab_number}"] = scratching

        if race_number and tab_number:
            by_race_number_tab[f"{race_number}|{tab_number}"] = scratching

    return {
        "by_runner_id": by_runner_id,
        "by_race_tab": by_race_tab,
        "by_race_number_tab": by_race_number_tab,
    }


def merge_scratchings_into_form_data(
    form_data: Dict[str, Any],
    scratchings_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    scratchings = (scratchings_data or {}).get("scratchings") or []
    indexes = build_scratchings_indexes(scratchings)

    total_runner_count = 0
    form_scratched_count = 0
    scratchings_matched_count = 0
    excluded_scratchings = []
    enriched_races = []

    for race in form_data.get("races") or []:
        enriched_runners = []

        race_id = str(race.get("race_id") or "").strip()
        race_number = str(race.get("race_number") or "").strip()

        for runner in race.get("runners") or []:
            total_runner_count += 1

            runner_id = str(runner.get("runner_id") or "").strip()
            tab_number = str(runner.get("tab_number") or "").strip()

            if runner.get("scratched") is True:
                form_scratched_count += 1

            scratching = None

            if runner_id and runner_id != "0":
                scratching = indexes["by_runner_id"].get(runner_id)

            if not scratching and race_id and race_id != "0" and tab_number:
                scratching = indexes["by_race_tab"].get(f"{race_id}|{tab_number}")

            if not scratching and race_number and tab_number:
                scratching = indexes["by_race_number_tab"].get(f"{race_number}|{tab_number}")

            is_scratched = bool(runner.get("scratched") or scratching)

            if scratching:
                scratchings_matched_count += 1
                excluded_scratchings.append(
                    {
                        "race_id": race.get("race_id"),
                        "race_number": race.get("race_number"),
                        "race_name": race.get("race_name"),
                        "tab_number": runner.get("tab_number"),
                        "runner_id": runner.get("runner_id"),
                        "runner": runner.get("horse_name"),
                        "track": scratching.get("track"),
                        "scratching_time": scratching.get("time_stamp"),
                        "deduction": scratching.get("deduction"),
                    }
                )

            enriched_runners.append(
                {
                    **runner,
                    "scratched": is_scratched,
                    "scratchings_matched": bool(scratching),
                    "scratching_details": scratching,
                }
            )

        enriched_races.append(
            {
                **race,
                "runners": enriched_runners,
            }
        )

    return {
        **form_data,
        "races": enriched_races,
        "scratchings_merge": {
            "scratchings_success": bool((scratchings_data or {}).get("success")),
            "scratchings_source": (scratchings_data or {}).get("source"),
            "scratchings_matched_by": (scratchings_data or {}).get("matched_by"),
            "scratchings_available_count": len(scratchings),
            "form_runner_count": total_runner_count,
            "form_scratched_count": form_scratched_count,
            "scratchings_matched_count": scratchings_matched_count,
            "scratchings_excluded_count": scratchings_matched_count + form_scratched_count,
            "scratchings_unmatched_count": max(len(scratchings) - scratchings_matched_count, 0),
            "excluded_scratchings": excluded_scratchings,
        },
    }

def fetch_meeting_metadata(
    meeting_id: Optional[int],
) -> Dict[str, Any]:
    try:
        meeting_id_int = safe_int(meeting_id, 0)

        if meeting_id_int <= 0:
            return {
                "success": False,
                "races": [],
                "race_count": 0,
                "matched_by": "invalid_meeting_id",
            }

        raw_meeting = get_meeting(meeting_id_int)
        simplified = simplify_meeting_response(raw_meeting)

        return {
            **simplified,
            "matched_by": "meeting_id",
        }

    except Exception as error:
        return {
            "success": False,
            "provider": "Punting Form",
            "source": "Punting Form API - Meeting",
            "races": [],
            "race_count": 0,
            "matched_by": "meeting_error",
            "error": str(error),
        }


def build_meeting_race_indexes(
    meeting_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    by_race_id: Dict[str, Dict[str, Any]] = {}
    by_race_number: Dict[str, Dict[str, Any]] = {}

    for race in (meeting_metadata or {}).get("races") or []:
        race_id = str(race.get("race_id") or "").strip()
        race_number = str(race.get("race_number") or "").strip()

        if race_id:
            by_race_id[race_id] = race

        if race_number:
            by_race_number[race_number] = race

    return {
        "by_race_id": by_race_id,
        "by_race_number": by_race_number,
    }


def merge_meeting_metadata_into_form_data(
    form_data: Dict[str, Any],
    meeting_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    indexes = build_meeting_race_indexes(meeting_metadata)
    matched_count = 0
    enriched_races = []

    for race in form_data.get("races") or []:
        race_id = str(race.get("race_id") or "").strip()
        race_number = str(race.get("race_number") or "").strip()

        metadata = None

        if race_id:
            metadata = indexes["by_race_id"].get(race_id)

        if not metadata and race_number:
            metadata = indexes["by_race_number"].get(race_number)

        if metadata:
            matched_count += 1
            official_race_name = metadata.get("race_name") or race.get("race_name")
            enriched_races.append(
                {
                    **race,
                    "race_number": metadata.get("race_number") or race.get("race_number"),
                    "race_name": official_race_name,
                    "official_race_name": official_race_name,
                    "provider_race_id": metadata.get("provider_race_id"),
                    "distance_m": metadata.get("distance_m") or race.get("distance_m"),
                    "race_class": metadata.get("race_class") or race.get("race_class"),
                    "prize_money": metadata.get("prize_money") or race.get("prize_money"),
                    "start_time": metadata.get("start_time"),
                    "start_time_utc": metadata.get("start_time_utc"),
                    "age_restrictions": metadata.get("age_restrictions"),
                    "jockey_restrictions": metadata.get("jockey_restrictions"),
                    "weight_type": metadata.get("weight_type"),
                    "description": metadata.get("description"),
                    "race_metadata_source": "Punting Form Meeting API",
                }
            )
        else:
            enriched_races.append(
                {
                    **race,
                    "official_race_name": race.get("race_name"),
                    "race_metadata_source": "Punting Form Form API fallback",
                }
            )

    race_count = len(form_data.get("races") or [])

    return {
        **form_data,
        "races": enriched_races,
        "meeting_metadata_merge": {
            "meeting_success": bool((meeting_metadata or {}).get("success")),
            "meeting_source": (meeting_metadata or {}).get("source"),
            "meeting_matched_by": (meeting_metadata or {}).get("matched_by"),
            "meeting_race_count": len((meeting_metadata or {}).get("races") or []),
            "form_race_count": race_count,
            "race_name_matched_count": matched_count,
            "race_name_unmatched_count": max(race_count - matched_count, 0),
            "track": (meeting_metadata or {}).get("track"),
            "meeting_date": (meeting_metadata or {}).get("meeting_date"),
        },
    }


def build_rating_indexes(ratings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    by_runner_id: Dict[str, Dict[str, Any]] = {}
    by_race_tab: Dict[str, Dict[str, Any]] = {}
    by_race_number_tab: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}

    for rating in ratings:
        runner_id = str(rating.get("runner_id") or "").strip()
        race_id = str(rating.get("race_id") or "").strip()
        race_number = str(rating.get("race_number") or "").strip()
        tab_number = str(rating.get("tab_number") or "").strip()
        runner_name = normalise_text(rating.get("runner_name"))

        if runner_id:
            by_runner_id[runner_id] = rating

        if race_id and tab_number:
            by_race_tab[f"{race_id}|{tab_number}"] = rating

        if race_number and tab_number:
            by_race_number_tab[f"{race_number}|{tab_number}"] = rating

        if race_number and runner_name:
            by_name[f"{race_number}|{runner_name}"] = rating

    return {
        "by_runner_id": by_runner_id,
        "by_race_tab": by_race_tab,
        "by_race_number_tab": by_race_number_tab,
        "by_name": by_name,
    }


def apply_rating_to_runner(
    runner: Dict[str, Any],
    rating: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not rating:
        return {
            **runner,
            "ratings_matched": False,
            "pf_ai_score": None,
            "pf_ai_price": None,
            "pf_ai_rank": None,
        }

    return {
        **runner,
        "ratings_matched": True,
        "rating_is_reliable": rating.get("is_reliable"),
        "pf_ai_score": rating.get("pf_ai_score"),
        "pf_ai_price": rating.get("pf_ai_price"),
        "pf_ai_rank": rating.get("pf_ai_rank"),
        "run_style": rating.get("run_style"),
        "predicted_settle_position": rating.get("predicted_settle_position"),
        "average_historical_settle_position": rating.get("average_historical_settle_position"),
        "time_rank": rating.get("time_rank"),
        "time_price": rating.get("time_price"),
        "early_time_rank": rating.get("early_time_rank"),
        "early_time_price": rating.get("early_time_price"),
        "last_600_time_rank": rating.get("last_600_time_rank"),
        "last_600_time_price": rating.get("last_600_time_price"),
        "last_400_time_rank": rating.get("last_400_time_rank"),
        "last_400_time_price": rating.get("last_400_time_price"),
        "last_200_time_rank": rating.get("last_200_time_rank"),
        "last_200_time_price": rating.get("last_200_time_price"),
        "class_change": rating.get("class_change"),
        "ratings_raw": rating.get("raw"),
    }


def merge_ratings_into_form_data(
    form_data: Dict[str, Any],
    ratings_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    ratings = (ratings_data or {}).get("ratings") or []
    indexes = build_rating_indexes(ratings)

    matched_count = 0
    total_count = 0
    enriched_races = []

    for race in form_data.get("races") or []:
        enriched_runners = []

        for runner in race.get("runners") or []:
            total_count += 1

            runner_id = str(runner.get("runner_id") or "").strip()
            race_id = str(race.get("race_id") or "").strip()
            race_number = str(race.get("race_number") or "").strip()
            tab_number = str(runner.get("tab_number") or "").strip()
            runner_name = normalise_text(runner.get("horse_name"))

            rating = None

            if runner_id:
                rating = indexes["by_runner_id"].get(runner_id)

            if not rating and race_id and tab_number:
                rating = indexes["by_race_tab"].get(f"{race_id}|{tab_number}")

            if not rating and race_number and tab_number:
                rating = indexes["by_race_number_tab"].get(f"{race_number}|{tab_number}")

            if not rating and race_number and runner_name:
                rating = indexes["by_name"].get(f"{race_number}|{runner_name}")

            if rating:
                matched_count += 1

            enriched_runners.append(
                apply_rating_to_runner(
                    runner=runner,
                    rating=rating,
                )
            )

        enriched_races.append(
            {
                **race,
                "runners": enriched_runners,
            }
        )

    return {
        **form_data,
        "races": enriched_races,
        "ratings_merge": {
            "ratings_success": bool((ratings_data or {}).get("success")),
            "ratings_source": (ratings_data or {}).get("source"),
            "ratings_matched_by": (ratings_data or {}).get("matched_by"),
            "ratings_available_count": len(ratings),
            "ratings_runner_count": total_count,
            "ratings_matched_count": matched_count,
            "ratings_unmatched_count": max(total_count - matched_count, 0),
        },
    }


def condition_track_bias(track_condition: str) -> str:
    condition = str(track_condition or "").upper()

    if "HEAVY" in condition or "HVY" in condition:
        return "Wet Track Influence - Heavy"
    if "SOFT" in condition:
        return "Wet Track Influence - Soft"
    if "GOOD" in condition:
        return "Good Track / Neutral"
    if "SYNTHETIC" in condition:
        return "Synthetic Surface"

    return "Neutral"


def predict_from_form_data(
    form_data: Dict[str, Any],
    meeting_id: Optional[int] = None,
    condition_data: Optional[Dict[str, Any]] = None,
    ratings_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    races = form_data.get("races") or []
    ratings_merge = form_data.get("ratings_merge") or {}
    meeting_metadata_merge = form_data.get("meeting_metadata_merge") or {}
    scratchings_merge = form_data.get("scratchings_merge") or {}

    eligible_races = [
        race for race in races
        if not is_barrier_trial_race(race)
    ]

    all_ranked = []

    for race in eligible_races:
        all_ranked.extend(score_race(race))

    all_ranked = sorted(
        all_ranked,
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    if not all_ranked:
        return {
            "success": False,
            "provider": "Punting Form",
            "message": "No eligible non-barrier-trial races available for prediction.",
            "meeting_id": meeting_id,
            "eligible_race_count": 0,
            "model_version": MODEL_VERSION,
            "prediction_type": PREDICTION_TYPE,
            "ratings_merge": ratings_merge,
            "meeting_metadata_merge": meeting_metadata_merge,
            "scratchings_merge": scratchings_merge,
            "scoring_weights": SCORING_WEIGHTS,
            "pf_ai_strategy": PF_AI_STRATEGY,
            "factor_capture": {
                "version": "2.12.0",
                "status": "not_available",
                "runner_count": 0,
                "runners": [],
            },
        }

    top_4_win = all_ranked[:4]
    top_4_each_way = all_ranked[4:8] if len(all_ranked) >= 8 else all_ranked[:4]
    excluded_for_roughies = top_4_win + top_4_each_way
    top_4_roughies = select_roughies(all_ranked, excluded_for_roughies)

    multis = build_multis(eligible_races)

    confidence_average = round(
        sum(safe_float(runner.get("confidence"), 0) for runner in top_4_win)
        / max(len(top_4_win), 1),
        1,
    )

    condition_data = condition_data or {}
    track_condition_display = (
        condition_data.get("track_condition_display")
        or "Not currently supplied."
    )
    weather_display = condition_data.get("weather") or "Not currently supplied."

    return {
        "success": True,
        "provider": "Punting Form",
        "source": "Punting Form API",
        "prediction_type": PREDICTION_TYPE,
        "model_version": MODEL_VERSION,
        "meeting_id": meeting_id,
        "meeting_date": (
            condition_data.get("meeting_date")
            or meeting_metadata_merge.get("meeting_date")
        ),
        "track": (
            condition_data.get("track")
            or (meeting_metadata_merge.get("track") or {}).get("name")
        ),
        "track_condition": track_condition_display,
        "weather": weather_display,
        "track_condition_details": condition_data,
        "ratings_merge": ratings_merge,
        "meeting_metadata_merge": meeting_metadata_merge,
        "scratchings_merge": scratchings_merge,
        "scoring_weights": SCORING_WEIGHTS,
        "pf_ai_strategy": PF_AI_STRATEGY,
        "eligible_race_count": len(eligible_races),
        "excluded_barrier_trial_count": len(races) - len(eligible_races),
        "runner_count": len(all_ranked),
        "prediction_summary": {
            "meeting_strength": "Punting Form API Assessment",
            "confidence_score": confidence_average,
            "track_bias": condition_track_bias(track_condition_display),
            "condition_source": condition_data.get("matched_by") or "not_supplied",
            "ratings_source": ratings_merge.get("ratings_source") or "not_supplied",
            "ratings_matched_count": ratings_merge.get("ratings_matched_count"),
            "ratings_unmatched_count": ratings_merge.get("ratings_unmatched_count"),
            "race_name_source": meeting_metadata_merge.get("meeting_source") or "not_supplied",
            "race_name_matched_count": meeting_metadata_merge.get("race_name_matched_count"),
            "race_name_unmatched_count": meeting_metadata_merge.get("race_name_unmatched_count"),
            "scratchings_source": scratchings_merge.get("scratchings_source") or "not_supplied",
            "scratchings_available_count": scratchings_merge.get("scratchings_available_count"),
            "scratchings_excluded_count": scratchings_merge.get("scratchings_excluded_count"),
            "scratching_impact": (
                "High"
                if safe_int(scratchings_merge.get("scratchings_excluded_count"), 0) >= 5
                else "Moderate"
                if safe_int(scratchings_merge.get("scratchings_excluded_count"), 0) >= 2
                else "Low"
            ),
            "scoring_model": (
                "RRT Punting Form Model v1.3: last10 form, win/place percentage, track record, "
                "distance record, track-distance record, track-condition record, trainer A2E, "
                "jockey A2E, trainer/jockey A2E, barrier, weight and market price. "
                "PF AI ratings are merged for comparison only and are not yet used in scoring. "
                "Roughies require price >= 10, price > 0 and market rank >= 6. "
                "Scratchings are merged from Punting Form Updates Scratchings and excluded before scoring."
            ),
        },
        "predictions": {
            "top_4_win_bets": [
                format_runner(runner)
                for runner in top_4_win
            ],
            "top_4_each_way_bets": [
                format_runner(runner)
                for runner in top_4_each_way
            ],
            "top_4_roughies": [
                format_runner(runner, category="roughie")
                for runner in top_4_roughies
            ],
            **multis,
        },
    }


def predict_meeting_from_punting_form(
    meeting_id: int,
    race_number: int = 0,
    runs: int = 10,
) -> Dict[str, Any]:
    raw_response = get_meeting_form(
        meeting_id=meeting_id,
        race_number=race_number,
        runs=runs,
    )

    form_data = simplify_form_response(raw_response)

    meeting_metadata = fetch_meeting_metadata(
        meeting_id=meeting_id,
    )

    form_data = merge_meeting_metadata_into_form_data(
        form_data=form_data,
        meeting_metadata=meeting_metadata,
    )

    scratchings_data = fetch_scratchings_for_meeting(
        meeting_id=meeting_id,
    )

    form_data = merge_scratchings_into_form_data(
        form_data=form_data,
        scratchings_data=scratchings_data,
    )

    condition_data = fetch_condition_for_meeting(
        meeting_id=meeting_id,
        form_data=form_data,
    )

    ratings_data = fetch_ratings_for_meeting(
        meeting_id=meeting_id,
    )

    form_data = merge_ratings_into_form_data(
        form_data=form_data,
        ratings_data=ratings_data,
    )

    return predict_from_form_data(
        form_data=form_data,
        meeting_id=meeting_id,
        condition_data=condition_data,
        ratings_data=ratings_data,
    )


if __name__ == "__main__":
    result = predict_meeting_from_punting_form(
        meeting_id=240369,
        race_number=0,
        runs=10,
    )

    print("Success:", result.get("success"))
    print("Prediction Type:", result.get("prediction_type"))
    print("Model Version:", result.get("model_version"))
    print("Eligible Races:", result.get("eligible_race_count"))
    print("Excluded Barrier Trials:", result.get("excluded_barrier_trial_count"))
    print("Runner Count:", result.get("runner_count"))
    print("Ratings Merge:", result.get("ratings_merge"))
    print("Scratchings Merge:", result.get("scratchings_merge"))

    predictions = result.get("predictions", {})

    print("\nTOP 4 WIN")
    for runner in predictions.get("top_4_win_bets", []):
        print(
            runner.get("race_title"),
            "|",
            runner.get("number"),
            runner.get("runner"),
            "| Score:",
            runner.get("score"),
            "| Confidence:",
            runner.get("confidence"),
            "| PF AI:",
            runner.get("pf_ai"),
        )

    print("\nTOP 4 EACH WAY")
    for runner in predictions.get("top_4_each_way_bets", []):
        print(
            runner.get("race_title"),
            "|",
            runner.get("number"),
            runner.get("runner"),
            "| Score:",
            runner.get("score"),
            "| Confidence:",
            runner.get("confidence"),
            "| PF AI:",
            runner.get("pf_ai"),
        )

    print("\nTOP 4 ROUGHIES")
    for runner in predictions.get("top_4_roughies", []):
        print(
            runner.get("race_title"),
            "|",
            runner.get("number"),
            runner.get("runner"),
            "| Price:",
            runner.get("price"),
            "| Market Rank:",
            runner.get("market_rank"),
            "| Score:",
            runner.get("score"),
            "| Confidence:",
            runner.get("confidence"),
            "| PF AI:",
            runner.get("pf_ai"),
        )

    print("\nDOUBLE")
    for leg in predictions.get("best_double", {}).get("legs", []):
        selections = ", ".join(
            f"{runner.get('number')} {runner.get('runner')}"
            for runner in leg.get("selections", [])
        )
        print(leg.get("race_title"), "|", selections)

    print("\nQUADDIE")
    for leg in predictions.get("best_quaddie", {}).get("legs", []):
        selections = ", ".join(
            f"{runner.get('number')} {runner.get('runner')}"
            for runner in leg.get("selections", [])
        )
        print(leg.get("race_title"), "|", selections)
