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
    "https://api.dexscreener.com/latest/dex/search?q=SOL"
)

# =========================
# SETTINGS
# =========================

SCAN_INTERVAL = 20

# FIRST ALERT FILTERS
MIN_LIQUIDITY = 500
MIN_VOLUME = 100

# =========================
# DUPLICATE FILTER
# =========================

SENT_PAIRS = {}

COOLDOWN_SECONDS = 7200

# =========================
# TELEGRAM FUNCTION
# =========================

def send_telegram_alert(
    token_name,
    token_symbol,
    liquidity,
    volume,
    pair_address,
    price,
    dex_url
):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ Telegram ENV variables missing")
        return False

    message = f"""
🚀 ROCKET HUNTER ALERT

💎 Token: {token_name} ({token_symbol})

💰 Price: ${price}

💧 Liquidity: ${liquidity:,.2f}

📊 Volume: ${volume:,.2f}

🔗 Pair:
{pair_address}

📈 Dex:
{dex_url}
"""

    telegram_url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            telegram_url,
            data=payload,
            timeout=10
        )

        logging.info(
            f"📩 TELEGRAM RESPONSE: {response.status_code}"
        )

        return response.status_code == 200

    except Exception as e:

        logging.error(f"❌ Telegram Error: {e}")

        return False

# =========================
# SCANNER
# =========================

def scan_pairs():

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

        alerts_sent = 0

        current_time = time.time()

        for pair in pairs:

            try:

                if pair.get("chainId") != "solana":
                    continue

                # =========================
                # NEW PAIR FILTER
                # =========================

                pair_created = pair.get(
                    "pairCreatedAt",
                    0
                )

                if pair_created:

                    age_minutes = (
                        (time.time() * 1000 - pair_created)
                        / 60000
                    )

                    if age_minutes > 120:
                        continue

                # =========================
                # TOKEN INFO
                # =========================

                base_token = pair.get(
                    "baseToken",
                    {}
                )

                token_name = base_token.get(
                    "name",
                    ""
                ).strip()

                token_symbol = base_token.get(
                    "symbol",
                    ""
                ).strip()

                pair_address = pair.get(
                    "pairAddress",
                    ""
                )

                dex_url = pair.get(
                    "url",
                    ""
                )

                # =========================
                # JUNK FILTER
                # =========================

                if not token_name:
                    continue

                if not token_symbol:
                    continue

                if token_symbol.upper() in [
                    "SOL",
                    "WSOL",
                    "USDC",
                    "USDT",
                    "WETH"
                ]:
                    continue

                # =========================
                # DUPLICATE FILTER
                # =========================

                last_alert = SENT_PAIRS.get(
                    pair_address,
                    0
                )

                if (
                    current_time - last_alert
                    < COOLDOWN_SECONDS
                ):
                    continue

                # =========================
                # PRICE
                # =========================

                price = pair.get(
                    "priceUsd",
                    "0"
                )

                # =========================
                # LIQUIDITY
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

                # =========================
                # VOLUME
                # =========================

                volume_data = pair.get(
                    "volume",
                    {}
                )

                volume = (
                    volume_data.get("h24")
                    or volume_data.get("h6")
                    or volume_data.get("h1")
                    or volume_data.get("m5")
                    or 0
                )

                volume = float(volume)

                # =========================
                # DEBUG
                # =========================

                logging.info(
                    f"TOKEN {token_symbol} | "
                    f"Liq ${liquidity:.2f} | "
                    f"Vol ${volume:.2f}"
                )

                # =========================
                # FILTERS
                # =========================

                if liquidity < MIN_LIQUIDITY:
                    continue

                if volume < MIN_VOLUME:
                    continue

                # =========================
                # ALERT FOUND
                # =========================

                logging.info(
                    f"🚨 ALERT FOUND: "
                    f"{token_symbol}"
                )

                success = send_telegram_alert(
                    token_name,
                    token_symbol,
                    liquidity,
                    volume,
                    pair_address,
                    price,
                    dex_url
                )

                if success:

                    SENT_PAIRS[pair_address] = (
                        current_time
                    )

                    alerts_sent += 1

                    logging.info(
                        f"🎯 ALERT SENT: "
                        f"{token_symbol}"
                    )

                    time.sleep(2)

                # =========================
                # LIMIT
                # =========================

                if alerts_sent >= 5:
                    break

            except Exception as pair_error:

                logging.error(
                    f"❌ Pair Error: "
                    f"{pair_error}"
                )

        logging.info(
            f"✅ Scan Complete | "
            f"Alerts: {alerts_sent}"
        )

    except Exception as e:

        logging.error(
            f"💥 Scanner Error: {e}"
        )

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
