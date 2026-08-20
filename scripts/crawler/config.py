from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent.parent

print("ROOT =", ROOT)

load_dotenv(ROOT / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

print("TOKEN =", GITHUB_TOKEN[:20] + "..." if GITHUB_TOKEN else None)

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

BASE_URL = "https://api.github.com"