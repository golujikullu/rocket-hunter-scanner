import os
import time
import requests
import logging
from threading import Thread
from flask import Flask

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DEX_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"

SENT_PAIRS = {}
COOLDOWN = 7200  # 2 hours


@app.route('/')
def home():
    return "🚀 Rocket Hunter LIVE", 200


def send_alert(symbol, name, liquidity, volume, pair_address, price_change):

    if liquidity > 50000 and volume > 20000:
        risk = "🟢 LOW RISK"
    elif liquidity > 10000:
        risk = "🟡 MEDIUM RISK"
    else:
        risk = "🔴 HIGH RISK"

    change_icon = "📈" if price_change >= 0 else "📉"

    clean_symbol = symbol.replace("<", "&lt;").replace(">", "&gt;")
    clean_name = name.replace("<", "&lt;").replace(">", "&gt;")

    message = (
        f"🚀 <b>Rocket Hunter Alert</b>\n\n"
        f"💎 <b>{clean_symbol}</b>\n"
        f"📛 {clean_name}\n\n"
        f"💧 Liquidity: ${liquidity:,.0f}\n"
        f"📊 Volume: ${volume:,.0f}\n"
        f"{change_icon} Change: {price_change:.1f}%\n\n"
        f"{risk}\n\n"
        f"📊 Dex:\n"
        f"https://dexscreener.com/solana/{pair_address}\n\n"
        f"🦎 Gecko:\n"
        f"https://www.geckoterminal.com/solana/pools/{pair_address}"
    )

    inline_keyboard = {
        "inline_keyboard": [[
            {
                "text": "📊 DexScreener",
                "url": f"https://dexscreener.com/solana/{pair_address}"
            },
            {
                "text": "🦎 GeckoTerminal",
                "url": f"https://www.geckoterminal.com/solana/pools/{pair_address}"
            }
        ]]
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard,
        "disable_web_page_preview": True
    }

    try:
        res = requests.post(url, json=payload, timeout=10)

        logging.info(f"Telegram Status: {res.status_code}")

        if res.status_code == 200:
            logging.info(f"✅ ALERT SENT: {symbol}")
            return True
        else:
            logging.error(f"Telegram Error: {res.text}")

    except Exception as e:
        logging.error(f"Telegram Exception: {e}")

    return False


def scanner():

    logging.info("🚀 Rocket Hunter Starting...")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ ENV VARIABLES MISSING!")
        return

    while True:

        try:

            now = time.time()

            # Cleanup old cooldown entries
            expired = [
                k for k, v in SENT_PAIRS.items()
                if now - v > COOLDOWN
            ]

            for k in expired:
                del SENT_PAIRS[k]

            # Memory safety
            if len(SENT_PAIRS) > 5000:
                SENT_PAIRS.clear()

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            res = requests.get(
                DEX_URL,
                headers=headers,
                timeout=15
            )

            logging.info(f"API STATUS: {res.status_code}")

            if res.status_code == 429:
                logging.warning("⚠️ Rate Limited. Waiting 90s...")
                time.sleep(90)
                continue

            if res.status_code != 200:
                time.sleep(30)
                continue

            pools = res.json().get("data", [])

            logging.info(f"📊 Pools Found: {len(pools)}")

            alerts = 0

            for pool in pools:

                try:

                    attr = pool.get("attributes", {})

                    pair_address = attr.get("address")

                    if not pair_address:
                        continue

                    if pair_address in SENT_PAIRS:
                        continue

                    pool_name = attr.get("name", "")

                    parts = pool_name.replace(" / ", "/").split("/")

                    symbol = (
                        parts[0].strip().upper()
                        if len(parts) > 0
                        else "UNKNOWN"
                    )

                    raw_name = (
                        parts[1].strip()
                        if len(parts) > 1
                        else "SOL"
                    )

                    if len(symbol) > 15:
                        symbol = symbol[:15]

                    if symbol.lower() in [
                        "sol",
                        "wsol",
                        "usdc",
                        "usdt"
                    ]:
                        continue

                    name = pool_name if pool_name else "Unknown"

                    liquidity = float(
                        attr.get("reserve_in_usd") or 0
                    )

                    vol_data = attr.get("volume_usd", {})

                    volume = float(
                        vol_data.get("h24") or 0
                    )

                    if volume == 0:
                        volume = float(
                            vol_data.get("h1") or 0
                        ) * 24

                    if volume == 0:
                        volume = float(
                            vol_data.get("m5") or 0
                        ) * 288

                    change_data = attr.get(
                        "price_change_percentage",
                        {}
                    )

                    price_change = float(
                        change_data.get("h24")
                        or change_data.get("h1")
                        or change_data.get("m5")
                        or 0
                    )

                    logging.info(
                        f"💎 {symbol} | "
                        f"Liq ${liquidity:,.0f} | "
                        f"Vol ${volume:,.0f}"
                    )

                    # FINAL FILTERS
                    if liquidity < 7000:
                        continue

                    if liquidity > 5000000:
                        continue

                    if volume < 1000:
                        continue

                    success = send_alert(
                        symbol,
                        name,
                        liquidity,
                        volume,
                        pair_address,
                        price_change
                    )

                    if success:
                        SENT_PAIRS[pair_address] = now
                        alerts += 1

                        time.sleep(3)

                    if alerts >= 5:
                        break

                except Exception as e:
                    logging.error(f"Pool Error: {e}")

            logging.info(f"✅ Scan Complete | Alerts: {alerts}")

        except Exception as e:
            logging.error(f"Scanner Error: {e}")

        logging.info("⏳ Waiting 60s...")
        time.sleep(60)


if __name__ == "__main__":

    t = Thread(target=scanner, daemon=True)
    t.start()

    port = int(os.getenv("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
