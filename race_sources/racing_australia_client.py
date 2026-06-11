import re
import requests

from bs4 import BeautifulSoup
from datetime import datetime, UTC
from urllib.parse import urljoin, unquote, urlparse, parse_qs


BASE_URL = "https://www.racingaustralia.horse"

STATE_URLS = {
    "NSW": f"{BASE_URL}/FreeFields/Calendar.aspx?State=NSW",
    "VIC": f"{BASE_URL}/FreeFields/Calendar.aspx?State=VIC",
    "QLD": f"{BASE_URL}/FreeFields/Calendar.aspx?State=QLD",
    "WA": f"{BASE_URL}/FreeFields/Calendar.aspx?State=WA",
    "SA": f"{BASE_URL}/FreeFields/Calendar.aspx?State=SA",
    "TAS": f"{BASE_URL}/FreeFields/Calendar.aspx?State=TAS",
}

STATE_TIMEZONES = {
    "NSW": "Australia/Sydney",
    "VIC": "Australia/Melbourne",
    "QLD": "Australia/Brisbane",
    "WA": "Australia/Perth",
    "SA": "Australia/Adelaide",
    "TAS": "Australia/Hobart",
    "ACT": "Australia/Sydney",
    "NT": "Australia/Darwin",
}


# ---------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------

def clean_text(value):
    return " ".join(
        str(value or "").replace("\xa0", " ").split()
    ).strip()


def clean_meeting_name(text, href):
    text = (text or "").strip()

    if re.fullmatch(r"\d{4}", text):
        text = ""

    if not text:
        match = re.search(
            r"Key=\d{4}\w+\d{2}%2C[A-Z]+%2C([^&]+)",
            href,
        )

        if match:
            text = match.group(1)
            text = text.replace("%20", " ")

            if "," in text:
                text = text.split(",")[0]

    return text.strip()


def is_valid_meeting(text):
    if not text:
        return False

    lowered = text.lower()

    if "trial" in lowered:
        return False

    if "picnic" in lowered:
        return False

    if "%2c" in lowered:
        return False

    if len(text) < 3:
        return False

    return True


def extract_state_from_url(url):
    try:
        decoded = unquote(url)
        match = re.search(r"Key=\d{4}[A-Za-z]{3}\d{2},([A-Z]+),", decoded)

        if match:
            return match.group(1).strip()
    except Exception:
        pass

    return None


def extract_meeting_date_from_url(url):
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        key_value = query.get("Key", [None])[0]

        if not key_value:
            return None

        decoded = unquote(key_value)
        date_part = decoded.split(",")[0]

        return datetime.strptime(date_part, "%Y%b%d").date()

    except Exception:
        return None


# ---------------------------------------------------------------------
# Meeting list extraction
# ---------------------------------------------------------------------

def extract_meetings_from_state(state_code, url):
    meetings = []

    response = requests.get(
        url,
        timeout=15,
        headers={
            "User-Agent": "Mozilla/5.0 RRT Predictor",
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    seen = set()

    for link in soup.find_all("a"):
        href = link.get("href")

        if not href:
            continue

        href_lower = href.lower()

        if "form.aspx" not in href_lower:
            continue

        if "calendar" in href_lower:
            continue

        meeting_name = clean_meeting_name(
            link.get_text(strip=True),
            href,
        )

        if not is_valid_meeting(meeting_name):
            continue

        full_url = urljoin(BASE_URL, href)

        key = f"{meeting_name}|{full_url}"

        if key in seen:
            continue

        seen.add(key)

        meetings.append({
            "state": state_code,
            "meeting_name": meeting_name,
            "url": full_url,
            "timezone": STATE_TIMEZONES.get(state_code, "Australia/Sydney"),
        })

    return meetings


def fetch_racing_australia_meetings():
    try:
        all_meetings = []

        for state_code, url in STATE_URLS.items():
            try:
                state_meetings = extract_meetings_from_state(
                    state_code,
                    url,
                )

                all_meetings.extend(state_meetings)

            except Exception as state_error:
                print(
                    f"Failed state {state_code}: "
                    f"{state_error}",
                )

        all_meetings.sort(
            key=lambda x: (
                x["state"],
                x["meeting_name"],
            ),
        )

        return {
            "provider": "Racing Australia",
            "last_updated": datetime.now(UTC).isoformat(),
            "meeting_count": len(all_meetings),
            "meetings": all_meetings,
        }

    except Exception as error:
        return {
            "provider": "Racing Australia",
            "error": str(error),
            "meetings": [],
        }


# ---------------------------------------------------------------------
# Text classification helpers
# ---------------------------------------------------------------------

def looks_like_form(value):
    if not value:
        return False

    value = clean_text(value).lower()

    if len(value) > 14:
        return False

    return bool(
        re.fullmatch(r"[0-9x]+", value)
        or re.fullmatch(r"[0-9x]+e", value)
    )


def looks_like_weight(value):
    if not value:
        return False

    value = clean_text(value).lower()

    return bool(
        re.fullmatch(r"\d{2,3}(\.\d)?kg", value)
    )


def looks_like_rating(value):
    if not value:
        return False

    value = clean_text(value)

    # Examples wrongly parsed before: 76.5, 74.5, 71.5
    return bool(
        re.fullmatch(r"\d{1,3}(\.\d)?", value)
    )


def looks_like_runner_number(value):
    if not value:
        return False

    value = clean_text(value)

    return bool(re.fullmatch(r"\d{1,2}", value))


def looks_like_jockey_name(value):
    if not value:
        return False

    value = clean_text(value)

    if len(value) < 3:
        return False

    if value.upper() in [
        "SCRATCHED",
        "TRUE WEIGHT :",
        "NO APPRENTICE",
        "NO RIDER",
    ]:
        return False

    if looks_like_form(value):
        return False

    if looks_like_weight(value):
        return False

    if looks_like_rating(value):
        return False

    if looks_like_runner_number(value):
        return False

    # Jockey names are usually mixed case. Allow titles like Ms.
    if re.search(r"[a-z]", value) and re.search(r"[A-Z]", value):
        return True

    return False


def looks_like_trainer_name(value):
    if not value:
        return False

    value = clean_text(value)

    if len(value) < 3:
        return False

    if value.upper() in [
        "SCRATCHED",
        "TRUE WEIGHT :",
    ]:
        return False

    if looks_like_form(value):
        return False

    if looks_like_weight(value):
        return False

    if looks_like_rating(value):
        return False

    if looks_like_runner_number(value):
        return False

    # Trainers are usually mixed case and may include "&".
    if re.search(r"[a-z]", value) and re.search(r"[A-Z]", value):
        return True

    return False


def looks_like_horse_name(value):
    if not value:
        return False

    value = clean_text(value)

    if len(value) < 3:
        return False

    banned = [
        "Horse",
        "Weight",
        "Penalty",
        "Hcp Rating",
        "Probable Weight",
        "Last 10",
        "Track Name:",
        "Track Type:",
        "Field Limit:",
        "Times displayed",
        "BOBS",
        "TRUE WEIGHT",
        "SCRATCHED",
        "Jockey",
        "Trainer",
        "Barrier",
        "Apprentice",
        "Claim",
    ]

    for item in banned:
        if item.lower() in value.lower():
            return False

    if looks_like_form(value):
        return False

    if looks_like_weight(value):
        return False

    if looks_like_rating(value):
        return False

    if looks_like_runner_number(value):
        return False

    # Real RA horse names are usually all caps.
    if value.upper() != value:
        return False

    # Must contain at least one letter.
    if not re.search(r"[A-Z]", value):
        return False

    # Reject strings that are mostly punctuation/numbers.
    letters = re.findall(r"[A-Z]", value)
    if len(letters) < 3:
        return False

    return True


def extract_race_number(text):
    match = re.search(r"race\s+(\d+)", text.lower())

    if match:
        return int(match.group(1))

    return None


def parse_time_from_text(text):
    if not text:
        return None

    cleaned = clean_text(text).upper().replace(".", ":")

    patterns = [
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        r"\b([1-9]|1[0-2]):([0-5]\d)\s?(AM|PM)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, cleaned)

        if not match:
            continue

        token = match.group(0).replace(" ", "")

        for fmt in ["%H:%M", "%I:%M%p"]:
            try:
                return datetime.strptime(token, fmt).time()
            except Exception:
                pass

    return None


def extract_race_time_from_context(table, lines):
    context_texts = []

    previous_elements = table.find_all_previous(string=True, limit=20)

    for item in previous_elements:
        text = clean_text(str(item))

        if text:
            context_texts.append(text)

    context_texts.extend(lines[:15])

    combined = " ".join(context_texts)

    return parse_time_from_text(combined)


# ---------------------------------------------------------------------
# Runner parsing
# ---------------------------------------------------------------------

def parse_runner_table_from_lines(lines):
    runners = []
    index = 0

    while index < len(lines):
        current = clean_text(lines[index])

        form = None

        if looks_like_form(current):
            form = current
            index += 1

            if index >= len(lines):
                break

            current = clean_text(lines[index])

        if not looks_like_horse_name(current):
            index += 1
            continue

        horse_name = current
        trainer = None
        jockey = None
        weight = None
        scratched = False

        index += 1

        # Trainer
        if index < len(lines):
            possible_trainer = clean_text(lines[index])

            if possible_trainer.upper() == "SCRATCHED":
                scratched = True
                index += 1
            elif looks_like_trainer_name(possible_trainer):
                trainer = possible_trainer
                index += 1
            else:
                # If the next row is not a trainer, do not force it.
                index += 1

        # Jockey
        if index < len(lines):
            possible_jockey = clean_text(lines[index])

            if possible_jockey.upper() == "SCRATCHED":
                scratched = True
                index += 1
            elif looks_like_jockey_name(possible_jockey):
                jockey = possible_jockey
                index += 1
            else:
                # Do not accept ratings, form strings, or numeric rows as jockeys.
                index += 1

        # Search forward until weight, scratched, or next horse.
        while index < len(lines):
            item = clean_text(lines[index])

            if item.upper() == "SCRATCHED":
                scratched = True
                index += 1
                break

            if looks_like_weight(item):
                weight = item
                index += 1
                break

            if looks_like_horse_name(item) or looks_like_form(item):
                break

            index += 1

        # Final validation before append.
        if not looks_like_horse_name(horse_name):
            continue

        runners.append({
            "horse_name": horse_name,
            "form": form,
            "trainer": trainer,
            "jockey": jockey,
            "weight": weight,
            "scratched": scratched,
        })

    return runners


def is_valid_runner(runner):
    horse_name = clean_text(runner.get("horse_name"))

    if not looks_like_horse_name(horse_name):
        return False

    trainer = runner.get("trainer")
    jockey = runner.get("jockey")
    weight = runner.get("weight")
    form = runner.get("form")

    if trainer and not looks_like_trainer_name(trainer):
        runner["trainer"] = None

    if jockey and not looks_like_jockey_name(jockey):
        runner["jockey"] = None

    if weight and not looks_like_weight(weight):
        runner["weight"] = None

    if form and not looks_like_form(form):
        runner["form"] = None

    return True


# ---------------------------------------------------------------------
# Meeting form extraction
# ---------------------------------------------------------------------

def fetch_racing_australia_meeting(meeting_url):
    try:
        response = requests.get(
            meeting_url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 RRT Predictor",
            },
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        tables = soup.find_all("table")

        races = []
        seen_races = set()

        meeting_state = extract_state_from_url(meeting_url)
        meeting_timezone = STATE_TIMEZONES.get(
            meeting_state or "",
            "Australia/Sydney",
        )
        meeting_date = extract_meeting_date_from_url(meeting_url)

        for table in tables:
            table_text = table.get_text("\n")

            lines = [
                clean_text(line)
                for line in table_text.splitlines()
                if clean_text(line)
            ]

            if not lines:
                continue

            joined = " ".join(lines)

            if "Last 10" not in joined:
                continue

            if "Horse" not in joined:
                continue

            race_number = None
            race_header = None

            previous = table.find_previous(
                string=re.compile(r"Race\s+\d+", re.IGNORECASE)
            )

            if previous:
                race_header = clean_text(str(previous))
                race_number = extract_race_number(race_header)

            if not race_number:
                for line in lines[:10]:
                    race_number = extract_race_number(line)

                    if race_number:
                        race_header = f"Race {race_number}"
                        break

            if not race_number:
                continue

            if race_number in seen_races:
                continue

            seen_races.add(race_number)

            race_time = extract_race_time_from_context(table, lines)

            race_datetime = None

            if meeting_date and race_time:
                race_datetime = datetime.combine(
                    meeting_date,
                    race_time,
                ).isoformat()

            try:
                start_index = lines.index("Last 10")
            except ValueError:
                start_index = 0

            runner_lines = lines[start_index + 1:]

            stop_words = [
                "Sire:",
                "Dam:",
                "View Pedigree Report",
                "Breeder:",
                "Owners:",
                "Colours:",
                "Record:",
                "Prizemoney:",
                "Distance(s) Won:",
                "Firm:",
                "Good:",
                "Soft:",
                "Heavy:",
                "Synthetic:",
            ]

            clean_runner_lines = []

            for line in runner_lines:
                if line in stop_words:
                    break

                clean_runner_lines.append(line)

            runners = parse_runner_table_from_lines(clean_runner_lines)

            cleaned_runners = []

            for runner in runners:
                if is_valid_runner(runner):
                    cleaned_runners.append(runner)

            races.append({
                "race_number": race_number,
                "race_header": race_header or f"Race {race_number}",
                "race_time": race_time.strftime("%H:%M") if race_time else None,
                "start_time": race_time.strftime("%H:%M") if race_time else None,
                "race_datetime": race_datetime,
                "timezone": meeting_timezone,
                "runner_count": len(cleaned_runners),
                "runners": cleaned_runners,
            })

        races.sort(key=lambda x: x["race_number"])

        return {
            "provider": "Racing Australia",
            "meeting_url": meeting_url,
            "state": meeting_state,
            "timezone": meeting_timezone,
            "meeting_date": meeting_date.isoformat() if meeting_date else None,
            "race_count": len(races),
            "races": races,
        }

    except Exception as error:
        return {
            "provider": "Racing Australia",
            "error": str(error),
            "races": [],
        }