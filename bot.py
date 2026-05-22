from flask import Flask
import requests
import os
import time

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Prevent duplicate spam
sent_tokens = set()

# Minimum liquidity filter
MIN_LIQUIDITY = 10000

@app.route("/")
def home():
    return "Rocket Hunter Running 🚀"

@app.route("/health")
def health():
    return "OK", 200


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)


def scan_tokens():

    url = "https://api.dexscreener.com/latest/dex/search/?q=solana"

    try:
        response = requests.get(url, timeout=15)
        data = response.json()

        pairs = data.get("pairs", [])

        for pair in pairs:

            # Solana only
            if pair.get("chainId") != "solana":
                continue

            liquidity = pair.get("liquidity", {}).get("usd", 0)

            if not liquidity:
                continue

            liquidity = float(liquidity)

            # Liquidity filter
            if liquidity < MIN_LIQUIDITY:
                continue

            base_token = pair.get("baseToken", {})

            token_name = base_token.get("name", "Unknown")
            symbol = base_token.get("symbol", "???")
            token_address = base_token.get("address")

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


if __name__ == "__main__":

    while True:
        print("[SCAN RUNNING]")

        scan_tokens()

        time.sleep(60)
