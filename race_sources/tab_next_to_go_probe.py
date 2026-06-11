import json
import requests

URL = (
    "https://api.beta.tab.com.au/v1/tab-info-service/"
    "racing/next-to-go/races?includeFixedOdds=true"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Origin": "https://www.tab.com.au",
    "Referer": "https://www.tab.com.au/",
    "Connection": "keep-alive",
}


def main():
    print("Requesting:", URL)

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=(10, 60),
        allow_redirects=True,
    )

    print("Status:", response.status_code)
    print("Content-Type:", response.headers.get("content-type"))
    print("Final URL:", response.url)

    response.raise_for_status()

    data = response.json()

    print("\nTop-level keys:")
    print(list(data.keys())[:20])

    races = (
        data.get("races")
        or data.get("items")
        or data.get("data")
        or []
    )

    print("\nRace count:", len(races))

    if races:
        print("\nFIRST RACE SAMPLE:\n")
        print(json.dumps(races[0], indent=2)[:8000])


if __name__ == "__main__":
    main()