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
    "User-Agent": "RocketHunter/1.0"
})

# =========================
# LOAD SEEN TOKENS
# =========================
def load_seen():
    global seen_tokens

    try:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, "r") as f:
                seen_tokens = json.load(f)
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
        with open(SEEN_FILE, "w") as f:
            json.dump(seen_tokens, f)

    except Exception as e:
        print("❌ SAVE ERROR:", e, flush=True)

# =========================
# CLEAN OLD TOKENS
# =========================
def prune_seen(now_ts):

    old = []

    for token_id, ts in list(seen_tokens.items()):

        try:
            if now_ts - float(ts) > COOLDOWN_SECONDS * 2:
                old.append(token_id)

        except:
            old.append(token_id)

    for token_id in old:
        seen_tokens.pop(token_id, None)

# =========================
# TELEGRAM SEND
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

            try:
                print(response.json(), flush=True)

            except:
                print(response.text, flush=True)

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

        print(
            f"✅ DEX STATUS: {response.status_code}",
            flush=True
        )

        if response.status_code != 200:
            return []

        data = response.json()

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return data.get("pairs", [])

        return []

    except Exception as e:
        print("❌ FETCH ERROR:", e, flush=True)
        return []

# =========================
# FILTER CHECK
# =========================
def should_skip(name, symbol, description):

    if symbol.upper() in BASE_TICKERS:
        return True

    name = name.lower()
    description = description.lower()

    for word in BAD_WORDS:

        if word in name:
            return True

        if word in description:
            return True

    return False

# =========================
# BUILD MESSAGE
# =========================
def build_message(token_name, token_symbol, token_id, pair_url):

    if len(token_name) > 20:
        token_name = token_name[:17] + "..."

    return f"""
🚀 <b>Rocket Hunter Alert</b>

🪙 <b>Token:</b> {token_name} ({token_symbol})

⛓ <b>Chain:</b> Solana

📌 <b>Mint:</b>
<code>{token_id[:6]}...{token_id[-4:]}</code>

🔗 <a href="{pair_url}">Trade on DexScreener</a>
"""

# =========================
# MAIN SCANNER
# =========================
def scan_tokens():

    print("🔍 SCANNING TOKENS...", flush=True)

    try:

        tokens = get_tokens()

        print(
            f"📊 TOKENS FOUND: {len(tokens)}",
            flush=True
        )

        now_ts = time.time()

        prune_seen(now_ts)

        alert_count = 0

        for token in tokens[:50]:

            try:

                # =========================
                # ONLY SOLANA
                # =========================
                chain = str(
                    token.get("chainId") or ""
                ).lower()

                if chain != "solana":
                    continue

                # =========================
                # TOKEN DATA
                # =========================
                token_name = (
                    token.get("name")
                    or token.get("tokenName")
                    or token.get("baseToken", {}).get("name")
                    or "Unknown"
                )

                token_symbol = (
                    token.get("symbol")
                    or token.get("tokenSymbol")
                    or token.get("baseToken", {}).get("symbol")
                    or "???"
                )

                token_name = str(token_name).strip()
                token_symbol = str(token_symbol).strip()

                token_id = str(
                    token.get("tokenAddress") or ""
                ).strip()

                description_text = str(
                    token.get("description") or ""
                )

                pair_url = str(
                    token.get("url") or ""
                ).strip()

                # =========================
                # SKIP BAD TOKENS
                # =========================
                if not token_id:
                    continue

                if not pair_url:
                    pair_url = f"https://dexscreener.com/solana/{token_id}"

                if should_skip(
                    token_name,
                    token_symbol,
                    description_text
                ):
                    print(
                        f"⏭️ SKIP: {token_name}",
                        flush=True
                    )
                    continue

                # =========================
                # COOLDOWN CHECK
                # =========================
                last_seen = float(
                    seen_tokens.get(token_id, 0)
                )

                if now_ts - last_seen < COOLDOWN_SECONDS:
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

    time.sleep(8)

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
# AUTO START
# =========================
if __name__ == "__main__":

    print(
        "🚀 ROCKET HUNTER STARTING...",
        flush=True
    )

    load_seen()

    scanner_worker = threading.Thread(
        target=scan_loop,
        daemon=True
    )

    scanner_worker.start()

    print(
        "✅ SCAN THREAD AUTO STARTED",
        flush=True
    )

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
