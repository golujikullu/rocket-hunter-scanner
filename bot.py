import requests
import time
import threading
from flask import Flask
import os

app = Flask(__name__)

# =========================
# TELEGRAM CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# DEXSCREENER API
# =========================

DEX_API = "https://api.dexscreener.com/latest/dex/pairs/solana"

# =========================
# DUPLICATE STORAGE
# =========================

sent_tokens = set()

# =========================
# TELEGRAM FUNCTION
# =========================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }

        response = requests.post(url, json=payload, timeout=10)

        print("TELEGRAM RESULT:", response.text)

    except Exception as e:
        print("Telegram Error:", e)

# =========================
# SCANNER
# =========================

def scan_tokens():

    try:
        response = requests.get(DEX_API, timeout=20)
        data = response.json()

        pairs = data.get("pairs", [])

        print(f"PAIRS FOUND: {len(pairs)}")

        for pair in pairs:

            liquidity = pair.get("liquidity", {}).get("usd", 0)

            # TESTING MODE
            if liquidity < 1000:
                continue

            base = pair.get("baseToken", {})

            token_name = base.get("name", "Unknown")
            symbol = base.get("symbol", "???")
            token_address = base.get("address")

            # DUPLICATE SUPPRESSION
            if token_address in sent_tokens:
                continue

            sent_tokens.add(token_address)

            volume = pair.get("volume", {}).get("h24", 0)
            pair_url = pair.get("url", "")

            message = f"""
🚀 <b>Rocket Hunter Alert</b>

🪙 Token: {token_name} ({symbol})
💧 Liquidity: ${liquidity:,.0f}
📊 Volume 24H: ${volume:,.0f}
⛓ Chain: Solana

🔗 {pair_url}
"""

            print(f"[ALERT] {token_name}")

            send_telegram(message)

            time.sleep(2)

    except Exception as e:
        print("Scanner Error:", e)

# =========================
# LOOP
# =========================

def scan_loop():

    while True:

        print("[SCAN RUNNING]")

        scan_tokens()

        time.sleep(60)

# =========================
# FLASK
# =========================

@app.route("/")
def home():
    return "Rocket Hunter Live 🚀"

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    print("🚀 ROCKET HUNTER STARTING...")

    try:
        send_telegram("🚀 Rocket Hunter Test Alert")
        print("✅ TEST ALERT SENT")
    except Exception as e:
        print("❌ TELEGRAM ERROR:", e)

    scanner_worker = threading.Thread(target=scan_loop)
    scanner_worker.daemon = True
    scanner_worker.start()

    print("✅ SCAN THREAD STARTED")

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
