import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DATABASE_PATH = Path("race_database.json")


def load_race_database() -> Dict[str, Any]:
    if not DATABASE_PATH.exists():
        return {
            "success": False,
            "message": "race_database.json not found. Run race_data_importer.py first.",
            "meetings": [],
        }

    with open(DATABASE_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    data["success"] = True
    return data


def normalise_key(value: Any) -> str:
    return str(value or "").strip().lower()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(value, maximum))


def get_runner_key(runner: Dict[str, Any]) -> str:
    return "|".join([
        str(runner.get("race_number") or ""),
        str(runner.get("horse_number") or runner.get("number") or ""),
        normalise_key(runner.get("horse_name") or runner.get("runner")),
    ])


def get_database_countries() -> List[str]:
    data = load_race_database()

    return sorted({
        meeting.get("country")
        for meeting in data.get("meetings", [])
        if meeting.get("country")
    })


def get_database_race_types(country: Optional[str] = None) -> List[str]:
    data = load_race_database()
    race_types = set()

    for meeting in data.get("meetings", []):
        if country and normalise_key(meeting.get("country")) != normalise_key(country):
            continue

        if meeting.get("race_type"):
            race_types.add(meeting.get("race_type"))

    return sorted(race_types)


def get_database_meetings(
    country: Optional[str] = None,
    race_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    data = load_race_database()
    meetings = []

    for meeting in data.get("meetings", []):
        if country and normalise_key(meeting.get("country")) != normalise_key(country):
            continue

        if race_type and normalise_key(meeting.get("race_type")) != normalise_key(race_type):
            continue

        meetings.append({
            "meeting_id": meeting.get("meeting_id"),
            "country": meeting.get("country"),
            "race_type": meeting.get("race_type"),
            "track": meeting.get("meeting_track"),
            "meeting_name": meeting.get("meeting_track"),
            "city": meeting.get("meeting_track"),
            "date": meeting.get("race_date"),
            "timezone": "Australia/Sydney",
            "race_count": meeting.get("race_count"),
            "runner_count": meeting.get("runner_count"),
            "source": "RRT Stored Race Database",
            "isActiveMeeting": True,
        })

    return sorted(
        meetings,
        key=lambda item: (
            item.get("country") or "",
            item.get("race_type") or "",
            item.get("track") or "",
        ),
    )


def find_meeting_by_track(track: str) -> Optional[Dict[str, Any]]:
    data = load_race_database()
    selected = normalise_key(track)

    for meeting in data.get("meetings", []):
        meeting_track = normalise_key(meeting.get("meeting_track"))
        meeting_id = normalise_key(meeting.get("meeting_id"))

        if selected == meeting_track or selected == meeting_id:
            return meeting

        if selected and selected in meeting_track:
            return meeting

    return None


def score_recent_form(form: Any) -> float:
    form_text = str(form or "").upper().replace("X", "").replace("-", "")

    if not form_text:
        return 50.0

    recent = form_text[-5:]
    score = 50.0

    for index, result in enumerate(recent):
        recency_multiplier = 1 + (index * 0.08)

        if result == "1":
            score += 8 * recency_multiplier
        elif result == "2":
            score += 6 * recency_multiplier
        elif result == "3":
            score += 4 * recency_multiplier
        elif result in ["4", "5"]:
            score += 2 * recency_multiplier
        elif result in ["6", "7"]:
            score -= 1 * recency_multiplier
        elif result in ["8", "9", "0"]:
            score -= 2 * recency_multiplier

    return clamp(score)


def score_market_rank(market_rank: Any) -> float:
    rank = safe_int(market_rank, 99)

    if rank <= 1:
        return 100
    if rank == 2:
        return 92
    if rank == 3:
        return 84
    if rank <= 5:
        return 72
    if rank <= 8:
        return 58
    if rank <= 12:
        return 44

    return 30


def score_roughie_value(market_rank: Any, final_score: float) -> float:
    rank = safe_int(market_rank, 99)

    if rank < 7:
        return 0

    value_bonus = 0

    if 7 <= rank <= 9:
        value_bonus = 10
    elif 10 <= rank <= 12:
        value_bonus = 15
    elif rank >= 13:
        value_bonus = 18

    return round(final_score + value_bonus, 1)


def score_last_start(last_start_finish: Any) -> float:
    finish = safe_int(last_start_finish, 99)

    if finish == 1:
        return 100
    if finish == 2:
        return 88
    if finish == 3:
        return 78
    if finish <= 5:
        return 64
    if finish <= 8:
        return 46

    return 30


def score_barrier(barrier: Any) -> float:
    barrier_number = safe_int(barrier, 0)

    if barrier_number <= 0:
        return 50

    if 2 <= barrier_number <= 7:
        return 85
    if barrier_number in [1, 8, 9]:
        return 72
    if 10 <= barrier_number <= 13:
        return 55

    return 38


def score_weight(weight_kg: Any) -> float:
    weight = safe_float(weight_kg, 57.0)

    if weight <= 53:
        return 85
    if weight <= 55:
        return 78
    if weight <= 57:
        return 68
    if weight <= 59:
        return 58
    if weight <= 61:
        return 46

    return 34


def score_prize_strength(avg_prize_money: Any) -> float:
    prize = safe_float(avg_prize_money, 0)

    if prize >= 200000:
        return 100
    if prize >= 150000:
        return 88
    if prize >= 100000:
        return 76
    if prize >= 60000:
        return 62
    if prize >= 30000:
        return 50

    return 38


def score_trainer(trainer_win_percent: Any, trainer_place_percent: Any = None) -> float:
    win = safe_float(trainer_win_percent, 0)
    place = safe_float(trainer_place_percent, 0)

    if place <= 0:
        place = win * 2.1

    return clamp((win * 2.2) + (place * 0.8))


def score_jockey(jockey_win_percent: Any, jockey_place_percent: Any) -> float:
    win = safe_float(jockey_win_percent, 0)
    place = safe_float(jockey_place_percent, 0)

    return clamp((win * 2.0) + (place * 1.0))


def score_runner(
    runner: Dict[str, Any],
    race: Dict[str, Any],
) -> Dict[str, Any]:
    recent_form_score = score_recent_form(runner.get("recent_form"))
    track_fit_score = safe_float(runner.get("track_condition_suitability"), 50)
    distance_fit_score = safe_float(runner.get("distance_suitability"), 50)
    jockey_score = score_jockey(
        runner.get("jockey_win_percent"),
        runner.get("jockey_place_percent"),
    )
    trainer_score = score_trainer(
        runner.get("trainer_win_percent"),
        runner.get("trainer_place_percent"),
    )
    barrier_score = score_barrier(runner.get("barrier"))
    weight_score = score_weight(runner.get("weight_kg"))
    market_score = score_market_rank(runner.get("market_rank"))
    prize_score = score_prize_strength(runner.get("avg_prize_money"))
    last_start_score = score_last_start(runner.get("last_start_finish"))

    base_score = safe_float(runner.get("rrt_base_score"), 50)

    final_score = (
        recent_form_score * 0.20
        + track_fit_score * 0.18
        + distance_fit_score * 0.16
        + jockey_score * 0.14
        + trainer_score * 0.08
        + barrier_score * 0.06
        + weight_score * 0.06
        + market_score * 0.07
        + prize_score * 0.05
    )

    final_score = (final_score * 0.88) + (base_score * 0.12)

    if last_start_score >= 88:
        final_score += 2.5
    elif last_start_score <= 35:
        final_score -= 2.0

    final_score = round(clamp(final_score), 1)

    roughie_value_score = score_roughie_value(
        runner.get("market_rank"),
        final_score,
    )

    confidence = round(
        clamp(
            (final_score * 0.70)
            + (track_fit_score * 0.10)
            + (distance_fit_score * 0.10)
            + (jockey_score * 0.05)
            + (market_score * 0.05),
            10,
            95,
        ),
        1,
    )

    return {
        **runner,
        "score": final_score,
        "roughie_value_score": roughie_value_score,
        "confidence": confidence,
        "race_number": race.get("race_number"),
        "race_name": race.get("race_name"),
        "race_time": race.get("race_time"),
        "track_condition": race.get("track_condition"),
        "distance_m": race.get("distance_m"),
        "score_breakdown": {
            "recent_form": round(recent_form_score, 1),
            "track_condition_suitability": round(track_fit_score, 1),
            "distance_suitability": round(distance_fit_score, 1),
            "jockey": round(jockey_score, 1),
            "trainer": round(trainer_score, 1),
            "barrier": round(barrier_score, 1),
            "weight": round(weight_score, 1),
            "market_rank": round(market_score, 1),
            "roughie_value": round(roughie_value_score, 1),
            "class_prize_strength": round(prize_score, 1),
            "base_score": round(base_score, 1),
        },
    }


def rank_race(race: Dict[str, Any]) -> List[Dict[str, Any]]:
    runners = race.get("runners", [])

    scored = [
        score_runner(runner, race)
        for runner in runners
        if runner.get("horse_name")
    ]

    return sorted(
        scored,
        key=lambda item: item.get("score", 0),
        reverse=True,
    )


def build_runner_reason(runner: Dict[str, Any], category: str = "standard") -> str:
    reasons = []
    breakdown = runner.get("score_breakdown", {})

    if category == "roughie":
        if safe_int(runner.get("market_rank"), 99) >= 7:
            reasons.append("outside the main market but still rates competitively")

        if safe_float(breakdown.get("roughie_value")) >= 80:
            reasons.append("strong roughie value score")

    if safe_float(breakdown.get("recent_form")) >= 75:
        reasons.append("strong recent form")

    if safe_float(breakdown.get("track_condition_suitability")) >= 80:
        reasons.append("strong track-condition suitability")

    if safe_float(breakdown.get("distance_suitability")) >= 80:
        reasons.append("strong distance suitability")

    if safe_float(breakdown.get("jockey")) >= 70:
        reasons.append("positive jockey win/place profile")

    if safe_float(breakdown.get("trainer")) >= 65:
        reasons.append("positive trainer profile")

    if safe_float(breakdown.get("barrier")) >= 80:
        reasons.append("favourable barrier")

    if category != "roughie" and safe_float(breakdown.get("market_rank")) >= 80:
        reasons.append("near the top of the market ranking")

    if not reasons:
        reasons.append("balanced profile across the RRT scoring model")

    return ", ".join(reasons).capitalize() + "."


def format_prediction_runner(
    runner: Dict[str, Any],
    category: str = "standard",
) -> Dict[str, Any]:
    return {
        "number": runner.get("horse_number"),
        "runner": runner.get("horse_name"),
        "horse_name": runner.get("horse_name"),
        "form": runner.get("recent_form"),
        "trainer": runner.get("trainer"),
        "jockey": runner.get("jockey"),
        "weight": runner.get("weight_kg"),
        "barrier": runner.get("barrier"),
        "market_rank": runner.get("market_rank"),
        "score": runner.get("score"),
        "roughie_value_score": runner.get("roughie_value_score"),
        "confidence": runner.get("confidence"),
        "race_number": runner.get("race_number"),
        "race_name": runner.get("race_name"),
        "race_time": runner.get("race_time"),
        "reason": build_runner_reason(runner, category=category),
        "score_breakdown": runner.get("score_breakdown"),
    }


def build_meeting_multis(races: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked_races = []

    for race in races:
        ranked = rank_race(race)

        if ranked:
            ranked_races.append({
                "race_number": race.get("race_number"),
                "race_name": race.get("race_name"),
                "race_time": race.get("race_time"),
                "selections": [
                    format_prediction_runner(runner)
                    for runner in ranked[:3]
                ],
            })

    return {
        "best_double": {
            "legs": ranked_races[:2],
            "status": "Active" if len(ranked_races) >= 2 else "Awaiting enough races",
        },
        "best_quaddie": {
            "legs": ranked_races[:4],
            "status": "Active" if len(ranked_races) >= 4 else "Awaiting enough races",
        },
    }


def select_roughies(
    all_ranked: List[Dict[str, Any]],
    excluded_runners: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    excluded_keys = {
        get_runner_key(runner)
        for runner in excluded_runners
    }

    roughie_candidates = []

    for runner in all_ranked:
        runner_key = get_runner_key(runner)

        if runner_key in excluded_keys:
            continue

        market_rank = safe_int(runner.get("market_rank"), 99)
        score = safe_float(runner.get("score"), 0)
        roughie_value = safe_float(runner.get("roughie_value_score"), 0)

        if market_rank >= 7 and score >= 55:
            roughie_candidates.append(runner)

    roughie_candidates = sorted(
        roughie_candidates,
        key=lambda item: (
            safe_float(item.get("roughie_value_score"), 0),
            safe_float(item.get("score"), 0),
        ),
        reverse=True,
    )

    return roughie_candidates[:3]


def predict_meeting(track: str) -> Dict[str, Any]:
    meeting = find_meeting_by_track(track)

    if not meeting:
        return {
            "success": False,
            "message": "Meeting not found in stored race database.",
        }

    all_ranked = []

    for race in meeting.get("races", []):
        all_ranked.extend(rank_race(race))

    all_ranked = sorted(
        all_ranked,
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    if not all_ranked:
        return {
            "success": False,
            "message": "No runners available for prediction.",
        }

    top_3_win = all_ranked[:3]
    top_3_each_way = all_ranked[3:6] if len(all_ranked) >= 6 else all_ranked[:3]

    excluded_for_roughies = top_3_win + top_3_each_way
    top_3_roughies = select_roughies(
        all_ranked=all_ranked,
        excluded_runners=excluded_for_roughies,
    )

    if not top_3_roughies:
        fallback_pool = [
            runner for runner in all_ranked
            if get_runner_key(runner) not in {
                get_runner_key(excluded)
                for excluded in excluded_for_roughies
            }
        ]
        top_3_roughies = fallback_pool[-3:]

    first_race = meeting.get("races", [{}])[0]
    multis = build_meeting_multis(meeting.get("races", []))

    confidence_average = round(
        sum(runner.get("confidence", 0) for runner in top_3_win)
        / max(len(top_3_win), 1),
        1,
    )

    return {
        "success": True,
        "provider": "RRT Stored Race Database",
        "prediction_type": "Stored Excel Data Prototype - Weighted Model v2.1",
        "country": meeting.get("country"),
        "race_type": meeting.get("race_type"),
        "track": meeting.get("meeting_track"),
        "meeting_date": meeting.get("race_date"),
        "timezone": "Australia/Sydney",
        "race_number": None,
        "race_name": "Whole Meeting Assessment",
        "race_time": None,
        "track_condition": first_race.get("track_condition"),
        "weather": first_race.get("weather"),
        "race_status": "Stored",
        "runner_count": meeting.get("runner_count"),
        "active_runner_count": meeting.get("runner_count"),
        "prediction_summary": {
            "meeting_strength": "Stored Data Assessment",
            "confidence_score": confidence_average,
            "track_bias": first_race.get("track_condition") or "Not available",
            "scratching_impact": "Not modelled in mock database",
            "runner_enrichment": "Excel import active",
            "scoring_model": (
                "Weighted Model v2.1: recent form 20%, track condition suitability 18%, "
                "distance suitability 16%, jockey win/place 14%, trainer profile 8%, "
                "barrier 6%, weight carried 6%, market rank 7%, class/prize strength 5%, "
                "with a 12% RRT base-score stabiliser. Roughies require market_rank >= 7, "
                "competitive score, and exclusion from Win/Each-Way selections."
            ),
        },
        "predictions": {
            "top_3_win_bets": [
                format_prediction_runner(runner)
                for runner in top_3_win
            ],
            "top_3_each_way_bets": [
                format_prediction_runner(runner)
                for runner in top_3_each_way
            ],
            "top_3_roughies": [
                format_prediction_runner(runner, category="roughie")
                for runner in top_3_roughies
            ],
            **multis,
        },
        "source": {
            "meetings": "Uploaded Excel",
            "runners": "Uploaded Excel",
            "form": "Uploaded Excel",
            "track_condition": "Uploaded Excel",
            "prediction_logic": "RRT Predictor Engine",
        },
    }