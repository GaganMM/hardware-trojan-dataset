from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import zipfile

SKIP_ARCHIVES = {
    "b15-T300.zip",
    "b19-T100.part01.rar",
    "vga_lcd-T100.zip",

    "EthernetMAC10GE-T100.part01.rar",
    "EthernetMAC10GE-T200.part01.rar",
    "EthernetMAC10GE-T300.part01.rar",
    "EthernetMAC10GE-T400.part01.rar",
    "EthernetMAC10GE-T500.part01.rar",
    "EthernetMAC10GE-T600.part01.rar",
    "EthernetMAC10GE-T700.part01.rar",
    "EthernetMAC10GE-T710.part01.rar",
    "EthernetMAC10GE-T720.part01.rar",
    "EthernetMAC10GE-T730.part01.rar",
}
DOWNLOAD_DIR = Path("downloads/trusthub")
OUTPUT_DIR = Path("downloads/trusthub_extracted")

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def extract_zip(path: Path):

    target = OUTPUT_DIR / path.stem
    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(target)

    print(f"[ZIP] {path.name}")


def extract_rar(archive: Path):

    target = OUTPUT_DIR / archive.stem
    target.mkdir(parents=True, exist_ok=True)

    possible_paths = [
        shutil.which("7z"),
        shutil.which("7zz"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]

    seven_zip = None

    for exe in possible_paths:
        if exe and Path(exe).exists():
            seven_zip = exe
            break

    if seven_zip is None:
        print("[ERROR] 7-Zip not found")
        return

    subprocess.run(
        [
            seven_zip,
            "x",
            "-y",
            str(archive),
            f"-o{target}",
        ],
        check=True,
    )

    print(f"[RAR] {archive.name}")
def main():

    archives = sorted(DOWNLOAD_DIR.iterdir())
    archives = [a for a in archives if a.name not in SKIP_ARCHIVES]

    print(f"Archives : {len(archives)}")

    for archive in archives:
        if archive.name in SKIP_ARCHIVES:
            print(f"[SKIP] {archive.name}")
            continue
        suffix = archive.suffix.lower()

        try:

            if suffix == ".zip":

                extract_zip(archive)

            elif suffix == ".rar":

                name = archive.name.lower()

                # Skip continuation volumes
                if ".part" in name and not name.endswith(".part01.rar"):
                    continue

                extract_rar(archive)

        except Exception as e:

            print(f"[FAIL] {archive.name} : {e}")

    print()

    print("[DONE]")


if __name__ == "__main__":
    main()