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

SEEN_FILE = os.getenv("SEEN_FILE", "/tmp/seen_tokens.json")

# =========================
# MEMORY
# =========================

seen_tokens = {}

# =========================
# FILTERS
# =========================

BAD_WORDS = {
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
    "User-Agent": "RocketHunter/4.0"
})

# =========================
# LOAD SEEN TOKENS
# =========================

def load_seen():
    global seen_tokens

    try:
        if os.path.exists(SEEN_FILE):

            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                seen_tokens = json.load(f)

            print(f"✅ LOADED {len(seen_tokens)} TOKENS", flush=True)

        else:
            seen_tokens = {}

    except Exception as e:
        print("❌ LOAD ERROR:", e, flush=True)
        seen_tokens = {}

# =========================
# SAVE SEEN TOKENS
# =========================

def save_seen():

    try:
        parent = os.path.dirname(SEEN_FILE)

        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_tokens, f)

    except Exception as e:
        print("❌ SAVE ERROR:", e, flush=True)

# =========================
# CLEAN OLD TOKENS
# =========================

def prune_seen(now_ts):

    old_tokens = []

    for token_id, ts in list(seen_tokens.items()):

        try:
            if now_ts - float(ts) > (COOLDOWN_SECONDS * 2):
                old_tokens.append(token_id)

        except Exception:
            old_tokens.append(token_id)

    for token_id in old_tokens:
        seen_tokens.pop(token_id, None)

# =========================
# TELEGRAM ALERT
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
        response = session.post(url, json=payload, timeout=20)

        print(f"📨 TELEGRAM STATUS: {response.status_code}", flush=True)

        if response.status_code != 200:
            print(response.text[:1000], flush=True)
            return False

        return True

    except Exception as e:
        print("❌ TELEGRAM ERROR:", e, flush=True)
        return False

# =========================
# FETCH TOKENS
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
# FILTER BAD TOKENS
# =========================

def should_skip(token_name, token_symbol, description_text):

    if token_symbol.upper() in BASE_TICKERS:
        return True

    lower_text = f"{token_name} {description_text}".lower()

    for word in BAD_WORDS:
        if word in lower_text:
            return True

    return False

# =========================
# MESSAGE FORMAT
# =========================

def build_message(token_name, token_symbol, token_id, pair_url):

    short_name = token_name

    if len(short_name) > 20:
        short_name = short_name[:17] + "..."

    return f"""
🚀 <b>Rocket Hunter Alert</b>

🪙 <b>Token:</b> {short_name} ({token_symbol})

⛓ <b>Chain:</b> Solana

📌 <b>Mint:</b>
<code>{token_id}</code>

🔗 <a href="{pair_url}">Trade on DexScreener</a>
"""

# =========================
# MAIN SCANNER
# =========================

def scan_tokens():

    print("🔎 SCANNING TOKENS...", flush=True)

    try:

        tokens = get_tokens()

        print(f"📊 TOKENS FOUND: {len(tokens)}", flush=True)

        now_ts = time.time()

        prune_seen(now_ts)

        alert_count = 0

        for token in tokens[:100]:

            try:

                chain = str(
                    token.get("chainId") or ""
                ).lower().strip()

                if chain != "solana":
                    continue

                token_name = str(
                    token.get("name")
                    or token.get("tokenName")
                    or ""
                ).strip()

                token_symbol = str(
                    token.get("symbol")
                    or token.get("tokenSymbol")
                    or ""
                ).strip()

                token_id = str(
                    token.get("tokenAddress")
                    or token.get("address")
                    or ""
                ).strip()

                description_text = str(
                    token.get("description")
                    or ""
                ).strip()

                pair_url = str(
                    token.get("url")
                    or ""
                ).strip()

                # =========================
                # EMPTY CHECKS
                # =========================

                if not token_symbol:
                    print("⏭ SKIP EMPTY SYMBOL", flush=True)
                    continue

                if not token_name:
                    print("⏭ SKIP EMPTY NAME", flush=True)
                    continue

                if not token_id:
                    print("⏭ SKIP EMPTY TOKEN ID", flush=True)
                    continue

                print(
                    f"🔥 FOUND TOKEN: {token_name} | {token_symbol}",
                    flush=True
                )

                # =========================
                # DEFAULT URL
                # =========================

                if not pair_url:
                    pair_url = f"https://dexscreener.com/solana/{token_id}"

                # =========================
                # FILTERS
                # =========================

                if should_skip(
                    token_name,
                    token_symbol,
                    description_text
                ):
                    print(f"⏭ FILTERED: {token_name}", flush=True)
                    continue

                # =========================
                # COOLDOWN
                # =========================

                last_seen = float(
                    seen_tokens.get(token_id, 0)
                )

                if now_ts - last_seen < COOLDOWN_SECONDS:
                    print(f"⏭ COOLDOWN: {token_symbol}", flush=True)
                    continue

                # =========================
                # SEND ALERT
                # =========================

                message = build_message(
                    token_name,
                    token_symbol,
                    token_id,
                    pair_url
                )

                ok = send_telegram(message)

                if ok:

                    seen_tokens[token_id] = now_ts

                    save_seen()

                    alert_count += 1

                    print(
                        f"🚨 ALERT SENT: {token_name} ({token_symbol})",
                        flush=True
                    )

                    time.sleep(2)

                # =========================
                # LIMIT ALERTS
                # =========================

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
# ROUTES
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
# START
# =========================

if __name__ == "__main__":

    print("🚀 ROCKET HUNTER STARTING...", flush=True)

    load_seen()

    scan_worker = threading.Thread(
        target=scan_loop,
        daemon=True
    )

    scan_worker.start()

    print("✅ SCANNER THREAD STARTED", flush=True)

    port = int(os.environ.get("PORT", 10000))

    print(f"🌐 RUNNING ON PORT {port}", flush=True)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
