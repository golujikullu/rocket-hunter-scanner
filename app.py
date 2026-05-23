import os
import time
import requests
import logging
from flask import Flask
from threading import Thread

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================
# FLASK
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 Rocket Hunter LIVE", 200

# =========================
# TELEGRAM
# =========================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# DEXSCREENER API
# =========================

DEX_URL = "https://api.dexscreener.com/latest/dex/pairs/solana"

# =========================
# CACHE
# =========================

SENT_PAIRS = set()

# =========================
# TELEGRAM ALERT
# =========================

def send_telegram_alert(name, symbol, liquidity, volume, pair_address):

    message = f"""
🚀 Rocket Hunter Alert

💎 Token: {name} ({symbol})

💰 Liquidity: ${liquidity}

📊 Volume: ${volume}

🔗 Pair:
https://dexscreener.com/solana/{pair_address}
"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        logging.info(f"Telegram Status: {response.status_code}")

        if response.status_code == 200:
            logging.info(f"✅ ALERT SENT: {symbol}")
            return True

        else:
            logging.error(response.text)
            return False

    except Exception as e:
        logging.error(f"Telegram Error: {e}")
        return False

# =========================
# SCANNER
# =========================

def scanner():

    logging.info("🚀 Scanner Started")

    while True:

        try:

            logging.info(DEX_URL)

            response = requests.get(
                DEX_URL,
                timeout=15
            )

            logging.info(f"API STATUS: {response.status_code}")

            if response.status_code != 200:
                time.sleep(20)
                continue

            data = response.json()

            pairs = data.get("pairs", [])

            logging.info(f"Pairs Found: {len(pairs)}")

            alerts = 0

            for pair in pairs:

                try:

                    pair_address = pair.get("pairAddress")

                    if not pair_address:
                        continue

                    if pair_address in SENT_PAIRS:
                        continue

                    base_token = pair.get("baseToken", {})

                    name = base_token.get("name", "Unknown")
                    symbol = base_token.get("symbol", "???")

                    liquidity_usd = float(
                        pair.get("liquidity", {}).get("usd", 0)
                    )

                    volume_usd = float(
                        pair.get("volume", {}).get("h24", 0)
                    )

                    logging.info(
                        f"💎 {symbol} | "
                        f"Liq ${liquidity_usd} | "
                        f"Vol ${volume_usd}"
                    )

                    # =========================
                    # REAL FILTER
                    # =========================

                    if liquidity_usd < 500:
                        continue

                    if volume_usd < 1000:
                        continue

                    # =========================
                    # SEND ALERT
                    # =========================

                    success = send_telegram_alert(
                        name,
                        symbol,
                        liquidity_usd,
                        volume_usd,
                        pair_address
                    )

                    if success:

                        SENT_PAIRS.add(pair_address)

                        alerts += 1

                        logging.info(
                            f"🔥 ALERT COUNT: {alerts}"
                        )

                        time.sleep(2)

                except Exception as e:
                    logging.error(f"Pair Error: {e}")

            logging.info(
                f"✅ Scan done | Alerts {alerts}"
            )

        except Exception as e:
            logging.error(f"Scanner Crash: {e}")

        logging.info("⏳ Waiting 20 seconds...")

        time.sleep(20)

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    thread = Thread(
        target=scanner,
        daemon=True
    )

    thread.start()

    port = int(
        os.getenv("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
