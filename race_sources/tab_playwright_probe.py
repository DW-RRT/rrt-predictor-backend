import json
from playwright.sync_api import sync_playwright

START_URL = "https://www.tab.com.au/racing-betting"


def print_preview(title, payload, limit=12000):
    print("\n" + "=" * 80)
    print(title)
    print(json.dumps(payload, indent=2)[:limit])


def main():
    captured_dates_payloads = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        context = browser.new_context(
            viewport={"width": 1440, "height": 1200},
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )

        page = context.new_page()

        def handle_response(response):
            url = response.url

            if "api.beta.tab.com.au/v1/tab-info-service/racing/dates?jurisdiction=NSW" not in url:
                return

            print("DATES RESPONSE:", response.status, url)

            try:
                payload = response.json()
                captured_dates_payloads.append(payload)
                print("DATES JSON captured")
            except Exception as error:
                print("DATES JSON failed:", error)

        page.on("response", handle_response)

        print("OPENING:", START_URL)
        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(30000)

        print("\nCaptured date payloads:", len(captured_dates_payloads))

        if not captured_dates_payloads:
            print("No date payloads captured.")
            browser.close()
            return

        dates_payload = captured_dates_payloads[0]
        print_preview("DATES PAYLOAD", dates_payload)

        meeting_links = []

        for item in dates_payload.get("dates", []):
            meeting_date = item.get("meetingDate")
            meetings_url = item.get("_links", {}).get("meetings")

            if meeting_date and meetings_url and "futures" not in meetings_url:
                meeting_links.append({
                    "date": meeting_date,
                    "url": meetings_url,
                })

        print("\nMeeting links:")
        for item in meeting_links:
            print(item["date"], item["url"])

        if not meeting_links:
            print("No meeting links found.")
            browser.close()
            return

        target = meeting_links[0]

        print("\nFETCHING MEETINGS FROM INSIDE TAB PAGE:")
        print(target["url"])

        meetings_result = page.evaluate(
            """async ({ url }) => {
                const response = await fetch(url, {
                    method: "GET",
                    credentials: "include",
                    headers: {
                        "accept": "application/json, text/plain, */*"
                    }
                });

                const text = await response.text();

                return {
                    ok: response.ok,
                    status: response.status,
                    contentType: response.headers.get("content-type"),
                    text: text
                };
            }""",
            {"url": target["url"]},
        )

        print("\nMEETINGS FETCH STATUS:", meetings_result.get("status"))
        print("MEETINGS CONTENT TYPE:", meetings_result.get("contentType"))

        text = meetings_result.get("text") or ""

        try:
            meetings_payload = json.loads(text)
            print_preview("MEETINGS PAYLOAD", meetings_payload)
        except Exception:
            print("MEETINGS TEXT PREVIEW:")
            print(text[:8000])

        browser.close()


if __name__ == "__main__":
    main()