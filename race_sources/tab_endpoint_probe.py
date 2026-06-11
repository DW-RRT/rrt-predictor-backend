import requests

URLS = [
    "https://www.tab.com.au/racing",
    "https://api.beta.tab.com.au/v1/tab-info-service/racing/dates/2026-05-11/meetings?jurisdiction=NSW",
    "https://api.beta.tab.com.au/v1/tab-info-service/racing/dates/2026-05-11/meetings?jurisdiction=VIC",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-AU,en;q=0.9",
    "Connection": "close",
}


def probe_url(url):
    print("\n" + "=" * 80)
    print("URL:", url)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=(10, 30),
            allow_redirects=True,
        )

        print("Status:", response.status_code)
        print("Final URL:", response.url)
        print("Content-Type:", response.headers.get("content-type"))
        print("Length:", len(response.text or ""))
        print("Preview:")
        print((response.text or "")[:1000])

    except Exception as error:
        print("ERROR:", repr(error))


if __name__ == "__main__":
    for url in URLS:
        probe_url(url)