from pathlib import Path
from git import Repo, GitCommandError
from tqdm import tqdm
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "metadata" / "ranked_sources.csv"
OUTPUT = ROOT / "metadata" / "downloaded_sources.csv"

DOWNLOAD_DIR = ROOT / "downloads"

DOWNLOAD_DIR.mkdir(exist_ok=True)

df = pd.read_csv(INPUT)

# Download only the best repositories first
TOP_N = 100
df = df.head(TOP_N)

downloaded = []

print("=" * 70)
print("HTBench Repository Downloader")
print("=" * 70)

for _, row in tqdm(df.iterrows(), total=len(df)):

    repo_name = row["source_name"]
    repo_url = row["url"]

    target = DOWNLOAD_DIR / repo_name

    # Already downloaded
    if target.exists():

        print(f"[SKIP] {repo_name}")

        row = row.copy()
        row["status"] = "Already Downloaded"

        downloaded.append(row)

        continue

    # Clone
    try:

        print(f"[CLONING] {repo_name}")

        Repo.clone_from(
            repo_url,
            target,
            depth=1
        )

        row = row.copy()
        row["status"] = "Downloaded"

        downloaded.append(row)

    except GitCommandError as e:

        print(f"[FAILED] {repo_name}")

        row = row.copy()
        row["status"] = "Clone Failed"

        downloaded.append(row)

        continue

downloaded = pd.DataFrame(downloaded)

downloaded.to_csv(
    OUTPUT,
    index=False
)

print()
print("=" * 70)
print("Download Summary")
print("=" * 70)

print(downloaded["status"].value_counts())

print()

print(f"Saved to {OUTPUT}")