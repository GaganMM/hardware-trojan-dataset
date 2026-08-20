from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

DOWNLOADS = ROOT / "downloads"
OUTPUT = ROOT / "metadata" / "rtl_inventory.csv"

rows = []

counter = 1


def infer_family(path: str):

    p = path.lower()

    keywords = {

        "aes": "AES",
        "sha": "SHA",
        "rsa": "RSA",
        "uart": "UART",
        "spi": "SPI",
        "i2c": "I2C",
        "can": "CAN",
        "ethernet": "Ethernet",
        "eth": "Ethernet",
        "cpu": "CPU",
        "core": "CPU",
        "riscv": "CPU",
        "ibex": "CPU",
        "picorv32": "CPU"

    }

    for k, v in keywords.items():

        if k in p:

            return v

    return "Unknown"


print("=" * 70)
print("RTL Inventory Builder")
print("=" * 70)

for repo in DOWNLOADS.iterdir():

    if not repo.is_dir():
        continue

    for ext in ("*.v", "*.sv"):

        for file in repo.rglob(ext):

            rows.append({

                "rtl_id":
                f"RTL{counter:06d}",

                "repository":
                repo.name,

                "file_name":
                file.name,

                "module":
                file.stem,

                "extension":
                file.suffix,

                "relative_path":
                file.relative_to(repo).as_posix(),

                "family":
                infer_family(file.as_posix()),

                "size_kb":
                round(file.stat().st_size / 1024, 2)

            })

            counter += 1

inventory = pd.DataFrame(rows)

inventory.to_csv(
    OUTPUT,
    index=False
)

print()

print(f"RTL Files : {len(inventory)}")

print()

print(
    inventory.head(20)
)

print()

print(f"Saved to {OUTPUT}")