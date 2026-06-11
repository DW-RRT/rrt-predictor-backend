import re
import requests
from urllib.parse import urljoin

URL = "https://www.tab.com.au/racing-betting"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}


def main():
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    html = response.text

    print("Status:", response.status_code)
    print("Final URL:", response.url)
    print("HTML length:", len(html))

    print("\nScript files:")
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
    for src in scripts:
        print(urljoin(response.url, src))

    print("\nAPI-like references:")
    patterns = [
        r'https?://[^"\']+',
        r'/v1/[^"\']+',
        r'/api/[^"\']+',
        r'tab-info-service[^"\']+',
        r'racing/dates[^"\']+',
    ]

    found = set()

    for pattern in patterns:
        for match in re.findall(pattern, html, flags=re.I):
            if any(term in match.lower() for term in ["api", "racing", "tab-info", "meetings"]):
                found.add(match[:300])

    for item in sorted(found):
        print(item)


if __name__ == "__main__":
    main()