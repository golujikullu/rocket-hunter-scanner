import os
import time
import requests
import logging
from threading import Thread
from flask import Flask
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DEX_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"

# =========================
# ROCKET HUNTER CACHE
# =========================
SENT_TOKENS = {}

# 1 hour cooldown
COOLDOWN = 3600


@app.route('/')
def home():
    return "🚀 Rocket Hunter LIVE", 200


# =========================
# ENTRY LABELS
# =========================
def get_entry_label(age_hours):

    if age_hours <= 1:
        return "⚡ ULTRA EARLY"

    elif age_hours <= 6:
        return "🟢 EARLY"

    elif age_hours <= 24:
        return "🟡 LATE ENTRY"

    return None


# =========================
# TELEGRAM ALERT
# =========================
def send_alert(
    symbol,
    liquidity,
    volume,
    pair_address,
    price_change,
    entry_label
):

    # Risk Engine
    if liquidity > 50000 and volume > 20000:
        risk = "🛡️ LOW RISK"

    elif liquidity > 10000:
        risk = "⚠️ MEDIUM RISK"

    else:
        risk = "🔴 HIGH RISK"

    change_icon = "📈" if price_change >= 0 else "📉"

    clean_symbol = (
        symbol
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    message = (
        f"🚀 <b>Rocket Hunter Alert</b>\n\n"

        f"⚡ {entry_label}\n\n"

        f"💎 <b>{clean_symbol} / SOL</b>\n\n"

        f"💧 Liquidity: ${liquidity:,.0f}\n"
        f"📊 Volume: ${volume:,.0f}\n"
        f"{change_icon} Change: {price_change:.1f}%\n\n"

        f"{risk}"
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

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
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

        if res.status_code == 200:
            logging.info(
                f"✅ ALERT SENT: {symbol} | {entry_label}"
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


# =========================
# MAIN SCANNER
# =========================
def scanner():

    logging.info("🚀 Rocket Hunter Starting...")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ ENV VARIABLES MISSING!")
        return

    while True:

        try:

            now = time.time()

            now_utc = datetime.now(timezone.utc)

            # =========================
            # CLEAN EXPIRED CACHE
            # =========================
            expired = [
                k for k, v in SENT_TOKENS.items()
                if now - v > COOLDOWN
            ]

            for k in expired:
                del SENT_TOKENS[k]

            # =========================
            # MEMORY SAFETY
            # =========================
            if len(SENT_TOKENS) > 5000:
                SENT_TOKENS.clear()
                logging.info("🧹 Cache flushed")

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            res = requests.get(
                DEX_URL,
                headers=headers,
                timeout=15
            )

            logging.info(
                f"📡 API STATUS: {res.status_code}"
            )

            # =========================
            # RATE LIMIT
            # =========================
            if res.status_code == 429:

                logging.warning(
                    "⚠️ Rate limited! Waiting 90s..."
                )

                time.sleep(90)
                continue

            elif res.status_code != 200:

                logging.warning(
                    "⚠️ API Error! Waiting 30s..."
                )

                time.sleep(30)
                continue

            pools = res.json().get("data", [])

            logging.info(
                f"📊 Pools Found: {len(pools)}"
            )

            alerts = 0

            for pool in pools:

                try:

                    attr = pool.get("attributes", {})

                    pair_address = attr.get("address")

                    if not pair_address:
                        continue

                    # =========================
                    # POOL AGE
                    # =========================
                    created_at = attr.get(
                        "pool_created_at",
                        ""
                    )

                    if not created_at:
                        continue

                    pool_time = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )

                    age_hours = (
                        now_utc - pool_time
                    ).total_seconds() / 3600

                    entry_label = get_entry_label(age_hours)

                    if entry_label is None:
                        continue

                    # =========================
                    # SYMBOL
                    # =========================
                    pool_name = attr.get("name", "")

                    if " / " in pool_name:
                        symbol = (
                            pool_name
                            .split(" / ")[0]
                            .strip()
                        )

                    elif "/" in pool_name:
                        symbol = (
                            pool_name
                            .split("/")[0]
                            .strip()
                        )

                    else:
                        symbol = (
                            pool_name[:12]
                            if pool_name
                            else "Unknown"
                        )

                    if symbol.lower() in [
                        "sol",
                        "wsol",
                        "usdc",
                        "usdt",
                        "unknown"
                    ]:
                        continue

                    # =========================
                    # DUPLICATE SHIELD
                    # =========================

                    # Strong symbol lock
                    token_key = symbol.upper()

                    last_sent = SENT_TOKENS.get(
                        token_key,
                        0
                    )

                    if now - last_sent < COOLDOWN:

                        logging.info(
                            f"⏭️ Duplicate skipped: {symbol}"
                        )

                        continue

                    # =========================
                    # LIQUIDITY
                    # =========================
                    liquidity = float(
                        attr.get("reserve_in_usd") or 0
                    )

                    # =========================
                    # VOLUME
                    # =========================
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

                    # =========================
                    # PRICE CHANGE
                    # =========================
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
                        f"Age:{age_hours:.1f}h | "
                        f"Liq:${liquidity:,.0f} | "
                        f"Vol:${volume:,.0f}"
                    )

                    # =========================
                    # FILTERS
                    # =========================
                    if liquidity < 5000:
                        continue

                    if volume < 3000:
                        continue

                    # =========================
                    # SEND ALERT
                    # =========================
                    success = send_alert(
                        symbol,
                        liquidity,
                        volume,
                        pair_address,
                        price_change,
                        entry_label
                    )

                    if success:

                        SENT_TOKENS[token_key] = now

                        alerts += 1

                        time.sleep(3)

                    # Limit alerts per cycle
                    if alerts >= 3:
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

        logging.info("⏳ Waiting 60s...")

        time.sleep(60)


# =========================
# START ENGINE
# =========================
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
