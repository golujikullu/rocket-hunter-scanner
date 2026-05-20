from flask import Flask
import requests
import threading
import time

BOT_TOKEN = "8913220765:AAG_Ncc_PqgbG6-mLSOklcDeX_-HRed41Wc"
CHAT_ID = "YOUR_CHAT_ID"

app = Flask(__name__)

sent_tokens = set()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=payload)

def scan_trending():

    while True:

        try:

            url = "https://api.dexscreener.com/latest/dex/search/?q=solana"

            response = requests.get(url)
            data = response.json()

            pairs = data.get("pairs", [])

            for pair in pairs[:10]:

                symbol = pair.get("baseToken", {}).get("symbol", "UNKNOWN")
                price = pair.get("priceUsd", "0")
                volume = pair.get("volume", {}).get("h24", 0)
                liquidity = pair.get("liquidity", {}).get("usd", 0)
                pair_url = pair.get("url", "")

                token_id = f"{symbol}-{price}"

                if token_id not in sent_tokens and float(liquidity) > 30000:

                    message = f"""
🚀 Rocket Hunter Alert

🪙 Token: {symbol}
💵 Price: ${price}
💧 Liquidity: ${liquidity}
📈 Volume 24h: ${volume}

🔗 {pair_url}
"""

                    send_telegram(message)

                    sent_tokens.add(token_id)

            time.sleep(300)

        except Exception as e:
            print(e)
            time.sleep(60)

@app.route('/')
def home():
    return "Rocket Hunter Scanner Running 🚀"

threading.Thread(target=scan_trending).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
