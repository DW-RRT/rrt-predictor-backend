import re
import requests

JS_URLS = [
    "https://www.tab.com.au/scripts/configuration.js",
    "https://www.tab.com.au/scripts/wwwTab.47879b33a8c0ea72f9ee.bundle.js",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-AU,en;q=0.9",
}


SEARCH_TERMS = [
    "tab-info-service",
    "racing/dates",
    "meetings",
    "races",
    "jurisdiction",
    "advertisedStart",
    "api.beta",
    "api",
]


def print_matches(label, text):
    print("\n" + "=" * 80)
    print(label)
    print("Length:", len(text))

    for term in SEARCH_TERMS:
        print(f"\n--- Searching: {term} ---")

        found_any = False

        for match in re.finditer(re.escape(term), text, flags=re.I):
            found_any = True
            start = max(match.start() - 300, 0)
            end = min(match.end() + 500, len(text))
            snippet = text[start:end]
            print(snippet.replace("\\n", "\n")[:1200])
            print("-" * 40)
            break

        if not found_any:
            print("No match")

    print("\nURL-like strings:")
    url_matches = sorted(set(re.findall(r'https?://[^"\'`\\)]+', text)))
    for url in url_matches:
        if any(x in url.lower() for x in ["api", "racing", "tab"]):
            print(url[:500])

    print("\nPath-like strings:")
    path_matches = sorted(set(re.findall(r'["\'](/[^"\']*(?:racing|meeting|race|tab-info|api)[^"\']*)["\']', text, flags=re.I)))
    for path in path_matches[:100]:
        print(path[:500])


def main():
    for url in JS_URLS:
        print("\nDownloading:", url)

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=60,
        )

        print("Status:", response.status_code)
        print("Content-Type:", response.headers.get("content-type"))

        response.raise_for_status()

        print_matches(url, response.text)


if __name__ == "__main__":
    main()