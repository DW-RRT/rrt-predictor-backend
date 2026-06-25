import random


SCRATCHED_VALUES = [
    "scratched",
    "scratch",
    "late scratching",
    "late scratched",
    "withdrawn",
    "withdrawal",
    "out",
]


def safe_text(value):
    return str(value or "").strip()


def is_scratched_runner(runner):
    if runner.get("scratched") is True:
        return True

    fields = [
        runner.get("scratched"),
        runner.get("status"),
        runner.get("runner_status"),
        runner.get("comment"),
    ]

    combined = " ".join(safe_text(value).lower() for value in fields)

    return any(value in combined for value in SCRATCHED_VALUES)


def score_runner(runner):
    score = 50

    form = runner.get("form")

    if form:
        recent = str(form)[-5:]

        for char in recent:
            if char == "1":
                score += 12
            elif char == "2":
                score += 8
            elif char == "3":
                score += 5
            elif char == "4":
                score += 2
            elif char in ["8", "9", "0"]:
                score -= 3

    weight = runner.get("weight")

    if weight:
        try:
            numeric_weight = float(
                str(weight).lower().replace("kg", "").strip()
            )

            if numeric_weight <= 55:
                score += 5
            elif numeric_weight >= 60:
                score -= 4
        except Exception:
            pass

    trainer = str(runner.get("trainer", "")).lower()

    strong_trainers = [
        "waterhouse",
        "maher",
        "snowden",
        "freedman",
        "williams",
        "waller",
        "cummings",
        "hayes",
        "eustace",
    ]

    for name in strong_trainers:
        if name in trainer:
            score += 6
            break

    score += random.randint(-2, 2)

    return max(1, min(99, round(score, 1)))


def confidence_label(score):
    if score >= 80:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def runner_name(runner):
    return (
        runner.get("horse_name")
        or runner.get("greyhound_name")
        or runner.get("runner_name")
        or runner.get("name")
        or runner.get("runner")
        or "Unknown Runner"
    )


def race_name(race, index):
    return (
        race.get("race_header")
        or race.get("race_name")
        or race.get("name")
        or race.get("race")
        or f"Race {index + 1}"
    )


def race_number_value(race, fallback_index):
    try:
        return int(race.get("race_number"))
    except Exception:
        return fallback_index + 1


def race_runners(race):
    runners = (
        race.get("runners")
        or race.get("horses")
        or race.get("greyhounds")
        or race.get("field")
        or []
    )

    return runners if isinstance(runners, list) else []


def selection_line(index, race, runner):
    score = runner.get("score", 0)

    return (
        f"{index}. {race} | {runner_name(runner)} | "
        f"Confidence: {score}% ({confidence_label(score)}) | "
        f"Trainer: {runner.get('trainer') or 'N/A'} | "
        f"Jockey/Driver: {runner.get('jockey') or runner.get('driver') or 'N/A'} | "
        f"Weight: {runner.get('weight') or 'N/A'} | "
        f"Form: {runner.get('form') or 'N/A'}"
    )


def leg_line(index, race, runner):
    score = runner.get("score", 0)

    return (
        f"Leg {index}: {race} | {runner_name(runner)} | "
        f"Confidence: {score}% ({confidence_label(score)})"
    )


def section(title, lines):
    return {
        "title": title,
        "body": "\n".join(lines) if lines else "Not available",
    }


def generate_whole_meeting_predictions(races):
    scored_races = []
    scratched_runner_count = 0

    for race_index, race in enumerate(races or []):
        current_race = race_name(race, race_index)
        current_race_number = race_number_value(race, race_index)

        scored = []

        for runner in race_runners(race):
            if is_scratched_runner(runner):
                scratched_runner_count += 1
                continue

            score = score_runner(runner)

            scored.append({
                "horse_name": runner_name(runner),
                "trainer": runner.get("trainer"),
                "jockey": runner.get("jockey"),
                "driver": runner.get("driver"),
                "weight": runner.get("weight"),
                "form": runner.get("form"),
                "score": score,
            })

        scored.sort(key=lambda item: item["score"], reverse=True)

        if scored:
            scored_races.append({
                "race": current_race,
                "race_number": current_race_number,
                "top_runners": scored[:4],
                "best_runner": scored[0],
            })

    if not scored_races:
        return {
            "sections": [
                section("TOP 3 BEST WIN BETS", []),
                section("TOP 3 EACH-WAY BETS", []),
                section("TOP 3 BEST ROUGHIE BETS", []),
                section("BEST DOUBLE BET", []),
                section("BEST QUADRELLA BET", []),
                section("TRACK CONDITION", ["Not available from current source"]),
                section("WEATHER", ["Not available from current source"]),
            ],
            "summary": "No valid runners were available for this meeting.",
            "scratched_runner_count": scratched_runner_count,
        }

    win_candidates = [
        {
            "race": race["race"],
            "race_number": race["race_number"],
            "runner": race["best_runner"],
        }
        for race in scored_races
    ]

    win_candidates_by_score = sorted(
        win_candidates,
        key=lambda item: item["runner"]["score"],
        reverse=True,
    )

    win_candidates_by_race_order = sorted(
        win_candidates,
        key=lambda item: item["race_number"],
    )

    each_way_candidates = []
    roughie_candidates = []

    for race in scored_races:
        for runner in race["top_runners"][1:3]:
            each_way_candidates.append({
                "race": race["race"],
                "race_number": race["race_number"],
                "runner": runner,
            })

        for runner in race["top_runners"][2:4]:
            roughie_candidates.append({
                "race": race["race"],
                "race_number": race["race_number"],
                "runner": runner,
            })

    each_way_candidates.sort(
        key=lambda item: item["runner"]["score"],
        reverse=True,
    )

    roughie_candidates.sort(
        key=lambda item: item["runner"]["score"],
        reverse=True,
    )

    win_lines = [
        selection_line(index + 1, item["race"], item["runner"])
        for index, item in enumerate(win_candidates_by_score[:3])
    ]

    each_way_lines = [
        selection_line(index + 1, item["race"], item["runner"])
        for index, item in enumerate(each_way_candidates[:3])
    ]

    roughie_lines = [
        selection_line(index + 1, item["race"], item["runner"])
        for index, item in enumerate(roughie_candidates[:3])
    ]

    double_lines = [
        leg_line(index + 1, item["race"], item["runner"])
        for index, item in enumerate(win_candidates_by_race_order[:2])
    ]

    quadrella_lines = [
        leg_line(index + 1, item["race"], item["runner"])
        for index, item in enumerate(win_candidates_by_race_order[:4])
    ]

    return {
        "sections": [
            section("TOP 3 BEST WIN BETS", win_lines),
            section("TOP 3 EACH-WAY BETS", each_way_lines),
            section("TOP 3 BEST ROUGHIE BETS", roughie_lines),
            section("BEST DOUBLE BET", double_lines),
            section("BEST QUADRELLA BET", quadrella_lines),
            section("TRACK CONDITION", ["Not available from current source"]),
            section("WEATHER", ["Not available from current source"]),
        ],
        "summary": "Whole-meeting prediction generated.",
        "scratched_runner_count": scratched_runner_count,
    }


def generate_predictions_from_races(races):
    return generate_whole_meeting_predictions(races)