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

DEX_URL = "https://api.dexscreener.com/latest/dex/pairs/solana"

# =========================
# TELEGRAM FUNCTION
# =========================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT TOKEN OR CHAT ID MISSING", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, data=data)

        print("📩 TELEGRAM RESPONSE:", response.text, flush=True)

    except Exception as e:
        print("❌ TELEGRAM ERROR:", e, flush=True)

# =========================
# TOKEN SCANNER
# =========================

def scan_tokens():

    print("🔍 SCANNING TOKENS...", flush=True)

    try:

        response = requests.get(DEX_URL)

        print("✅ API STATUS:", response.status_code, flush=True)

        if response.status_code == 200:

            message = "🚀 Rocket Hunter Running Successfully"

            send_telegram(message)

        else:
            print("❌ API FAILED", flush=True)

    except Exception as e:
        print("❌ SCAN ERROR:", e, flush=True)

# =========================
# LOOP
# =========================

def scan_loop():

    while True:

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

    print("🚀 ROCKET HUNTER STARTING...", flush=True)

    scanner_worker = threading.Thread(target=scan_loop)

    scanner_worker.daemon = True

    scanner_worker.start()

    print("✅ SCAN THREAD STARTED", flush=True)

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
