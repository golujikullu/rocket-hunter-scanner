from flask import Flask
from threading import Thread
import requests
import time
import os
import logging

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================
# FLASK APP
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 Rocket Hunter LIVE", 200

# =========================
# ENV VARIABLES
# =========================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# DEXSCREENER API
# =========================

DEX_URL = "https://api.dexscreener.com/latest/dex/search?q=SOL"

# =========================
# MEMORY CACHE
# =========================

SENT_PAIRS = set()

# =========================
# TELEGRAM ALERT
# =========================

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

💰 Liquidity: ${liquidity:,.0f}

📊 Volume 24h: ${volume:,.0f}

🔗 DexScreener:
https://dexscreener.com/solana/{pair_address}
"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            logging.info(f"✅ ALERT SENT: {symbol}")
            return True

        else:
            logging.error(
                f"❌ Telegram Error: {response.text}"
            )

    except Exception as e:
        logging.error(f"❌ Telegram Failed: {e}")

    return False

# =========================
# SCANNER LOOP
# =========================

def scanner():

    global SENT_PAIRS

    logging.info("🚀 Scanner Started")

    while True:

        try:

            response = requests.get(
                DEX_URL,
                timeout=15
            )

            logging.info(
                f"✅ API STATUS: {response.status_code}"
            )

            if response.status_code != 200:
                time.sleep(20)
                continue

            data = response.json()

            pairs = data.get("pairs", [])

            logging.info(
                f"📊 Pairs Found: {len(pairs)}"
            )

            for pair in pairs:

                try:

                    # =========================
                    # ONLY SOLANA
                    # =========================

                    if pair.get("chainId") != "solana":
                        continue

                    pair_address = pair.get(
                        "pairAddress",
                        ""
                    )

                    if not pair_address:
                        continue

                    # =========================
                    # DUPLICATE SKIP
                    # =========================

                    if pair_address in SENT_PAIRS:
                        continue

                    # =========================
                    # TOKEN DATA
                    # =========================

                    base_token = pair.get(
                        "baseToken",
                        {}
                    )

                    symbol = base_token.get(
                        "symbol",
                        ""
                    ).strip()

                    name = base_token.get(
                        "name",
                        ""
                    ).strip()

                    # =========================
                    # UNKNOWN FILTER
                    # =========================

                    if not symbol:
                        continue

                    if not name:
                        continue

                    if symbol == "???":
                        continue

                    if name.lower() == "unknown":
                        continue

                    # =========================
                    # LIQUIDITY + VOLUME
                    # =========================

                    liquidity_usd = float(
                        pair.get(
                            "liquidity",
                            {}
                        ).get(
                            "usd",
                            0
                        )
                    )

                    volume_usd = float(
                        pair.get(
                            "volume",
                            {}
                        ).get(
                            "h24",
                            0
                        )
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

                        SENT_PAIRS.add(
                            pair_address
                        )

                        logging.info(
                            f"🔥 REAL ALERT: {symbol}"
                        )

                        # cache clean
                        if len(SENT_PAIRS) > 1000:
                            SENT_PAIRS.clear()

                        time.sleep(5)

                except Exception as pair_error:

                    logging.error(
                        f"❌ Pair Error: {pair_error}"
                    )

        except Exception as e:

            logging.error(
                f"❌ Scanner Error: {e}"
            )

        # =========================
        # LOOP DELAY
        # =========================

        logging.info("⏳ Waiting 20 seconds...")
        time.sleep(20)

# =========================
# START
# =========================

if __name__ == "__main__":

    thread = Thread(
        target=scanner,
        daemon=True
    )

    thread.start()

    port = int(
        os.getenv("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
