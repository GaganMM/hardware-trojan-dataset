from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.trust-hub.org/"
START = "https://www.trust-hub.org/#/benchmarks"

DOWNLOAD_RE = re.compile(r"/resources/\d+/download/", re.IGNORECASE)


def collect_download_links(url: str):

    response = requests.get(
        url,
        timeout=60,
        verify=False,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    links = set()

    for tag in soup.find_all("a", href=True):

        href = urljoin(BASE, tag["href"])

        if DOWNLOAD_RE.search(href):

            links.add(href)

    return sorted(links)


def download(url: str, out_dir: Path):

    filename = url.split("/")[-1]

    out = out_dir / filename

    if out.exists():
        print(f"[SKIP] {filename}")
        return

    print(f"[GET ] {filename}")

    r = requests.get(
        url,
        stream=True,
        timeout=120,
        verify=False,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    r.raise_for_status()    

    with open(out, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)


def main():

    out = Path("downloads/trusthub")
    out.mkdir(parents=True, exist_ok=True)

    links = collect_download_links(START)

    print(f"Found {len(links)} files")

    for link in links:
        download(link, out)


if __name__ == "__main__":
    main()