import os
import time
import requests
import logging
from threading import Thread
from flask import Flask

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 Rocket Hunter LIVE", 200

# =========================================================
# ENV VARIABLES
# =========================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================================================
# API
# =========================================================

DEX_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"

# =========================================================
# MEMORY / DUPLICATE PROTECTION
# =========================================================

SENT_PAIRS = {}

COOLDOWN = 7200  # 2 HOURS

# =========================================================
# SCAM FILTER
# =========================================================

BAD_WORDS = [
    "SPERM",
    "SEX",
    "PORN",
    "XXX",
    "TEST",
    "SCAM",
    "RUG",
    "BANK"
]

# =========================================================
# TELEGRAM ALERT
# =========================================================

def send_alert(
    symbol,
    name,
    liquidity,
    volume,
    pair_address,
    price_change
):

    # =========================
    # RISK LEVEL
    # =========================

    if liquidity > 50000 and volume > 20000:
        risk = "🟢 LOW RISK"

    elif liquidity > 15000:
        risk = "🟡 MEDIUM RISK"

    else:
        risk = "🔴 HIGH RISK"

    # =========================
    # PRICE CHANGE ICON
    # =========================

    change_icon = "📈" if price_change >= 0 else "📉"

    # =========================
    # CLEAN HTML
    # =========================

    clean_symbol = symbol.replace("<", "").replace(">", "")
    clean_name = name.replace("<", "").replace(">", "")

    # =========================
    # MESSAGE
    # =========================

    message = (
        f"🚀 <b>Rocket Hunter Alert</b>\n\n"

        f"💎 <b>{clean_symbol}</b>\n"
        f"🪙 {clean_name}\n\n"

        f"💧 Liquidity: <b>${liquidity:,.0f}</b>\n"
        f"📊 Volume 24h: <b>${volume:,.0f}</b>\n"
        f"{change_icon} Change: <b>{price_change:.1f}%</b>\n\n"

        f"{risk}"
    )

    # =========================
    # BUTTONS
    # =========================

    keyboard = {
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

    # =========================
    # TELEGRAM API
    # =========================

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
        "disable_web_page_preview": True
    }

    try:

        res = requests.post(
            url,
            json=payload,
            timeout=15
        )

        logging.info(f"Telegram Status: {res.status_code}")

        if res.status_code == 200:
            logging.info(f"✅ ALERT SENT: {symbol}")
            return True

        else:
            logging.error(res.text)

    except Exception as e:
        logging.error(f"Telegram Error: {e}")

    return False

# =========================================================
# MAIN SCANNER
# =========================================================

def scanner():

    logging.info("🚀 Rocket Hunter Started")

    # =========================
    # ENV CHECK
    # =========================

    if not TELEGRAM_BOT_TOKEN:
        logging.error("❌ TELEGRAM_BOT_TOKEN missing")
        return

    if not TELEGRAM_CHAT_ID:
        logging.error("❌ TELEGRAM_CHAT_ID missing")
        return

    # =========================
    # LOOP
    # =========================

    while True:

        try:

            now = time.time()

            # =====================================
            # CLEAN OLD CACHE
            # =====================================

            expired = []

            for pair, ts in SENT_PAIRS.items():

                if now - ts > COOLDOWN:
                    expired.append(pair)

            for pair in expired:
                del SENT_PAIRS[pair]

            # =====================================
            # API REQUEST
            # =====================================

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.get(
                DEX_URL,
                headers=headers,
                timeout=20
            )

            logging.info(f"API STATUS: {response.status_code}")

            # =====================================
            # RATE LIMIT
            # =====================================

            if response.status_code == 429:

                logging.warning("⚠️ RATE LIMITED")

                time.sleep(90)

                continue

            # =====================================
            # BAD RESPONSE
            # =====================================

            if response.status_code != 200:

                logging.warning("❌ BAD API RESPONSE")

                time.sleep(30)

                continue

            # =====================================
            # JSON
            # =====================================

            data = response.json()

            pools = data.get("data", [])

            logging.info(f"📊 Pools Found: {len(pools)}")

            alerts = 0

            # =====================================
            # LOOP POOLS
            # =====================================

            for pool in pools:

                try:

                    attr = pool.get("attributes", {})

                    pair_address = attr.get("address")

                    # =================================
                    # DUPLICATE PROTECTION
                    # =================================

                    if not pair_address:
                        continue

                    if pair_address in SENT_PAIRS:
                        continue

                    # =================================
                    # NAME
                    # =================================

                    pool_name = attr.get("name", "")

                    if " / " in pool_name:

                        symbol = pool_name.split(" / ")[0].strip()
                        base = pool_name.split(" / ")[1].strip()

                    elif "/" in pool_name:

                        symbol = pool_name.split("/")[0].strip()
                        base = pool_name.split("/")[1].strip()

                    else:

                        symbol = pool_name[:12]
                        base = "SOL"

                    # =================================
                    # EMPTY FIX
                    # =================================

                    if not symbol:
                        symbol = "UNKNOWN"

                    # =================================
                    # SKIP BASE TOKENS
                    # =================================

                    if symbol.lower() in [
                        "sol",
                        "wsol",
                        "usdc",
                        "usdt"
                    ]:
                        continue

                    # =================================
                    # SCAM FILTER
                    # =================================

                    if any(
                        word in symbol.upper()
                        for word in BAD_WORDS
                    ):
                        continue

                    # =================================
                    # METRICS
                    # =================================

                    liquidity = float(
                        attr.get("reserve_in_usd") or 0
                    )

                    volume_data = attr.get("volume_usd", {})

                    volume = float(
                        volume_data.get("h24") or 0
                    )

                    if volume == 0:
                        volume = float(
                            volume_data.get("h1") or 0
                        ) * 24

                    if volume == 0:
                        volume = float(
                            volume_data.get("m5") or 0
                        ) * 288

                    # =================================
                    # PRICE CHANGE
                    # =================================

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

                    # =================================
                    # LOG
                    # =================================

                    logging.info(
                        f"💎 {symbol} | "
                        f"Liq ${liquidity:,.0f} | "
                        f"Vol ${volume:,.0f}"
                    )

                    # =================================
                    # FILTERS
                    # =================================

                    if liquidity < 10000:
                        continue

                    if volume < 5000:
                        continue

                    # =================================
                    # SEND ALERT
                    # =================================

                    success = send_alert(
                        symbol=symbol,
                        name=pool_name,
                        liquidity=liquidity,
                        volume=volume,
                        pair_address=pair_address,
                        price_change=price_change
                    )

                    # =================================
                    # SAVE CACHE
                    # =================================

                    if success:

                        SENT_PAIRS[pair_address] = now

                        alerts += 1

                        time.sleep(3)

                    # =================================
                    # ALERT LIMIT
                    # =================================

                    if alerts >= 5:
                        break

                except Exception as e:

                    logging.error(f"Pool Error: {e}")

            logging.info(f"✅ Scan Complete | Alerts: {alerts}")

        except Exception as e:

            logging.error(f"Scanner Error: {e}")

        logging.info("⏳ Waiting 60 seconds...")

        time.sleep(60)

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    t = Thread(
        target=scanner,
        daemon=True
    )

    t.start()

    port = int(os.getenv("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
