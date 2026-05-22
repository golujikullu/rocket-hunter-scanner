import requests
import time
import threading
from flask import Flask
import os

app = Flask(__name__)

# =========================
# TELEGRAM CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# DUPLICATE FILTER
# same token 2 ghante baad hi repeat hoga
# =========================

seen_tokens = {}   # {token_id: timestamp}
COOLDOWN_SECONDS = 7200   # 2 hours

# =========================
# TELEGRAM FUNCTION
# =========================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT TOKEN OR CHAT ID MISSING", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        print(
            "📩 TELEGRAM RESPONSE:",
            response.text,
            flush=True
        )

    except Exception as e:

        print(
            "❌ TELEGRAM ERROR:",
            e,
            flush=True
        )

# =========================
# TOKEN SCANNER
# =========================

def scan_tokens():

    print("🔍 SCANNING TOKENS...", flush=True)

    try:

        # CORRECT API URL
        url = "https://api.dexscreener.com/latest/dex/search?q=solana"

        response = requests.get(
            url,
            timeout=10
        )

        print(
            f"✅ API STATUS: {response.status_code}",
            flush=True
        )

        if response.status_code != 200:
            return

        data = response.json()

        pairs = data.get("pairs", [])

        # ONLY SOLANA PAIRS
        solana_pairs = [
            p for p in pairs
            if p.get("chainId") == "solana"
        ]

        print(
            f"📊 Solana pairs found: {len(solana_pairs)}",
            flush=True
        )

        now = time.time()

        alert_count = 0

        for pair in solana_pairs:

            try:

                base = pair.get("baseToken", {})

                token_name = base.get(
                    "name",
                    "Unknown"
                )

                token_symbol = base.get(
                    "symbol",
                    "???"
                )

                # TRACK TOKEN MINT ADDRESS
                token_id = base.get("address")

                if not token_id:
                    continue

                # SKIP BASE TOKENS
                if token_symbol.upper() in [
                    "SOL",
                    "WSOL",
                    "USDC",
                    "USDT"
                ]:
                    continue

                # =========================
                # DATA
                # =========================

                liquidity = float(
                    pair.get(
                        "liquidity",
                        {}
                    ).get("usd") or 0
                )

                volume = float(
                    pair.get(
                        "volume",
                        {}
                    ).get("h24") or 0
                )

                # =========================
                # FILTERS
                # =========================

                if liquidity < 1000:
                    continue

                if volume < 500:
                    continue

                # =========================
                # DUPLICATE COOLDOWN
                # =========================

                last_seen = seen_tokens.get(
                    token_id,
                    0
                )

                if now - last_seen < COOLDOWN_SECONDS:
                    continue

                # UPDATE TIMESTAMP
                seen_tokens[token_id] = now

                # =========================
                # EXTRA DATA
                # =========================

                price = pair.get(
                    "priceUsd",
                    "N/A"
                )

                price_change = float(
                    pair.get(
                        "priceChange",
                        {}
                    ).get("h24") or 0
                )

                pair_url = pair.get(
                    "url",
                    "https://dexscreener.com"
                )

                # =========================
                # FORMAT
                # =========================

                liq_str = f"${int(liquidity):,}"

                vol_str = f"${int(volume):,}"

                change_icon = (
                    "📈"
                    if price_change > 0
                    else "📉"
                )

                # =========================
                # MESSAGE
                # =========================

                message = f"""
🚀 <b>Rocket Hunter Alert</b>

💎 <b>{token_name} ({token_symbol})</b>

💰 Price: ${price}

💧 Liquidity: {liq_str}

📊 Volume 24H: {vol_str}

{change_icon} 24H Change: {price_change}%

⛓ Chain: Solana

🔗 <a href="{pair_url}">DexScreener</a>
"""

                print(
                    f"🚨 Alert: {token_name} ({token_symbol})",
                    flush=True
                )

                send_telegram(message)

                alert_count += 1

                time.sleep(2)

                # MAX 5 ALERTS
                if alert_count >= 5:
                    break

            except Exception as e:

                print(
                    "PAIR ERROR:",
                    e,
                    flush=True
                )

        print(
            f"✅ Scan complete. Alerts sent: {alert_count}",
            flush=True
        )

    except Exception as e:

        print(
            "❌ SCAN ERROR:",
            e,
            flush=True
        )

# =========================
# LOOP
# =========================

def scan_loop():

    while True:

        scan_tokens()

        print(
            "[WAITING 120 SECONDS]",
            flush=True
        )

        time.sleep(120)

# =========================
# FLASK
# =========================

@app.route("/")
def home():

    return "Rocket Hunter Live 🚀"

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    print(
        "🚀 ROCKET HUNTER STARTING...",
        flush=True
    )

    scanner_worker = threading.Thread(
        target=scan_loop
    )

    scanner_worker.daemon = True

    scanner_worker.start()

    print(
        "✅ SCAN THREAD STARTED",
        flush=True
    )

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
