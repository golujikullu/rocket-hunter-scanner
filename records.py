import csv
import os
from datetime import datetime

FILE = "records.csv"

FIELDS = [
    "timestamp",
    "symbol",
    "price",
    "trigger",
    "source"
]

def save_record():
    print("\n=== ROCKET HUNTER RECORD ===")

    symbol = input("Symbol/Coin: ").strip()
    price = input("Price: ").strip()
    trigger = input("Trigger/Reason: ").strip()
    source = input("Source: ").strip()

    exists = os.path.exists(FILE)

    with open(FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)

        if not exists:
            writer.writeheader()

        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "price": price,
            "trigger": trigger,
            "source": source
        })

    print("\n✅ RECORD SAVED")
    print(f"📁 File: {FILE}")

if __name__ == "__main__":
    save_record()
