from flask import Flask
import requests
import os
import time
import threading

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Prevent duplicate spam
sent_tokens = set()

DEX_API = "https://api.dexscreener.com/latest/dex/search/?q=solana"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

@app.route("/")
def home():
    return "Rocket Hunter Running 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
    return "OK", 200

def scan_tokens():
    try:
        response = requests.get(DEX_API, timeout=15)
        data = response.json()

        pairs = data.get("pairs", [])

        for pair in pairs:

            # Solana only
            if pair.get("chainId") != "solana":
                continue

            liquidity = pair.get("liquidity", {}).get("usd", 0)

            # Minimum liquidity filter
            if liquidity < 10000:
                continue

            base = pair.get("baseToken", {})

            token_name = base.get("name", "Unknown")
            symbol = base.get("symbol", "???")
            token_address = base.get("address")

            # Duplicate suppression
            if token_address in sent_tokens:
                continue

            sent_tokens.add(token_address)

            volume = pair.get("volume", {}).get("h24", 0)
            pair_url = pair.get("url", "")

            message = f"""
🚀 <b>Rocket Hunter Alert</b>

💎 Token: {token_name} ({symbol})
💧 Liquidity: ${liquidity:,.0f}
📈 Volume 24H: ${volume}
✅ Chain: Solana

🔗 {pair_url}
"""

            print(f"[ALERT] {token_name}")

            send_telegram(message)

    except Exception as e:
        print("Scanner Error:", e)

def scan_loop():
    while True:
        print("[SCAN RUNNING]")

        scan_tokens()

        time.sleep(60)

scanner_worker = threading.Thread(target=scan_loop)
scanner_worker.daemon = True
scanner_worker.start()
