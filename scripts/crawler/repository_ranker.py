from pathlib import Path
import pandas as pd
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "metadata" / "raw_sources.csv"
OUTPUT = ROOT / "metadata" / "ranked_sources.csv"

df = pd.read_csv(INPUT)

today = datetime.utcnow()


def compute_score(row):

    score = 0

    stars = row.get("stars", 0)

    if stars > 500:
        score += 20
    elif stars > 100:
        score += 15
    elif stars > 20:
        score += 10
    elif stars > 5:
        score += 5

    language = str(row.get("language", "")).lower()

    if "verilog" in language:
        score += 20

    desc = str(row.get("description", "")).lower()

    keywords = [
        "trojan",
        "verilog",
        "rtl",
        "hardware",
        "aes",
        "uart",
        "riscv",
        "processor",
        "security",
    ]

    for keyword in keywords:
        if keyword in desc:
            score += 3

    owner = str(row.get("owner", ""))

    if owner and owner[0].isupper():
        score += 5

    updated = str(row.get("updated", ""))

    try:

        date = datetime.fromisoformat(
            updated.replace("Z", "+00:00")
        ).replace(tzinfo=None)

        years = (today - date).days / 365

        if years < 2:
            score += 10
        elif years < 4:
            score += 5

    except Exception:
        pass

    return score


df["score"] = df.apply(compute_score, axis=1)

df = df.sort_values(
    "score",
    ascending=False
)

df.to_csv(
    OUTPUT,
    index=False
)

print("=" * 60)
print("Ranking Complete")
print("=" * 60)

print(df[
    [
        "source_name",
        "owner",
        "score",
        "stars",
        "language",
    ]
].head(25))

print()

print(f"Saved to {OUTPUT}")