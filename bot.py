import requests
import time
import threading
from flask import Flask
import os

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

seen_tokens = {}

COOLDOWN_SECONDS = 7200

# =========================
# TELEGRAM
# =========================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT TOKEN OR CHAT ID MISSING", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        print(
            f"📩 TELEGRAM STATUS: {response.status_code}",
            flush=True
        )

    except Exception as e:

        print(
            "❌ TELEGRAM ERROR:",
            e,
            flush=True
        )

# =========================
# SCANNER
# =========================

def scan_tokens():

    print("🔍 SCANNING TOKENS...", flush=True)

    try:

        url = "https://api.dexscreener.com/token-profiles/latest/v1"

        response = requests.get(
            url,
            timeout=15
        )

        print(
            f"✅ API STATUS: {response.status_code}",
            flush=True
        )

        if response.status_code != 200:
            return

        data = response.json()

        tokens = data if isinstance(data, list) else []

        print(
            f"📊 TOKENS FOUND: {len(tokens)}",
            flush=True
        )

        now = time.time()

        alert_count = 0

        for token in tokens:

            try:

                chain_id = str(
                    token.get("chainId", "")
                ).lower()

                if chain_id != "solana":
                    continue

                # CLEAN TOKEN NAME
                token_name = str(
                    token.get("description", "New Token")
                )

                # REMOVE LONG TEXT
                token_name = token_name.split(".")[0]

                # LIMIT SIZE
                token_name = token_name[:60]

                # SKIP IMAGE URL
                if (
                    "http" in token_name
                    or "cdn.dexscreener"
                    in token_name
                ):
                    continue

                token_id = (
                    token.get("tokenAddress")
                    or token.get("url")
                )

                if not token_id:
                    continue

                # DUPLICATE FILTER
                last_seen = seen_tokens.get(
                    token_id,
                    0
                )

                if now - last_seen < COOLDOWN_SECONDS:
                    continue

                seen_tokens[token_id] = now

                pair_url = token.get(
                    "url",
                    "https://dexscreener.com"
                )

                message = (
                    f"🚀 Rocket Hunter Alert\n\n"
                    f"💎 {token_name}\n\n"
                    f"⛓ Chain: Solana\n\n"
                    f"🔗 {pair_url}"
                )

                print(
                    f"🚨 ALERT: {token_name}",
                    flush=True
                )

                send_telegram(message)

                alert_count += 1

                time.sleep(2)

                if alert_count >= 5:
                    break

            except Exception as e:

                print(
                    "PAIR ERROR:",
                    e,
                    flush=True
                )

        print(
            f"✅ Scan Complete. Alerts Sent: {alert_count}",
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
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
