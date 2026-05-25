import os
import time
import random
import sqlite3
import logging
import threading
import requests

from flask import Flask, jsonify
from threading import Thread
from datetime import datetime, timezone
from contextlib import contextmanager
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
# ========================================================
# ALPHA SHIELD V3 - PRODUCTION PREDICTIVE LAYER
# ========================================================

BASE_TICKERS = {"SOL", "WSOL", "USDC", "USDT", "USDC.SOL", "USDT.SOL"}

def run_alpha_shield_v3(pair_data, now_ts):

    base_token = pair_data.get("baseToken", {})
    token_symbol = str(base_token.get("symbol") or "???").strip()
    token_id = str(base_token.get("address") or "").strip()

    if token_symbol.upper() in BASE_TICKERS or not token_id:
        return False, "BASE_ASSET_SKIP", 0, 0

    liquidity = float(pair_data.get("liquidity", {}).get("usd") or 0)
    volume_5m = float(pair_data.get("volume", {}).get("m5") or 0)

    if liquidity < 3000:
        return False, "LOW_LIQUIDITY_SKIP", 0, 0

    pair_created_at = float(pair_data.get("pairCreatedAt") or 0) / 1000.0
    pool_age_seconds = now_ts - pair_created_at if pair_created_at > 0 else 99999

    if pool_age_seconds > 900:
        return False, "STALE_POOL_SKIP", pool_age_seconds, 0

    conviction_score = 50

    if pool_age_seconds <= 180:
         conviction_score += 20        
# ========================================================
# ALPHA SHIELD V3 - PRODUCTION PREDICTIVE LAYER
# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ==========================================
# APP
# ==========================================

app = Flask(__name__)

# ==========================================
# ENV
# ==========================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================================
# CONFIG
# ==========================================

DEX_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"

COOLDOWN = int(os.getenv("COOLDOWN", "1800"))
MAX_CACHE = int(os.getenv("MAX_CACHE", "5000"))
MAX_ALERTS_PER_SCAN = int(os.getenv("MAX_ALERTS_PER_SCAN", "3"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "60"))

MIN_GECKO_LIQ = float(os.getenv("MIN_GECKO_LIQ", "5000"))
MIN_DEX_LIQ = float(os.getenv("MIN_DEX_LIQ", "1000"))
MIN_VOLUME = float(os.getenv("MIN_VOLUME", "3000"))
MAX_FDV = float(os.getenv("MAX_FDV", "25000000"))

JOURNAL_DB = os.getenv("JOURNAL_DB", "rocket-hunter-journal.db")
PORT = int(os.getenv("PORT", "10000"))

# ==========================================
# CACHE
# ==========================================

SENT_TOKENS = {}

CACHE_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()

LAST_SCAN_STATS = {
    "status": "booting",
    "last_scan_at": None,
    "last_alerts": 0,
    "last_error": None,
    "tracked_tokens": 0
}

# ==========================================
# HTTP SESSION
# ==========================================

def build_session():
    s = requests.Session()

    s.headers.update({
        "User-Agent": "RocketHunterV2/1.0"
    })

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=20,
        pool_maxsize=20
    )

    s.mount("https://", adapter)
    s.mount("http://", adapter)

    return s

session = build_session()

# ==========================================
# ROUTES
# ==========================================

@app.route("/")
def home():
    return "🚀 Rocket Hunter V2 — Alpha Shield LIVE", 200

@app.route("/healthz")
def healthz():
    with STATE_LOCK:
        return jsonify(LAST_SCAN_STATS), 200

@app.route("/stats")
def stats():
    with journal_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM alerts")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM alerts WHERE alert_sent = 1")
        sent = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM alerts WHERE label = 'blocked'")
        blocked = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM alerts WHERE label = 'rejected'")
        rejected = cur.fetchone()[0]

    return jsonify({
        "total_logged": total,
        "sent": sent,
        "blocked": blocked,
        "rejected": rejected
    }), 200

@app.route("/recent")
def recent():
    with journal_db() as conn:
        conn.row_factory = sqlite3.Row

        cur = conn.cursor()

        cur.execute("""
            SELECT mint,
                   symbol,
                   timestamp,
                   liquidity,
                   volume,
                   price_change,
                   entry_label,
                   shield_result,
                   alert_sent,
                   label
            FROM alerts
            ORDER BY id DESC
            LIMIT 20
        """)

        rows = [dict(r) for r in cur.fetchall()]

    return jsonify(rows), 200

# ==========================================
# HELPERS
# ==========================================

def get_entry_label(age_hours):
    if age_hours <= 1:
        return "⚡ ULTRA EARLY"

    if age_hours <= 6:
        return "🟢 EARLY"

    if age_hours <= 24:
        return "🟡 LATE ENTRY"

    return None

def normalize_mint(token_id):
    if not token_id:
        return None

    raw = token_id.split("_", 1)[1] if token_id.startswith("solana_") else token_id
    raw = raw.strip()

    allowed = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

    if len(raw) < 32 or len(raw) > 48:
        return None

    if any(ch not in allowed for ch in raw):
        return None

    return raw

# ==========================================
# SQLITE
# ==========================================

def init_journal_db():
    conn = sqlite3.connect(JOURNAL_DB, timeout=30)

    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mint TEXT,
            symbol TEXT,
            timestamp TEXT,
            liquidity REAL,
            volume REAL,
            price_change REAL,
            age_hours REAL,
            entry_label TEXT,
            buys INTEGER,
            sells INTEGER,
            buyers INTEGER,
            suspicious INTEGER,
            fdv REAL,
            shield_result TEXT,
            alert_sent INTEGER,
            label TEXT,
conviction_score INTEGER DEFAULT 0
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_mint ON alerts(mint)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")

    conn.commit()
    conn.close()

@contextmanager
def journal_db():
    conn = sqlite3.connect(JOURNAL_DB, timeout=30)

    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")

        yield conn

    finally:
        conn.close()

# ==========================================
# CACHE CLEANUP
# ==========================================

def cleanup_cache(now_ts):
    with CACHE_LOCK:

        expired = [
            k for k, v in SENT_TOKENS.items()
            if now_ts - v > COOLDOWN
        ]

        for k in expired:
            SENT_TOKENS.pop(k, None)

        if len(SENT_TOKENS) > MAX_CACHE:

            overflow = len(SENT_TOKENS) - MAX_CACHE

            oldest = sorted(
                SENT_TOKENS.items(),
                key=lambda x: x[1]
            )[:overflow]

            for k, _ in oldest:
                SENT_TOKENS.pop(k, None)

            logging.info("🧹 Cache trimmed")

        with STATE_LOCK:
            LAST_SCAN_STATS["tracked_tokens"] = len(SENT_TOKENS)

# ==========================================
# TELEGRAM BACKOFF
# ==========================================

def tg_backoff_sleep(resp_json):
    params = resp_json.get("parameters", {}) if isinstance(resp_json, dict) else {}

    retry_after = params.get("retry_after")

    wait_s = int(retry_after) + 1 if retry_after else 5

    logging.warning(f"Telegram 429 hit, sleeping {wait_s}s")

    time.sleep(wait_s)

# ==========================================
# DEXSCREENER VERIFY
# ==========================================

def verify_on_dexscreener(mint_address):

    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"

        time.sleep(0.25)

        res = session.get(url, timeout=10)

        if res.status_code == 429:
            logging.warning("DexScreener 429 rate limit")
            return 0, None, None

        if res.status_code != 200:
            return 0, None, None

        pairs = res.json().get("pairs", [])

        solana_pairs = [
            p for p in pairs
            if p.get("chainId") == "solana"
        ]

        if not solana_pairs:
            return 0, None, None

        best = max(
            solana_pairs,
            key=lambda x: float(x.get("liquidity", {}).get("usd") or 0)
        )

        real_liq = float(best.get("liquidity", {}).get("usd") or 0)

        dex_url = best.get("url")
        price_usd = best.get("priceUsd")

        return real_liq, dex_url, price_usd

    except Exception as e:
        logging.error(f"DexScreener verify error: {e}")
        return 0, None, None

# ==========================================
# ALPHA SHIELD V2
# ==========================================
# ==========================================
# CONVICTION ENGINE
# ==========================================


# ==========================================
# ALPHA SHIELD V2
# ==========================================


def alpha_shield_v2(fdv, liquidity, buys, sells, buyers, suspicious_reports=0):

    if liquidity < 3000:
        return False, "LOW_REAL_LIQUIDITY"

    if fdv and fdv > MAX_FDV:
        return False, "OVERPUMPED_FAKE_MC"

    if buys <= 0 or buyers <= 0:
        return False, "NO_REAL_BUY_ACTIVITY"

    if sells == 0 and buys > 25:
        return False, "ONE_SIDED_FLOW"

    if suspicious_reports and suspicious_reports > 0:
        return False, "COMMUNITY_FLAGGED"

    return True, "SURVIVABLE_ALPHA"

# ==========================================
# TELEGRAM ALERT
# ==========================================

def send_alert(
    symbol,
    liquidity,
    volume,
    dex_url,
    gecko_url,
    price_change,
    entry_label,
    mint_address
):

    if liquidity > 50000 and volume > 20000:
        risk = "🛡️ LOW RISK"

    elif liquidity > 10000:
        risk = "⚠️ MEDIUM RISK"

    else:
        risk = "🔴 HIGH RISK"

    change_icon = "📈" if price_change >= 0 else "📉"

    clean_symbol = symbol.replace("<", "&lt;").replace(">", "&gt;")

    short_mint = f"{mint_address[:6]}...{mint_address[-6:]}"

    message = (
        f"🚀 <b>Rocket Hunter Alert</b>\n\n"
        f"{entry_label}\n\n"
        f"💎 <b>{clean_symbol} / SOL</b>\n"
        f"🪪 Mint: <code>{short_mint}</code>\n\n"
        f"💧 Liquidity: ${liquidity:,.0f}\n"
        f"📊 Volume: ${volume:,.0f}\n"
        f"{change_icon} Change: {price_change:.1f}%\n\n"
        f"{risk}\n"
        f"🛡️ Alpha Shield V2 Active\n"
        f"✅ <i>Verified on DexScreener</i>"
    )

    buttons = []

    if dex_url:
        buttons.append({
            "text": "📊 DexScreener",
            "url": dex_url
        })

    if gecko_url:
        buttons.append({
            "text": "🦎 GeckoTerminal",
            "url": gecko_url
        })

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [buttons]
        }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for _ in range(3):

        try:
            res = session.post(url, json=payload, timeout=10)

            if res.status_code == 200:
                logging.info(f"✅ ALERT: {symbol} | {entry_label}")
                return True

            try:
                body = res.json()
            except Exception:
                body = {}

            if res.status_code == 429:
                tg_backoff_sleep(body)
                continue

            logging.error(f"Telegram Error: {res.text}")
            return False

        except Exception as e:
            logging.error(f"Telegram Exception: {e}")
            time.sleep(2)

    return False

# ==========================================
# SQLITE LOGGING
# ==========================================

def log_alert(
    mint,
    symbol,
    ts,
    liquidity,
    volume,
    price_change,
    age_hours,
    entry_label,
    buys,
    sells,
    buyers,
    suspicious,
    fdv,
    shield_result,
    alert_sent,
        label,
     conviction_score=0
):


    with journal_db() as conn:

        conn.execute("""
            INSERT INTO alerts (
                mint,
                symbol,
                timestamp,
                liquidity,
                volume,
                price_change,
                age_hours,
                entry_label,
                buys,
                sells,
                buyers,
                suspicious,
                fdv,
             shield_result,
   alert_sent,
     label,
     conviction_score
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mint,
            symbol,
            ts,
            liquidity,
            volume,
            price_change,
            age_hours,
            entry_label,
            buys,
            sells,
            buyers,
            suspicious,
            fdv,
            shield_result,
1 if alert_sent else 0,
label or "pending",
conviction_score
))

        conn.commit()

# ==========================================
# STATE
# ==========================================

def set_scan_state(status=None, last_alerts=None, last_error=None):

    with STATE_LOCK:

        if status is not None:
            LAST_SCAN_STATS["status"] = status

        if last_alerts is not None:
            LAST_SCAN_STATS["last_alerts"] = last_alerts

        if last_error is not None:
            LAST_SCAN_STATS["last_error"] = last_error

        LAST_SCAN_STATS["last_scan_at"] = datetime.now(timezone.utc).isoformat()

# ==========================================
# MAIN SCANNER
# ==========================================

def scanner():

    init_journal_db()

    logging.info("🚀 Rocket Hunter V2 — Alpha Shield Starting...")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ ENV VARIABLES MISSING!")

        set_scan_state(
            status="env_error",
            last_error="Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
        )

        return

    while True:

        alerts = 0

        try:

            now_ts = time.time()
            now_utc = datetime.now(timezone.utc)

            cleanup_cache(now_ts)

            res = session.get(DEX_URL, timeout=15)

            logging.info(f"API STATUS: {res.status_code}")

            if res.status_code == 429:

                wait_s = 90 + random.randint(0, 20)

                logging.warning(f"Rate limited! Waiting {wait_s}s...")

                set_scan_state(
                    status="rate_limited",
                    last_alerts=0,
                    last_error="GeckoTerminal 429"
                )

                time.sleep(wait_s)
                continue

            if res.status_code != 200:

                set_scan_state(
                    status="api_error",
                    last_alerts=0,
                    last_error=f"GeckoTerminal status {res.status_code}"
                )

                time.sleep(30)
                continue

            pools = res.json().get("data", [])

            for pool in pools:

                try:

                    attr = pool.get("attributes", {})

                    pair_address = attr.get("address")

                    if not pair_address:
                        continue

                    created_at = attr.get("pool_created_at")

                    if not created_at:
                        continue

                    pool_time = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )

                    age_hours = (
                        now_utc - pool_time
                    ).total_seconds() / 3600

                    entry_label = get_entry_label(age_hours)

                    if not entry_label:
                        continue

                    pool_name = attr.get("name", "")

                    symbol = (
                        pool_name.split("/")[0].replace(" ", "").strip()
                        if "/" in pool_name
                        else (pool_name[:10] or "Unknown")
                    )

                    if symbol.lower() in {
                        "sol",
                        "wsol",
                        "usdc",
                        "usdt",
                        "unknown"
                    }:
                        continue

                    mint_id = (
                        pool.get("relationships", {})
                        .get("base_token", {})
                        .get("data", {})
                        .get("id")
                    )

                    mint_address = normalize_mint(mint_id)

                    if not mint_address:
                        continue

                    with CACHE_LOCK:

                        if now_ts - SENT_TOKENS.get(mint_address, 0) < COOLDOWN:
                            logging.info(f"⏭️ Duplicate skip: {symbol}")
                            continue

                    gecko_liq = float(attr.get("reserve_in_usd") or 0)

                    if gecko_liq < MIN_GECKO_LIQ:
                        continue

                    vol_data = attr.get("volume_usd", {})

                    volume = (
                        float(vol_data.get("h24") or 0)
                        or float(vol_data.get("h1") or 0) * 24
                        or float(vol_data.get("m5") or 0) * 288
                    )

                    if volume < MIN_VOLUME:
                        continue

                    change_data = attr.get("price_change_percentage", {})

                    price_change = float(
                        change_data.get("h24")
                        or change_data.get("h1")
                        or change_data.get("m5")
                        or 0
                    )

                    tx = attr.get("transactions", {})

                    txh1 = tx.get("h1") or tx.get("m15") or {}

                    buys = int(txh1.get("buys") or 0)
                    sells = int(txh1.get("sells") or 0)
                    buyers = int(txh1.get("buyers") or 0)

                    suspicious = int(
                        attr.get("community_sus_report") or 0
                    )

                    fdv = float(
                        attr.get("fdv_usd")
                        or attr.get("fully_diluted_valuation")
                        or 0
                    )

                    real_liq, dex_url, _price_usd = verify_on_dexscreener(
                        mint_address
                    )

                    if real_liq < MIN_DEX_LIQ:

                        log_alert(
                            mint_address,
                            symbol,
                            datetime.utcnow().isoformat(),
                            gecko_liq,
                            volume,
                            price_change,
                            age_hours,
                            entry_label,
                            buys,
                            sells,
                            buyers,
                            suspicious,
                            fdv,
                            "LOW_DEX_LIQUIDITY",
                            False,
                            "rejected"
                        )

                        continue

                    passed, shield_reason = alpha_shield_v2(
                        fdv,
                        real_liq,
                        buys,
                        sells,
                        buyers,
                        suspicious
                    )

                    if not passed:

                        log_alert(
                            mint_address,
                            symbol,
                            datetime.utcnow().isoformat(),
                            gecko_liq,
                            volume,
                            price_change,
                            age_hours,
                            entry_label,
                            buys,
                            sells,
                            buyers,
                            suspicious,
                            fdv,
                            shield_reason,
                            False,
                            "blocked"
                        )

                        logging.info(
                            f"🚫 SHIELD BLOCKED: {symbol} | {shield_reason}"
                        )

                        continue

                    gecko_url = (
                        f"https://www.geckoterminal.com/solana/pools/{pair_address}"
                    )

                    success = send_alert(
                        symbol,
                        real_liq,
                        volume,
                        dex_url,
                        gecko_url,
                        price_change,
                        entry_label,
                        mint_address
                    )

                    if success:

                        with CACHE_LOCK:
                            SENT_TOKENS[mint_address] = now_ts

                        log_alert(
                            mint_address,
                            symbol,
                            datetime.utcnow().isoformat(),
                            gecko_liq,
                            volume,
                            price_change,
                            age_hours,
                            entry_label,
                            buys,
                            sells,
                            buyers,
                            suspicious,
                            fdv,
                            "SURVIVABLE",
                            True,
                            "sent"
                        )

                        alerts += 1

                        time.sleep(3)

                    if alerts >= MAX_ALERTS_PER_SCAN:
                        break

                except Exception as e:
                    logging.error(f"Pool Error: {e}")

            logging.info(f"✅ Done | Alerts: {alerts}")

            set_scan_state(
                status="running",
                last_alerts=alerts,
                last_error=None
            )

        except Exception as e:

            logging.error(f"Scanner Error: {e}")

            set_scan_state(
                status="scanner_error",
                last_alerts=alerts,
                last_error=str(e)
            )

        logging.info(f"⏳ Waiting {SCAN_INTERVAL}s...")

        time.sleep(SCAN_INTERVAL)

# ==========================================
# START ENGINE
# ==========================================

if __name__ == "__main__":

    Thread(target=scanner, daemon=True).start()

    app.run(
        host="0.0.0.0",
        port=PORT
    )
