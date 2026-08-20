from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.dataset.config import DatasetConfig


TRUSTHUB_REPOS = [
    # Fill with actual TrustHub Git repository URLs
    # Example:
    # "https://github.com/<org>/AES-T100.git",
]


def clone(url: str, destination: Path):

    repo = url.split("/")[-1].replace(".git", "")

    target = destination / repo

    if target.exists():
        print(f"[SKIP] {repo}")
        return

    print(f"[CLONE] {repo}")

    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            url,
            str(target),
        ],
        check=True,
    )


def main():

    config = DatasetConfig.from_project_root(
        Path(__file__).resolve().parents[2]
    )

    destination = config.downloads / "trusthub"

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    for repo in TRUSTHUB_REPOS:
        clone(repo, destination)


if __name__ == "__main__":
    main()