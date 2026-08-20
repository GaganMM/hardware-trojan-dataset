from __future__ import annotations

from pathlib import Path
import hashlib
import pandas as pd

GITHUB = Path("metadata/04_unique_inventory.csv")
TRUSTHUB = Path("metadata/trusthub_inventory.csv")

OUTPUT = Path("metadata/06_master_inventory.csv")


def sha256(path: str) -> str:

    p = Path(path)

    if not p.exists():
        return None

    h = hashlib.sha256()

    with open(p, "rb") as f:

        while True:

            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def make_absolute(row):

    if row.source == "GitHub":

        return Path("downloads") / row.repository / row.relative_path

    return Path("downloads") / "trusthub_extracted" / row.relative_path


def main():

    github = pd.read_csv(GITHUB)

    trusthub = pd.read_csv(TRUSTHUB)

    # Add source column
    github["source"] = "GitHub"
    trusthub["source"] = "TrustHub"

    master = pd.concat(
        [trusthub, github],
        ignore_index=True,
    )

    master["absolute_path"] = master.apply(
        make_absolute,
        axis=1,
    )

    master["sha256"] = master.absolute_path.apply(
        lambda p: sha256(str(p))
    )

    before = len(master)

    master = master[
    master["sha256"].isna() |
    ~master["sha256"].duplicated()
    ]

    after = len(master)

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    master.to_csv(
        OUTPUT,
        index=False,
    )

    print()
    print(f"Before : {before}")
    print(f"After  : {after}")
    print(f"Removed: {before-after}")
    print()
    print(f"Saved : {OUTPUT}")


if __name__ == "__main__":
    main()