import requests
import time
import threading
from flask import Flask
import os
import sys

app = Flask(__name__)

# =========================
# TELEGRAM CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# DEXSCREENER API
# =========================

DEX_URL = "https://api.dexscreener.com/latest/dex/pairs/solana"

# =========================
# TELEGRAM FUNCTION
# =========================

def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(url, data=data)

    print("TELEGRAM STATUS:", response.status_code, flush=True)
    print("TELEGRAM RESPONSE:", response.text, flush=True)

# =========================
# TOKEN SCANNER
# =========================

def scan_tokens():

    print("[SCAN STARTED]", flush=True)

    try:

        response = requests.get(DEX_URL)

        data = response.json()

        pairs = data.get("pairs", [])

        print(f"TOTAL PAIRS FOUND: {len(pairs)}", flush=True)

        for pair in pairs[:5]:

            try:

                name = pair.get("baseToken", {}).get("name", "Unknown")
                symbol = pair.get("baseToken", {}).get("symbol", "???")

                liquidity = pair.get("liquidity", {}).get("usd", 0)

                volume = pair.get("volume", {}).get("h24", 0)

                price_change = pair.get("priceChange", {}).get("h24", 0)

                link = pair.get("url", "")

                message = f"""
🚀 Rocket Hunter Alert

🪙 Token: {name} ({symbol})

💧 Liquidity: ${liquidity}
📈 24H Volume: ${volume}
🔥 24H Change: {price_change}%

🔗 {link}
"""

                print(f"ALERT SENT: {symbol}", flush=True)

                send_telegram(message)

                time.sleep(3)

            except Exception as e:

                print("PAIR ERROR:", e, flush=True)

    except Exception as e:

        print("SCAN ERROR:", e, flush=True)

# =========================
# LOOP
# =========================

def scan_loop():

    while True:

        print("[SCAN RUNNING]", flush=True)

        scan_tokens()

        print("[WAITING 60 SECONDS]", flush=True)

        time.sleep(60)

# =========================
# FLASK SERVER
# =========================

@app.route("/")
def home():

    return "Rocket Hunter Live 🚀"

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    print("🚀 ROCKET HUNTER STARTING...", flush=True)

    try:

        send_telegram("🚀 Rocket Hunter Test Alert Working!")

        print("✅ TEST ALERT SENT", flush=True)

    except Exception as e:

        print("❌ TELEGRAM ERROR:", e, flush=True)

    scanner_worker = threading.Thread(target=scan_loop)

    scanner_worker.daemon = True

    scanner_worker.start()

    print("✅ SCAN THREAD STARTED", flush=True)

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
