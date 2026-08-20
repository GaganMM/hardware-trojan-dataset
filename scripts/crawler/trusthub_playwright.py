from playwright.sync_api import sync_playwright
from pathlib import Path
import time

BASE_URL = "https://trust-hub.org/#/benchmarks/chip-level-trojan"
DOWNLOAD_DIR = Path("downloads/trusthub")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def main():

    import requests

    print("[*] Starting Playwright...")

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context(
            accept_downloads=True
        )

        page = context.new_page()

        print("[*] Opening TrustHub...")

        page.goto(
            BASE_URL,
            wait_until="networkidle",
            timeout=120000,
        )

        page.wait_for_timeout(8000)

        print(page.title())
        print(page.url)

        page.screenshot(
            path="trusthub.png",
            full_page=True,
        )

        print("[*] Screenshot saved")

        page.wait_for_selector("body")

        page.wait_for_timeout(5000)

        anchors = page.locator("a").all()

        print(f"[*] Found {len(anchors)} anchor tags")

        download_links = []

        for anchor in anchors:

            href = anchor.get_attribute("href")

            if not href:
                continue

            href = href.strip()

            if (
                "download" in href.lower()
                or "resource" in href.lower()
                or "benchmark" in href.lower()
            ):

                if href.startswith("/"):

                    href = "https://www.trust-hub.org" + href

                elif not href.startswith("http"):

                    href = "https://www.trust-hub.org/" + href.lstrip("/")

                download_links.append(href)

        download_links = sorted(
            set(download_links)
        )

        print(
            f"[*] Candidate downloads: {len(download_links)}"
        )

        for link in download_links:
            print(link)

        print()
        print("[*] Downloading benchmarks...")

        session = requests.Session()

        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0"
            }
        )

        for link in download_links:

            if link.lower().endswith(".pdf"):
                continue

            filename = link.split("/")[-1]

            output = DOWNLOAD_DIR / filename

            if output.exists():

                print(f"[SKIP] {filename}")

                continue

            print(f"[GET ] {filename}")

            try:

                response = session.get(
                    link,
                    stream=True,
                    timeout=300,
                    verify=False,
                )

                response.raise_for_status()

                with open(output, "wb") as f:

                    for chunk in response.iter_content(
                        1024 * 1024
                    ):

                        if chunk:

                            f.write(chunk)

            except Exception as e:

                print(
                    f"[FAIL] {filename} : {e}"
                )

        print()
        print("[*] Download Complete")

        browser.close()

if __name__ == "__main__":
    main()