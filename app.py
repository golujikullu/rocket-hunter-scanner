import os
import time
import requests
import logging
from flask import Flask
from threading import Thread

# =========================================
# LOGGING
# =========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================================
# FLASK
# =========================================

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 Rocket Hunter Gecko LIVE", 200

# =========================================
# TELEGRAM
# =========================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================================
# GECKOTERMINAL API
# =========================================

DEX_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"

# =========================================
# CACHE
# =========================================

SENT_PAIRS = set()

# =========================================
# TELEGRAM ALERT
# =========================================

def send_telegram_alert(
    name,
    symbol,
    liquidity,
    volume,
    pair_address
):

    message = f"""
🚀 Rocket Hunter Alert

💎 Token: {name} ({symbol})

💰 Liquidity: ${liquidity:,.2f}

📊 Volume 24h: ${volume:,.2f}

🔗 Chart:
https://www.geckoterminal.com/solana/pools/{pair_address}
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

        logging.info(
            f"Telegram Status: {response.status_code}"
        )

        if response.status_code == 200:

            logging.info(
                f"✅ ALERT SENT: {symbol}"
            )

            return True

        else:

            logging.error(response.text)

            return False

    except Exception as e:

        logging.error(
            f"Telegram Error: {e}"
        )

        return False

# =========================================
# SCANNER
# =========================================

def scanner():

    logging.info("🚀 Gecko Scanner Started")

    while True:

        try:

            logging.info(
                f"Fetching: {DEX_URL}"
            )

            response = requests.get(
                DEX_URL,
                timeout=15
            )

            logging.info(
                f"API STATUS: {response.status_code}"
            )

            if response.status_code != 200:

                time.sleep(20)
                continue

            data = response.json()

            pairs = data.get("data", [])

            logging.info(
                f"Pools Found: {len(pairs)}"
            )

            alerts = 0

            for pair in pairs:

                try:

                    attributes = pair.get(
                        "attributes",
                        {}
                    )

                    pair_address = attributes.get(
                        "address"
                    )

                    if not pair_address:
                        continue

                    if pair_address in SENT_PAIRS:
                        continue

                    name = attributes.get(
                        "name",
                        "Unknown"
                    )

                    symbol = attributes.get(
                        "symbol",
                        "???"
                    )

                    liquidity_usd = float(
                        attributes.get(
                            "reserve_in_usd",
                            0
                        )
                    )

                    volume_data = attributes.get(
                        "volume_usd",
                        {}
                    )

                    volume_usd = float(
                        volume_data.get(
                            "h24",
                            0
                        )
                    )

                    logging.info(
                        f"💎 {symbol} | "
                        f"Liq ${liquidity_usd} | "
                        f"Vol ${volume_usd}"
                    )

                    # =========================================
                    # REAL FILTER
                    # =========================================

                    if liquidity_usd < 100:
                        continue

                    if volume_usd < 500:
                        continue

                    # =========================================
                    # SEND ALERT
                    # =========================================

                    success = send_telegram_alert(
                        name,
                        symbol,
                        liquidity_usd,
                        volume_usd,
                        pair_address
                    )

                    if success:

                        SENT_PAIRS.add(
                            pair_address
                        )

                        alerts += 1

                        logging.info(
                            f"🔥 ALERT COUNT: {alerts}"
                        )

                        time.sleep(2)

                except Exception as e:

                    logging.error(
                        f"Pair Error: {e}"
                    )

            logging.info(
                f"✅ Scan Complete | Alerts: {alerts}"
            )

        except Exception as e:

            logging.error(
                f"Scanner Crash: {e}"
            )

        logging.info(
            "⏳ Waiting 20 seconds..."
        )

        time.sleep(20)

# =========================================
# MAIN
# =========================================

if __name__ == "__main__":

    scanner_thread = Thread(
        target=scanner,
        daemon=True
    )

    scanner_thread.start()

    port = int(
        os.getenv("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
