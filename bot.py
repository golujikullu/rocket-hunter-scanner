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
# DEXSCREENER API
# =========================

DEX_URL = "https://api.dexscreener.com/latest/dex/search?q=solana"

# =========================
# DUPLICATE FILTER
# =========================

seen_tokens = set()

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
        "parse_mode": "HTML"
    }

    try:

        response = requests.post(url, data=payload)

        print("📩 TELEGRAM RESPONSE:", response.text, flush=True)

    except Exception as e:

        print("❌ TELEGRAM ERROR:", e, flush=True)

# =========================
# TOKEN SCANNER
# =========================

def scan_tokens():

    print("🔍 SCANNING TOKENS...", flush=True)

    try:

        response = requests.get(DEX_URL, timeout=10)

        print(f"✅ API STATUS: {response.status_code}", flush=True)

        if response.status_code != 200:
            return

        data = response.json()

        pairs = data.get("pairs", [])

        # ONLY SOLANA PAIRS
        solana_pairs = [
            p for p in pairs
            if p.get("chainId") == "solana"
        ]

        print(f"📊 Solana pairs found: {len(solana_pairs)}", flush=True)

        alert_count = 0

        for pair in solana_pairs[:20]:

            try:

                token_name = pair["baseToken"]["name"]
                token_symbol = pair["baseToken"]["symbol"]

                # SKIP NATIVE SOL
                if token_symbol.upper() == "SOL":
                    continue

                token_id = pair["pairAddress"]

                # DUPLICATE FILTER
                if token_id in seen_tokens:
                    continue

                seen_tokens.add(token_id)

                price = pair.get("priceUsd", "N/A")

                liquidity = pair.get("liquidity", {}).get("usd", 0)

                volume = pair.get("volume", {}).get("h24", 0)

                price_change = pair.get("priceChange", {}).get("h24", 0)

                # MINIMUM LIQUIDITY
                if liquidity < 5000:
                    print(f"⏭️ Skipped low liquidity: {token_name}", flush=True)
                    continue

                liq_str = f"${int(liquidity):,}"
                vol_str = f"${int(volume):,}"

                change_icon = "📈" if float(price_change or 0) > 0 else "📉"

                message = f"""
🚀 <b>Rocket Hunter Alert</b>

💎 <b>{token_name} ({token_symbol})</b>

💰 Price: ${price}
💧 Liquidity: {liq_str}
📊 Volume 24H: {vol_str}
{change_icon} 24H Change: {price_change}%

🔗 Chain: Solana
"""

                print(f"🚨 Alert: {token_name} ({token_symbol})", flush=True)

                send_telegram(message)

                alert_count += 1

                time.sleep(2)

                # MAX 5 ALERTS
                if alert_count >= 5:
                    break

            except Exception as e:

                print("PAIR ERROR:", e, flush=True)

        print(f"✅ Scan complete. Alerts sent: {alert_count}", flush=True)

    except Exception as e:

        print("❌ SCAN ERROR:", e, flush=True)

# =========================
# LOOP
# =========================

def scan_loop():

    while True:

        scan_tokens()

        print("[WAITING 120 SECONDS]", flush=True)

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

    print("🚀 ROCKET HUNTER STARTING...", flush=True)

    scanner_worker = threading.Thread(target=scan_loop)

    scanner_worker.daemon = True

    scanner_worker.start()

    print("✅ SCAN THREAD STARTED", flush=True)

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
