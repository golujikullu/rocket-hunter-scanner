import os
import time
import requests
import logging
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

DEX_API = "https://api.dexscreener.com/latest/dex/pairs/solana"

# =========================
# SETTINGS
# =========================

SCAN_INTERVAL = 20

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

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        logging.error("❌ TELEGRAM_BOT_TOKEN missing")
        return

    if not TELEGRAM_CHAT_ID:
        logging.error("❌ TELEGRAM_CHAT_ID missing")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

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

        logging.info(f"📩 Telegram Status: {response.status_code}")

    except Exception as e:

        logging.error(f"❌ Telegram Error: {e}")

# =========================
# SCANNER
# =========================

def scan():

    global SENT_PAIRS

    logging.info("🔎 Scanning Solana pairs...")

    try:

        response = requests.get(
            DEX_API,
            timeout=15
        )

        logging.info(f"✅ API STATUS: {response.status_code}")

        if response.status_code != 200:
            return

        data = response.json()

        pairs = data.get("pairs", [])

        logging.info(f"📊 Pairs Found: {len(pairs)}")

        alerts_sent = 0

        now = time.time()

        for pair in pairs:

            try:

                chain = pair.get("chainId", "")

                if chain != "solana":
                    continue

                base = pair.get("baseToken", {})

                token_name = base.get("name", "").strip()

                token_symbol = base.get("symbol", "").strip()

                if not token_name:
                    continue

                if not token_symbol:
                    continue

                # skip major tokens

                if token_symbol.upper() in [
                    "SOL",
                    "USDC",
                    "USDT",
                    "BTC",
                    "ETH",
                    "WETH",
                    "WSOL"
                ]:
                    continue

                pair_address = pair.get("pairAddress", "")

                if not pair_address:
                    continue

                # duplicate cooldown

                last_seen = SENT_PAIRS.get(pair_address, 0)

                if now - last_seen < COOLDOWN_SECONDS:
                    continue

                liquidity = float(
                    pair.get("liquidity", {}).get("usd", 0)
                )

                volume = float(
                    pair.get("volume", {}).get("h24", 0)
                )

                logging.info(
                    f"🚀 {token_symbol} | "
                    f"Liq ${liquidity:.2f} | "
                    f"Vol ${volume:.2f}"
                )

                # filters

                if liquidity < MIN_LIQUIDITY:
                    continue

                if volume < MIN_VOLUME:
                    continue

                # mark as seen

                SENT_PAIRS[pair_address] = now

                # cleanup memory

                if len(SENT_PAIRS) > 1000:
                    SENT_PAIRS = {}

                dex_url = pair.get("url", "")

                message = f"""
🚀 ROCKET ALERT

💎 {token_name} ({token_symbol})

💧 Liquidity: ${liquidity:,.2f}

📊 Volume: ${volume:,.2f}

🔗 {dex_url}
"""

                send_telegram(message)

                logging.info(f"✅ ALERT SENT: {token_symbol}")

                alerts_sent += 1

                time.sleep(2)

                if alerts_sent >= 5:
                    break

            except Exception as pair_error:

                logging.error(f"❌ Pair Error: {pair_error}")

        logging.info(f"✅ Scan Complete | Alerts: {alerts_sent}")

    except Exception as e:

        logging.error(f"❌ Scan Error: {e}")

# =========================
# LOOP
# =========================

def scanner_loop():

    while True:

        scan()

        logging.info(f"⏳ Waiting {SCAN_INTERVAL} seconds...")

        time.sleep(SCAN_INTERVAL)

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    logging.info("🚀 Rocket Hunter Starting...")

    scanner_thread = Thread(
        target=scanner_loop,
        daemon=True
    )

    scanner_thread.start()

    port = int(os.getenv("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
