from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path("downloads/trusthub_extracted")
OUTPUT = Path("metadata/trusthub_inventory.csv")

RTL_EXTENSIONS = {
    ".v",
    ".vh",
    ".sv",
    ".svh",
}


def count_loc(path: Path) -> int:

    try:
        with open(path, "r", errors="ignore") as f:
            return sum(1 for _ in f)

    except Exception:
        return 0


def language(ext: str) -> str:

    if ext in {".sv", ".svh"}:
        return "SystemVerilog"

    return "Verilog"

print("Entered main()")
print(ROOT)
print(ROOT.exists())
def main():

    rows = []

    files = sorted(ROOT.rglob("*"))

    rtl = [
        f
        for f in files
        if f.is_file()
        and f.suffix.lower() in RTL_EXTENSIONS
    ]

    print(f"RTL Files : {len(rtl)}")

    for file in rtl:

        relative = file.relative_to(ROOT)

        repository = relative.parts[0]

        rows.append({

            "repository": repository,

            "family": repository,

            "file_name": file.name,

            "relative_path": str(relative),

            "language": language(file.suffix.lower()),

            "loc": count_loc(file),

            "source": "TrustHub"

        })

    df = pd.DataFrame(rows)

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT,
        index=False,
    )

    print()

    print(df.head())

    print()

    print(f"Saved : {OUTPUT}")

    print(f"RTL Files : {len(df)}")

    print(f"Repositories : {df.repository.nunique()}")


if __name__ == "__main__":
    print("Starting TrustHub inventory...")
    main()