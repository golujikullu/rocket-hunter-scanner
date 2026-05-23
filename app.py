import os
import time
import logging
import requests
from threading import Thread
from flask import Flask

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
    return "🚀 Rocket Hunter LIVE"

# =========================================
# TELEGRAM CONFIG
# =========================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================================
# API
# =========================================

DEX_API = "https://api.dexscreener.com/latest/dex/search?q=SOL"

# =========================================
# SETTINGS
# =========================================

SCAN_INTERVAL = 20

MIN_LIQUIDITY = 500
MIN_VOLUME = 100

COOLDOWN_SECONDS = 7200

# =========================================
# MEMORY
# =========================================

SENT_ALERTS = {}

# =========================================
# TELEGRAM FUNCTION
# =========================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ Telegram ENV missing")
        return False

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
            data=payload,
            timeout=10
        )

        logging.info(
            f"📩 Telegram Status: "
            f"{response.status_code}"
        )

        return response.status_code == 200

    except Exception as e:

        logging.error(
            f"❌ Telegram Error: {e}"
        )

        return False

# =========================================
# FORMAT ALERT
# =========================================

def build_message(
    name,
    symbol,
    liquidity,
    volume,
    price,
    pair_address,
    dex_url
):

    return f"""
🚀 ROCKET HUNTER ALERT

💎 {name} ({symbol})

💰 Price: ${price}

💧 Liquidity: ${liquidity:,.2f}

📊 Volume: ${volume:,.2f}

🔗 Pair:
{pair_address}

📈 Dex:
{dex_url}
"""

# =========================================
# SCANNER
# =========================================

def scan_pairs():

    logging.info("🔎 Scanning pairs...")

    try:

        response = requests.get(
            DEX_API,
            timeout=15
        )

        logging.info(
            f"✅ API STATUS: "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            return

        data = response.json()

        pairs = data.get("pairs", [])

        logging.info(
            f"📊 TOTAL PAIRS: "
            f"{len(pairs)}"
        )

        alerts_sent = 0

        now = time.time()

        for pair in pairs:

            try:

                # =========================================
                # DEBUG RAW
                # =========================================

                logging.info(
                    f"🧪 RAW SYMBOL: "
                    f"{pair.get('baseToken', {}).get('symbol')}"
                )

                # =========================================
                # TOKEN INFO
                # =========================================

                base = pair.get(
                    "baseToken",
                    {}
                )

                token_name = base.get(
                    "name",
                    ""
                ).strip()

                token_symbol = base.get(
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

                # =========================================
                # SKIP EMPTY
                # =========================================

                if not token_name:
                    continue

                if not token_symbol:
                    continue

                # =========================================
                # SKIP BIG TOKENS
                # =========================================

                upper_symbol = token_symbol.upper()

                if (
                    "SOL" in upper_symbol
                    or "USDC" in upper_symbol
                    or "USDT" in upper_symbol
                    or "WETH" in upper_symbol
                    or "BTC" in upper_symbol
                ):
                    continue

                # =========================================
                # NEW PAIR FILTER
                # =========================================

                pair_created = pair.get(
                    "pairCreatedAt",
                    0
                )

                if pair_created:

                    age_minutes = (
                        (
                            time.time() * 1000
                            - pair_created
                        ) / 60000
                    )

                    if age_minutes > 120:
                        continue

                # =========================================
                # DUPLICATE FILTER
                # =========================================

                last_alert = SENT_ALERTS.get(
                    pair_address,
                    0
                )

                if (
                    now - last_alert
                    < COOLDOWN_SECONDS
                ):
                    continue

                # =========================================
                # PRICE
                # =========================================

                price = pair.get(
                    "priceUsd",
                    "0"
                )

                # =========================================
                # LIQUIDITY
                # =========================================

                liquidity = float(
                    pair.get(
                        "liquidity",
                        {}
                    ).get(
                        "usd",
                        0
                    )
                )

                # =========================================
                # VOLUME
                # =========================================

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

                # =========================================
                # DEBUG VALUES
                # =========================================

                logging.info(
                    f"TOKEN {token_symbol} | "
                    f"Liq ${liquidity:.2f} | "
                    f"Vol ${volume:.2f}"
                )

                # =========================================
                # FILTERS
                # =========================================

                if liquidity < MIN_LIQUIDITY:
                    continue

                if volume < MIN_VOLUME:
                    continue

                # =========================================
                # ALERT
                # =========================================

                logging.info(
                    f"🚨 ALERT FOUND: "
                    f"{token_symbol}"
                )

                message = build_message(
                    token_name,
                    token_symbol,
                    liquidity,
                    volume,
                    price,
                    pair_address,
                    dex_url
                )

                success = send_telegram(
                    message
                )

                if success:

                    SENT_ALERTS[pair_address] = now

                    alerts_sent += 1

                    logging.info(
                        f"🎯 ALERT SENT: "
                        f"{token_symbol}"
                    )

                    time.sleep(2)

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

# =========================================
# LOOP
# =========================================

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

# =========================================
# MAIN
# =========================================

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
