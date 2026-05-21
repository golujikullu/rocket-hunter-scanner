import os
from flask import Flask
import requests
import threading
import time

# =========================================
# ROCKET HUNTER V2 FOUNDATION
# =========================================

# Telegram ENV variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# Core Filters
ALLOWED_CHAIN = "solana"
MIN_LIQUIDITY_USD = 10000

# Correct DexScreener API Endpoint
DEX_API_URL = "https://api.dexscreener.com/latest/dex/search/?q=solana"

# Flask App Setup
app = Flask(__name__)

# Render Health Endpoint
@app.route('/')
def health_check():
    return "Rocket Hunter V2 Core Engine is Awake 24/7! 🚀", 200

# Duplicate suppression memory
sent_tokens = set()

# =========================================
# TELEGRAM ALERT SYSTEM
# =========================================

def send_telegram(pair):

    name = pair.get("baseToken", {}).get("name", "Unknown")
    symbol = pair.get("baseToken", {}).get("symbol", "XYZ")

    liquidity = float(
        pair.get("liquidity", {}).get("usd", 0)
    )

    volume = float(
        pair.get("volume", {}).get("h24", 0)
    )

    price = pair.get("priceUsd", "0")

    dex_url = pair.get("url", "")

    # Mobile-first clean alert
    message = (
        f"🚀 *Rocket Hunter Alert*\n\n"

        f"🪙 *Token:* {name} ({symbol})\n"
        f"💵 *Price:* ${price}\n"
        f"💧 *Liquidity:* ${liquidity:,.0f}\n"
        f"📈 *24H Volume:* ${volume:,.0f}\n\n"

        f"🛡 *Safety:* ⚠️ UNVERIFIED\n"
        f"✅ *Chain:* Solana Only\n\n"

        f"🔗 *DexScreener:*\n{dex_url}"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            url,
            json=payload
        )

        if response.status_code == 200:
            print(f"[ALERT SENT] {symbol}")

        else:
            print("Telegram API Error:", response.text)

    except Exception as e:

        print("Telegram Error:", e)

# =========================================
# HARD FILTER LAYER
# =========================================

def passes_filters(pair):

    # Solana-only filter
    if pair.get("chainId") != ALLOWED_CHAIN:
        return False

    # Liquidity filter
    liquidity = pair.get(
        "liquidity",
        {}
    ).get("usd", 0)

    if float(liquidity) < MIN_LIQUIDITY_USD:
        return False

    return True

# =========================================
# MAIN SCANNER LOOP
# =========================================

def scan_trending():

    while True:

        try:

            response = requests.get(
                DEX_API_URL,
                timeout=15
            )

            if response.status_code != 200:

                print(
                    "Dex API Error:",
                    response.status_code
                )

                time.sleep(60)
                continue

            data = response.json()

            pairs = data.get("pairs", [])

            print(f"Found {len(pairs)} pairs")

            for pair in pairs[:10]:

                token_address = pair.get(
                    "baseToken",
                    {}
                ).get("address")

                if not token_address:
                    continue

                # Duplicate suppression
                if token_address in sent_tokens:
                    continue

                # Hard filter gate
                if not passes_filters(pair):
                    continue

                # Send alert
                send_telegram(pair)

                # Save memory
                sent_tokens.add(token_address)

            # Scan every 5 min
            time.sleep(300)

        except Exception as e:

            print("Scanner Loop Error:", e)

            time.sleep(60)

# =========================================
# START BACKGROUND SCANNER
# =========================================

scanner_thread = threading.Thread(
    target=scan_trending
)

scanner_thread.daemon = True

scanner_thread.start()

# =========================================
# START FLASK SERVER
# =========================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host='0.0.0.0',
        port=port
    )
