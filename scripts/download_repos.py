from pathlib import Path
import subprocess
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "repos.csv"
DOWNLOAD_DIR = ROOT / "downloads"

DOWNLOAD_DIR.mkdir(exist_ok=True)

df = pd.read_csv(CSV)

for idx, row in df.iterrows():

    url = str(row["github_url"]).strip()
    name = row["name"]

    if url == "" or url == "nan":
        print(f"[SKIP] {name} (URL missing)")
        continue

    target = DOWNLOAD_DIR / name

    if target.exists():
        print(f"[EXISTS] {name}")
        df.loc[idx, "status"] = "downloaded"
        continue

    print(f"[CLONING] {name}")

    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                url,
                str(target)
            ],
            check=True
        )

        df.loc[idx, "status"] = "downloaded"

    except Exception as e:

        print(f"[FAILED] {name}")
        print(e)

        df.loc[idx, "status"] = "failed"

df.to_csv(CSV, index=False)

print("\nRepository download complete.")