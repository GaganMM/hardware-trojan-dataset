import requests
import time

from config import BASE_URL, HEADERS


def github_search(query, per_page=50):

    url = (
        f"{BASE_URL}/search/repositories"
        f"?q={query}"
        f"&sort=stars"
        f"&order=desc"
        f"&per_page={per_page}"
    )

    while True:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code == 403:

            print("Rate limited...waiting.")

            time.sleep(60)

            continue

        response.raise_for_status()

        return response.json()["items"]