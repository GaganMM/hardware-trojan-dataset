from pathlib import Path
from tqdm import tqdm
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "metadata" / "downloaded_sources.csv"
OUTPUT = ROOT / "metadata" / "verified_sources.csv"

DOWNLOADS = ROOT / "downloads"

df = pd.read_csv(INPUT)

verified = []

print("=" * 70)
print("HTBench Repository Verifier")
print("=" * 70)


def repository_size(folder: Path):

    total = 0

    for file in folder.rglob("*"):

        if file.is_file():

            total += file.stat().st_size

    return round(total / (1024 * 1024), 2)


def find_top_candidates(folder: Path):

    candidates = []

    keywords = [

        "top",
        "core",
        "cpu",
        "soc",
        "aes",
        "uart",
        "spi",
        "can",
        "eth",
        "main"

    ]

    for ext in ("*.v", "*.sv"):

        for file in folder.rglob(ext):

            name = file.stem.lower()

            for k in keywords:

                if k in name:

                    candidates.append(file.stem)

                    break

    return ", ".join(sorted(set(candidates[:10])))


for _, row in tqdm(df.iterrows(), total=len(df)):

    repo = DOWNLOADS / row["source_name"]

    if not repo.exists():

        continue

    verilog = list(repo.rglob("*.v"))
    sv = list(repo.rglob("*.sv"))

    rtl = len(verilog) + len(sv)

    if rtl == 0:

        continue

    readme = any(repo.glob("README*"))
    license_file = any(repo.glob("LICENSE*"))

    row = row.copy()

    row["rtl_files"] = rtl
    row["verilog_files"] = len(verilog)
    row["systemverilog_files"] = len(sv)

    row["readme"] = readme
    row["license"] = license_file

    row["size_mb"] = repository_size(repo)

    row["top_candidates"] = find_top_candidates(repo)

    row["status"] = "Verified"

    verified.append(row)

verified = pd.DataFrame(verified)

if verified.empty:

    print("No RTL repositories found.")

    exit()

verified = verified.sort_values(
    by="rtl_files",
    ascending=False
)

verified.to_csv(
    OUTPUT,
    index=False
)

print()

print("=" * 70)
print("Verification Complete")
print("=" * 70)

print(

    verified[
        [

            "source_name",

            "rtl_files",

            "verilog_files",

            "systemverilog_files",

            "size_mb"

        ]

    ].head(20)

)

print()

print(f"Verified repositories : {len(verified)}")

print(f"Saved to {OUTPUT}")