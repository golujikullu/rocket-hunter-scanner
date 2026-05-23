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

# =========================
# ENV VARIABLES
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
MIN_LIQUIDITY = 5000
MIN_VOLUME = 10000

# =========================
# DUPLICATE FILTER
# =========================

SENT_PAIRS = {}

COOLDOWN_SECONDS = 7200

# =========================
# FLASK ROUTE
# =========================

@app.route("/")
def home():
    return "🚀 Rocket Hunter LIVE"

# =========================
# TELEGRAM ALERT
# =========================

def send_telegram_alert(
    token_name,
    symbol,
    liquidity,
    volume,
    pair_address,
    price
):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ Telegram credentials missing")
        return False

    dex_link = (
        f"https://dexscreener.com/solana/{pair_address}"
    )

    message = f"""
🚀 <b>Rocket Hunter Alert</b>

💎 <b>{token_name} ({symbol})</b>

💰 Price: ${price}

💧 Liquidity: ${int(liquidity):,}

📊 Volume 24H: ${int(volume):,}

📈 <a href="{dex_link}">DexScreener Link</a>
"""

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        logging.info(
            f"📩 Telegram Response: {response.text}"
        )

        return response.status_code == 200

    except Exception as e:

        logging.error(
            f"❌ Telegram Error: {e}"
        )

        return False

# =========================
# MAIN SCANNER
# =========================

def scan_pairs():

    global SENT_PAIRS

    logging.info(
        "🔎 Scanning Solana pairs..."
    )

    try:

        response = requests.get(
            DEXSCREENER_API_URL,
            timeout=20
        )

        logging.info(
            f"✅ API STATUS: {response.status_code}"
        )

        if response.status_code != 200:
            return

        data = response.json()

        pairs = data.get("pairs", [])

        logging.info(
            f"📊 Pairs Found: {len(pairs)}"
        )

        now = time.time()

        alert_count = 0

        for pair in pairs[:50]:

            try:

                # =========================
                # CHAIN CHECK
                # =========================

                if pair.get("chainId") != "solana":
                    continue

                # =========================
                # SAFE PARSING
                # =========================

                base = pair.get("baseToken", {})

                token_name = str(
                    base.get("name", "Unknown")
                ).strip()

                symbol = str(
                    base.get("symbol", "???")
                ).strip()

                pair_address = str(
                    pair.get("pairAddress", "")
                ).strip()

                # =========================
                # EMPTY CHECK
                # =========================

                if not symbol or symbol == "???":
                    continue

                if not pair_address:
                    continue

                if symbol.upper() in [
                    "SOL",
                    "WSOL"
                ]:
                    continue

                # =========================
                # MARKET DATA
                # =========================

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
                    "N/A"
                )

                # =========================
                # FILTERS
                # =========================

                if liquidity < MIN_LIQUIDITY:
                    continue

                if volume < MIN_VOLUME:
                    continue

                # =========================
                # DUPLICATE FILTER
                # =========================

                last_seen = SENT_PAIRS.get(
                    pair_address,
                    0
                )

                if (
                    now - last_seen
                    < COOLDOWN_SECONDS
                ):
                    continue

                SENT_PAIRS[pair_address] = now

                # =========================
                # ALERT
                # =========================

                logging.info(
                    f"🚨 ALERT: "
                    f"{token_name} ({symbol})"
                )

                ok = send_telegram_alert(
                    token_name,
                    symbol,
                    liquidity,
                    volume,
                    pair_address,
                    price
                )

                if ok:
                    alert_count += 1

                time.sleep(2)

                # =========================
                # LIMIT
                # =========================

                if alert_count >= 5:
                    break

            except Exception as e:

                logging.error(
                    f"❌ Pair Error: {e}"
                )

        logging.info(
            f"✅ Scan Complete | Alerts: "
            f"{alert_count}"
        )

    except Exception as e:

        logging.error(
            f"❌ Scan Error: {e}"
        )

# =========================
# LOOP
# =========================

def scanner_loop():

    logging.info(
        "⚡ Scanner Thread Started"
    )

    time.sleep(5)

    while True:

        scan_pairs()

        logging.info(
            f"⏳ Waiting "
            f"{SCAN_INTERVAL} seconds..."
        )

        time.sleep(SCAN_INTERVAL)

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    logging.info(
        "🚀 Rocket Hunter Starting..."
    )

    scanner_worker = Thread(
        target=scanner_loop,
        daemon=True
    )

    scanner_worker.start()

    logging.info(
        "✅ Scanner Thread Running"
    )

    port = int(
        os.getenv("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
