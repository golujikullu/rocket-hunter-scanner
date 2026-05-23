import os
import time
import requests
import logging
from threading import Thread
from flask import Flask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = Flask(__name__)

@app.route("/")
def home():
    return "Rocket Hunter LIVE 🚀"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# WORKING API
DEX_API = "https://api.dexscreener.com/latest/dex/search?q=SOL"

SCAN_INTERVAL = 20

MIN_LIQUIDITY = 500
MIN_VOLUME = 100

SEEN = {}

COOLDOWN = 7200

def send_telegram(msg):

    if not BOT_TOKEN or not CHAT_ID:
        logging.error("Telegram ENV missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": msg
    }

    try:

        r = requests.post(
            url,
            data=payload,
            timeout=10
        )

        logging.info(f"Telegram: {r.status_code}")

        return r.status_code == 200

    except Exception as e:

        logging.error(e)

        return False

def scan():

    logging.info("Scanning...")

    try:

        r = requests.get(
            DEX_API,
            timeout=15
        )

        logging.info(f"API STATUS: {r.status_code}")

        if r.status_code != 200:
            return

        data = r.json()

        pairs = data.get("pairs", [])

        logging.info(f"Pairs: {len(pairs)}")

        now = time.time()

        alerts = 0

        for pair in pairs:

            try:

                if pair.get("chainId") != "solana":
                    continue

                base = pair.get("baseToken", {})

                symbol = base.get("symbol", "")
                name = base.get("name", "")

                if not symbol or not name:
                    continue

                # skip big coins

                if symbol.upper() in [
                    "SOL",
                    "USDC",
                    "USDT",
                    "BTC",
                    "ETH",
                    "WSOL"
                ]:
                    continue

                liquidity = float(
                    pair.get("liquidity", {}).get("usd", 0)
                )

                volume = float(
                    pair.get("volume", {}).get("h24", 0)
                )

                logging.info(
                    f"{symbol} | "
                    f"Liq ${liquidity} | "
                    f"Vol ${volume}"
                )

                if liquidity < MIN_LIQUIDITY:
                    continue

                if volume < MIN_VOLUME:
                    continue

                pair_address = pair.get("pairAddress")

                if not pair_address:
                    continue

                last = SEEN.get(pair_address, 0)

                if now - last < COOLDOWN:
                    continue

                SEEN[pair_address] = now

                link = pair.get("url", "")

                msg = f"""
🚀 ROCKET ALERT

💎 {name} ({symbol})

💧 Liquidity: ${liquidity:,.2f}

📊 Volume: ${volume:,.2f}

🔗 {link}
"""

                ok = send_telegram(msg)

                if ok:

                    alerts += 1

                    logging.info(
                        f"ALERT SENT: {symbol}"
                    )

                time.sleep(2)

                if alerts >= 5:
                    break

            except Exception as pair_error:

                logging.error(pair_error)

        logging.info(f"Scan done | Alerts {alerts}")

    except Exception as e:

        logging.error(e)

def loop():

    while True:

        scan()

        logging.info(
            f"Waiting {SCAN_INTERVAL}s..."
        )

        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":

    t = Thread(
        target=loop,
        daemon=True
    )

    t.start()

    port = int(
        os.getenv("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
