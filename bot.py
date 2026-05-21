from flask import Flask, request
import requests
import time
import os

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

sent_tokens = set()


def send_message(text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    requests.post(url, json=payload)


def scan_tokens():

    try:

        url = "https://api.dexscreener.com/latest/dex/pairs/solana"

        response = requests.get(url).json()

        pairs = response.get("pairs", [])

        for pair in pairs[:20]:

            name = pair.get("baseToken", {}).get("name", "Unknown")

            symbol = pair.get("baseToken", {}).get("symbol", "")

            pair_url = pair.get("url", "")

            liquidity = float(
                pair.get("liquidity", {}).get("usd", 0)
            )

            volume = float(
                pair.get("volume", {}).get("h24", 0)
            )

            key = f"{name}_{symbol}"

            if key in sent_tokens:
                continue

            if liquidity > 5000 and volume > 10000:

                text = f"""
🚀 <b>Rocket Hunter Alert</b>

💎 {name} ({symbol})

💧 Liquidity: ${liquidity:,.0f}
📈 Volume 24h: ${volume:,.0f}

🔗 {pair_url}
"""

                send_message(text)

                sent_tokens.add(key)

    except Exception as e:

        print("ERROR:", e)


@app.route("/")
def home():
    return "Rocket Hunter Running 🚀"


@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json(force=True)

    if "message" in data:

        chat_id = data["message"]["chat"]["id"]

        text = data["message"].get("text", "")

        if text == "/start":

            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

            payload = {
                "chat_id": chat_id,
                "text": "🚀 Rocket Hunter Activated!"
            }

            requests.post(url, json=payload)

    return "ok", 200


if __name__ == "__main__":

    while True:

        scan_tokens()

        time.sleep(300)
