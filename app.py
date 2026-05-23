import os
import time
import requests
import logging
from threading import Thread
from flask import Flask

# ============================================
# LOGGING
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ============================================
# FLASK
# ============================================

app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 Rocket Hunter LIVE", 200

# ============================================
# ENV VARIABLES
# ============================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ============================================
# API
# ============================================

DEX_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"

# ============================================
# CACHE
# ============================================

SENT_PAIRS = {}

COOLDOWN = 7200  # 2 HOURS

# ============================================
# TELEGRAM ALERT
# ============================================

def send_alert(
    symbol,
    name,
    liquidity,
    volume,
    pair_address,
    price_change
):

    # RISK ENGINE

    if liquidity > 50000 and volume > 20000:
        risk = "🟢 LOW RISK"

    elif liquidity > 10000:
        risk = "🟡 MEDIUM RISK"

    else:
        risk = "🔴 HIGH RISK"

    # PRICE CHANGE ICON

    change_icon = "📈" if price_change >= 0 else "📉"

    # CLEAN HTML

    clean_symbol = (
        symbol.replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    clean_name = (
        name.replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    # MESSAGE

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

    # BUTTONS

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

    # TELEGRAM URL

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard,
        "disable_web_page_preview": True
    }

    try:

        res = requests.post(
            url,
            json=payload,
            timeout=10
        )

        logging.info(
            f"Telegram Status: {res.status_code}"
        )

        if res.status_code == 200:

            logging.info(
                f"✅ ALERT SENT: {symbol}"
            )

            return True

        else:

            logging.error(
                f"Telegram Error: {res.text}"
            )

    except Exception as e:

        logging.error(
            f"Telegram Exception: {e}"
        )

    return False

# ============================================
# SCANNER
# ============================================

def scanner():

    logging.info(
        "🚀 Rocket Hunter Starting..."
    )

    # ENV CHECK

    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        logging.error(
            "❌ ENV VARIABLES MISSING!"
        )
        return

    while True:

        try:

            now = time.time()

            # ====================================
            # CLEAN OLD CACHE
            # ====================================

            expired = [

                k

                for k, v in SENT_PAIRS.items()

                if now - v > COOLDOWN
            ]

            for k in expired:
                del SENT_PAIRS[k]

            # MEMORY SAFETY

            if len(SENT_PAIRS) > 5000:
                SENT_PAIRS.clear()

            # ====================================
            # API CALL
            # ====================================

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            res = requests.get(
                DEX_URL,
                headers=headers,
                timeout=15
            )

            logging.info(
                f"API STATUS: {res.status_code}"
            )

            # RATE LIMIT

            if res.status_code == 429:

                logging.warning(
                    "⚠️ Rate Limited. Waiting 90s..."
                )

                time.sleep(90)

                continue

            # BAD RESPONSE

            if res.status_code != 200:

                time.sleep(30)

                continue

            # JSON

            pools = res.json().get("data", [])

            logging.info(
                f"📊 Pools Found: {len(pools)}"
            )

            alerts = 0

            # ====================================
            # LOOP POOLS
            # ====================================

            for pool in pools:

                try:

                    attr = pool.get(
                        "attributes",
                        {}
                    )

                    pair_address = attr.get(
                        "address"
                    )

                    # SKIP EMPTY

                    if not pair_address:
                        continue

                    # DUPLICATE BLOCK

                    if pair_address in SENT_PAIRS:
                        continue

                    # ====================================
                    # NAME + SYMBOL FIX
                    # ====================================

                    pool_name = attr.get(
                        "name",
                        ""
                    )

                    parts = (
                        pool_name
                        .replace(" / ", "/")
                        .split("/")
                    )

                    symbol = "UNKNOWN"

                    if len(parts) > 0:

                        symbol = (
                            parts[0]
                            .strip()
                            .upper()
                        )

                    if (
                        not symbol
                        or symbol == "UNKNOWN"
                    ):

                        symbol = attr.get(
                            "symbol",
                            "UNKNOWN"
                        )

                    if not symbol:
                        symbol = "UNKNOWN"

                    if len(symbol) > 15:
                        symbol = symbol[:15]

                    # BASE COINS SKIP

                    if symbol.lower() in [

                        "sol",
                        "wsol",
                        "usdc",
                        "usdt"

                    ]:
                        continue

                    # NAME

                    name = (
                        pool_name
                        if pool_name
                        else "Unknown"
                    )

                    # ====================================
                    # LIQUIDITY
                    # ====================================

                    liquidity = float(
                        attr.get(
                            "reserve_in_usd"
                        ) or 0
                    )

                    # ====================================
                    # VOLUME
                    # ====================================

                    vol_data = attr.get(
                        "volume_usd",
                        {}
                    )

                    volume = float(
                        vol_data.get("h24") or 0
                    )

                    if volume == 0:

                        volume = (
                            float(
                                vol_data.get("h1") or 0
                            ) * 24
                        )

                    if volume == 0:

                        volume = (
                            float(
                                vol_data.get("m5") or 0
                            ) * 288
                        )

                    # ====================================
                    # PRICE CHANGE
                    # ====================================

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

                    # ====================================
                    # LOGS
                    # ====================================

                    logging.info(
                        f"💎 {symbol} | "
                        f"Liq ${liquidity:,.0f} | "
                        f"Vol ${volume:,.0f}"
                    )

                    # ====================================
                    # FINAL FILTERS
                    # ====================================

                    if liquidity < 7000:
                        continue

                    if liquidity > 5000000:
                        continue

                    if volume < 1000:
                        continue

                    # ====================================
                    # SEND ALERT
                    # ====================================

                    success = send_alert(

                        symbol,
                        name,
                        liquidity,
                        volume,
                        pair_address,
                        price_change
                    )

                    # ====================================
                    # SUCCESS
                    # ====================================

                    if success:

                        SENT_PAIRS[
                            pair_address
                        ] = now

                        alerts += 1

                        time.sleep(3)

                    # LIMIT ALERTS

                    if alerts >= 5:
                        break

                except Exception as e:

                    logging.error(
                        f"Pool Error: {e}"
                    )

            logging.info(
                f"✅ Scan Complete | Alerts: {alerts}"
            )

        except Exception as e:

            logging.error(
                f"Scanner Error: {e}"
            )

        logging.info(
            "⏳ Waiting 60s..."
        )

        time.sleep(60)

# ============================================
# START
# ============================================

if __name__ == "__main__":

    t = Thread(
        target=scanner,
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
