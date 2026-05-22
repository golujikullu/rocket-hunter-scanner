import os
import json
import time
import threading
import requests
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# ENV VARIABLES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "7200"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "120"))
MAX_ALERTS_PER_SCAN = int(os.getenv("MAX_ALERTS_PER_SCAN", "5"))

SEEN_FILE = "/tmp/seen_tokens.json"

# =========================
# MEMORY
# =========================
seen_tokens = {}

# =========================
# FILTERS
# =========================
BAD_WORDS = {
    "usdc",
    "creator",
    "official",
    "website",
    "telegram",
    "twitter",
    "pumpfun",
    "airdrop",
    "follow",
    "join",
}

BASE_TICKERS = {
    "SOL",
    "WSOL",
    "USDC",
    "USDT",
}

# =========================
# REQUEST SESSION
# =========================
session = requests.Session()

session.headers.update({
    "User-Agent": "RocketHunter/2.0"
})

# =========================
# LOAD SAVED TOKENS
# =========================
def load_seen():
    global seen_tokens

    try:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, "r") as f:
                seen_tokens = json.load(f)

            print(f"✅ Loaded {len(seen_tokens)} old tokens", flush=True)

    except Exception as e:
        print("❌ LOAD ERROR:", e, flush=True)

# =========================
# SAVE TOKENS
# =========================
def save_seen():
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump(seen_tokens, f)

    except Exception as e:
        print("❌ SAVE ERROR:", e, flush=True)

# =========================
# TELEGRAM
# =========================
def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT TOKEN OR CHAT ID MISSING", flush=True)
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = session.post(
            url,
            json=payload,
            timeout=15
        )

        print(f"📨 TELEGRAM STATUS: {response.status_code}", flush=True)

        if response.status_code != 200:
            print(response.text, flush=True)
            return False

        return True

    except Exception as e:
        print("❌ TELEGRAM ERROR:", e, flush=True)
        return False

# =========================
# FILTER CHECK
# =========================
def should_skip(token_name, token_symbol, description):

    if token_symbol.upper() in BASE_TICKERS:
        return True

    text = f"{token_name} {description}".lower()

    for word in BAD_WORDS:
        if word in text:
            return True

    return False

# =========================
# MESSAGE BUILDER
# =========================
def build_message(token_name, token_symbol, token_id, pair_url):

    if len(token_name) > 22:
        token_name = token_name[:19] + "..."

    return f"""
🚀 <b>Rocket Hunter Alert</b>

🪙 <b>Token:</b> {token_name} ({token_symbol})

⛓ <b>Chain:</b> Solana

📌 <b>Mint:</b>
<code>{token_id}</code>

🔗 <a href="{pair_url}">DexScreener Chart</a>
"""

# =========================
# GET TOKENS
# =========================
def get_tokens():

    url = "https://api.dexscreener.com/token-profiles/latest/v1"

    try:
        response = session.get(url, timeout=20)

        print(f"✅ API STATUS: {response.status_code}", flush=True)

        if response.status_code != 200:
            return []

        data = response.json()

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return data.get("pairs", [])

        return []

    except Exception as e:
        print("❌ API ERROR:", e, flush=True)
        return []

# =========================
# SCANNER
# =========================
def scan_tokens():

    print("🔍 SCANNING TOKENS...", flush=True)

    try:

        tokens = get_tokens()

        print(f"📊 TOKENS FOUND: {len(tokens)}", flush=True)

        now = time.time()

        alert_count = 0

        for token in tokens[:50]:

            try:

                chain = str(
                    token.get("chainId") or ""
                ).lower()

                if chain != "solana":
                    continue

                token_name = str(
                    token.get("name")
                    or token.get("tokenName")
                    or "Unknown"
                ).strip()

                token_symbol = str(
                    token.get("symbol")
                    or token.get("tokenSymbol")
                    or "???"
                ).strip()

                token_id = str(
                    token.get("tokenAddress")
                    or ""
                ).strip()

                description = str(
                    token.get("description")
                    or ""
                )

                pair_url = str(
                    token.get("url")
                    or ""
                ).strip()

                if not token_id:
                    continue

                if not pair_url:
                    pair_url = f"https://dexscreener.com/solana/{token_id}"

                # =========================
                # FILTERS
                # =========================
                if should_skip(
                    token_name,
                    token_symbol,
                    description
                ):
                    print(f"⏭ SKIPPED: {token_name}", flush=True)
                    continue

                # =========================
                # DUPLICATE CHECK
                # =========================
                last_seen = float(
                    seen_tokens.get(token_id, 0)
                )

                if now - last_seen < COOLDOWN_SECONDS:
                    continue

                # =========================
                # MESSAGE
                # =========================
                message = build_message(
                    token_name,
                    token_symbol,
                    token_id,
                    pair_url
                )

                # =========================
                # SEND ALERT
                # =========================
                ok = send_telegram(message)

                if ok:

                    seen_tokens[token_id] = now

                    save_seen()

                    alert_count += 1

                    print(
                        f"🚨 ALERT SENT: {token_name} ({token_symbol})",
                        flush=True
                    )

                    time.sleep(2)

                if alert_count >= MAX_ALERTS_PER_SCAN:
                    break

            except Exception as e:
                print("❌ TOKEN ERROR:", e, flush=True)

        print(
            f"✅ SCAN COMPLETE | ALERTS: {alert_count}",
            flush=True
        )

    except Exception as e:
        print("❌ SCAN ERROR:", e, flush=True)

# =========================
# LOOP
# =========================
def scan_loop():

    time.sleep(5)

    while True:

        try:
            scan_tokens()

        except Exception as e:
            print("❌ LOOP ERROR:", e, flush=True)

        print(
            f"[WAITING {SCAN_INTERVAL} SECONDS]",
            flush=True
        )

        time.sleep(SCAN_INTERVAL)

# =========================
# FLASK ROUTES
# =========================
@app.route("/")
def home():
    return "Rocket Hunter Live 🚀"

@app.route("/healthz")
def health():

    return jsonify({
        "ok": True,
        "tracked_tokens": len(seen_tokens)
    })

# =========================
# AUTO START THREAD
# =========================
load_seen()

scanner_worker = threading.Thread(
    target=scan_loop,
    daemon=True
)

scanner_worker.start()

print("✅ SCAN THREAD AUTO STARTED", flush=True)
