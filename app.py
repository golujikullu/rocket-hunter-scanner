import os
import time
import logging
import requests
from threading import Thread
from flask import Flask

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
    return "🚀 Rocket Hunter LIVE"

# =========================
# TELEGRAM CONFIG
# =========================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# API
# =========================

DEXSCREENER_API_URL = (
    "https://api.dexscreener.com/latest/dex/search?q=solana"
)

# =========================
# SETTINGS
# =========================

SCAN_INTERVAL = 20

# FIRST ALERT FILTERS
MIN_LIQUIDITY = 500
MIN_VOLUME = 500

# =========================
# DUPLICATE FILTER
# =========================

SENT_PAIRS = {}
COOLDOWN_SECONDS = 3600

# =========================
# TELEGRAM FUNCTION
# =========================

def send_telegram_alert(
    token_name,
    symbol,
    liquidity,
    volume,
    price,
    pair_address
):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ TELEGRAM VARIABLES MISSING")
        return False

    message = f"""
🚀 Rocket Hunter Alert

💎 Token: {token_name} ({symbol})

💰 Price: ${price}

💧 Liquidity: ${liquidity:,.2f}

📊 Volume 24H: ${volume:,.2f}

🔗 Pair:
https://dexscreener.com/solana/{pair_address}
"""

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        logging.info(
            f"📩 Telegram Response: {response.status_code}"
        )

        if response.status_code == 200:
            return True

    except Exception as e:
        logging.error(f"❌ Telegram Error: {e}")

    return False

# =========================
# SCANNER
# =========================

def scan_pairs():

    global SENT_PAIRS

    logging.info("🔎 Scanning Solana pairs...")

    try:

        response = requests.get(
            DEXSCREENER_API_URL,
            timeout=15
        )

        logging.info(
            f"✅ API STATUS: {response.status_code}"
        )

        if response.status_code != 200:
            return

        data = response.json()

        pairs = data.get("pairs", [])

        logging.info(f"📊 Pairs Found: {len(pairs)}")

        now = time.time()

        alerts_sent = 0

        for pair in pairs:

            try:

                chain = pair.get("chainId")

                if chain != "solana":
                    continue

                pair_address = pair.get("pairAddress")

                if not pair_address:
                    continue

                # DUPLICATE FILTER
                last_seen = SENT_PAIRS.get(
                    pair_address,
                    0
                )

                if now - last_seen < COOLDOWN_SECONDS:
                    continue

                base_token = pair.get(
                    "baseToken",
                    {}
                )

                token_name = base_token.get(
                    "name",
                    ""
                ).strip()

                symbol = base_token.get(
                    "symbol",
                    ""
                ).strip()

                if not token_name or not symbol:
                    continue

                liquidity = float(
                    pair.get(
                        "liquidity",
                        {}
                    ).get(
                        "usd",
                        0
                    )
                )

                volume = float(
                    pair.get(
                        "volume",
                        {}
                    ).get(
                        "h24",
                        0
                    )
                )

                price = pair.get(
                    "priceUsd",
                    "0"
                )

                # DEBUG
                logging.info(
                    f"TOKEN {symbol} | "
                    f"Liq ${liquidity} | "
                    f"Vol ${volume}"
                )

                # FILTERS
                if liquidity < MIN_LIQUIDITY:
                    continue

                if volume < MIN_VOLUME:
                    continue

                logging.info(
                    f"🚨 ALERT FOUND: {symbol}"
                )

                success = send_telegram_alert(
                    token_name,
                    symbol,
                    liquidity,
                    volume,
                    price,
                    pair_address
                )

                if success:

                    SENT_PAIRS[pair_address] = now

                    alerts_sent += 1

                    logging.info(
                        f"🎯 ALERT SENT: {symbol}"
                    )

                    time.sleep(2)

                    # LIMIT
                    if alerts_sent >= 3:
                        break

            except Exception as e:
                logging.error(
                    f"PAIR ERROR: {e}"
                )

        logging.info(
            f"✅ Scan Complete | Alerts: {alerts_sent}"
        )

    except Exception as e:
        logging.error(f"❌ SCAN ERROR: {e}")

# =========================
# LOOP
# =========================

def scanner_loop():

    logging.info(
        "⚡ Scanner Thread Started"
    )

    while True:

        scan_pairs()

        logging.info(
            f"⏳ Waiting {SCAN_INTERVAL} seconds..."
        )

        time.sleep(SCAN_INTERVAL)

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    logging.info(
        "🚀 Rocket Hunter Starting..."
    )

    scanner_thread = Thread(
        target=scanner_loop,
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
