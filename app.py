import os
import json
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

BASE_TICKERS = {"SOL", "WSOL", "USDC", "USDT", "USDC.SOL", "USDT.SOL"}


def run_alpha_shield_v3(pair_data, now_ts, buyers=0):

    base_token = pair_data.get("baseToken", {})

    token_symbol = str(
        base_token.get("symbol") or "???"
    ).strip()

    token_id = str(
        base_token.get("address") or ""
    ).strip()

    if token_symbol.upper() in BASE_TICKERS or not token_id:
        return False, "BASE_ASSET_SKIP", 0, 0, [], []

    liquidity = float(
        pair_data.get("liquidity", {}).get("usd") or 0
    )

    volume_5m = float(
        pair_data.get("volume", {}).get("m5") or 0
    )

    if liquidity < 3000:
        return False, "LOW_LIQUIDITY_SKIP", 0, 0, [], []

    pair_created_at = float(
        pair_data.get("pairCreatedAt") or 0
    ) / 1000.0

    pool_age_seconds = (
        now_ts - pair_created_at
        if pair_created_at > 0
        else 99999
    )
if pool_age_seconds > 900:  
    return False, "STALE_POOL_SKIP", pool_age_seconds, 0, [], []  

# ========================================================  
# CONVICTION ENGINE  
# ========================================================  

conviction_score = 0  

reasons = []  
penalties = []  

# ========================================================  
# POOL AGE  
# ========================================================  

if pool_age_seconds <= 180:  
    conviction_score += 20  
    reasons.append("fresh_pool")  

elif pool_age_seconds <= 420:  
    conviction_score += 10  
    reasons.append("moderately_fresh_pool")  

elif pool_age_seconds <= 900:  
    conviction_score += 5  
    reasons.append("older_pool")  

# ========================================================  
# LIQUIDITY  
# ========================================================  

if liquidity >= 20000:  
    conviction_score += 15  
    reasons.append("strong_liquidity")  

elif liquidity >= 10000:  
    conviction_score += 10  
    reasons.append("healthy_liquidity")  

elif liquidity >= 5000:  
    conviction_score += 5  
    reasons.append("acceptable_liquidity")  

# ========================================================  
# VOLUME  
# ========================================================  

if volume_5m >= 50000:  
    conviction_score += 20  
    reasons.append("strong_volume")  

elif volume_5m >= 20000:  
    conviction_score += 15  
    reasons.append("healthy_volume")  

elif volume_5m >= 8000:  
    conviction_score += 10  
    reasons.append("good_volume")  

elif volume_5m >= 3000:  
    conviction_score += 5  
    reasons.append("minimum_volume")  

# ========================================================  
# TXNS  
# ========================================================  

txns = pair_data.get("txns", {})  
tx_5m = txns.get("m5", {}) or {}  

buys = int(tx_5m.get("buys") or 0)  
sells = int(tx_5m.get("sells") or 0)  

# ========================================================  
# BUY PRESSURE  
# ========================================================  

if buys >= 40:  
    conviction_score += 15  
    reasons.append("heavy_buy_pressure")  

elif buys >= 20:  
    conviction_score += 10  
    reasons.append("good_buy_pressure")  

elif buys >= 8:  
    conviction_score += 5  
    reasons.append("light_buy_pressure")  

# ========================================================  
# ONE SIDED FLOW  
# ========================================================  

if sells == 0 and buys >= 25:  
    conviction_score -= 15  
    penalties.append("one_sided_flow")  

elif buys > 0 and sells > 0:  

    ratio = buys / max(sells, 1)  

    if ratio >= 2.5:  
        conviction_score += 10  
        reasons.append("strong_buy_sell_ratio")  

    elif ratio >= 1.5:  
        conviction_score += 5  
        reasons.append("healthy_buy_sell_ratio")  

    elif ratio < 0.8:  
        conviction_score -= 5  
        penalties.append("weak_buy_sell_ratio")  

# ========================================================  
# PRICE CHANGE  
# ========================================================  

price_change_5m = float(  
    pair_data.get("priceChange", {}).get("m5") or 0  
)  

if price_change_5m >= 300:  
    conviction_score -= 30  
    penalties.append("hyper_pump_penalty")  

elif price_change_5m >= 150:  
    conviction_score -= 15  
    penalties.append("overextended_price")  

elif price_change_5m >= 15:  
    conviction_score += 10  
    reasons.append("momentum_building")  

elif price_change_5m >= 7:  
    conviction_score += 5  
    reasons.append("healthy_momentum")  

elif price_change_5m <= -8:  
    conviction_score -= 10  
    penalties.append("price_breakdown")  

# ========================================================  
# FDV  
# ========================================================  

fdv = float(  
    pair_data.get("fdv") or 0  
)  

if fdv > 0:  

    if fdv > 25000000:  
        conviction_score -= 20  
        penalties.append("overinflated_fdv")  

    elif fdv > 10000000:  
        conviction_score -= 10  
        penalties.append("high_fdv")  

    elif 500000 <= fdv <= 2000000:  
        conviction_score += 5  
        reasons.append("healthy_fdv")  

# ========================================================  
# LIQ / FDV  
# ========================================================  

if liquidity > 0 and fdv > 0:  

    liq_to_fdv = liquidity / fdv  

    if liq_to_fdv >= 0.12:  
        conviction_score += 10  
        reasons.append("excellent_liq_ratio")  

    elif liq_to_fdv >= 0.06:  
        conviction_score += 5  
        reasons.append("healthy_liq_ratio")  

    elif liq_to_fdv < 0.02:  
        conviction_score -= 10  
        penalties.append("weak_liq_ratio")  

# ========================================================  
# ANTI BOT  
# ========================================================  

if buys >= 12:  

    estimated_buyers = (  
        buyers  
        if buyers > 0  
        else int(buys * 0.35)  
    )  

    unique_ratio = estimated_buyers / buys  

    if unique_ratio < 0.25:  
        conviction_score -= 20  
        penalties.append("wash_trade_risk")  

    elif unique_ratio < 0.40:  
        conviction_score -= 10  
        penalties.append("anti_bot_penalty")  

# ========================================================  
# MICRO FDV  
# ========================================================  
if fdv > 0:

    if fdv < 10000:
        conviction_score -= 20
        penalties.append("micro_fdv_trap")

    elif fdv < 25000:
        conviction_score -= 10
        penalties.append("low_fdv")

    elif fdv < 50000:
        conviction_score -= 5
        penalties.append("mid_low_fdv")
  

# ========================================================  
# LOW LIQ + HIGH VOL  
# ========================================================  

if liquidity < 10000 and volume_5m > 50000:  
    conviction_score -= 20  
    penalties.append("fake_volume_profile")  

# ========================================================  
# SUSPICIOUS LABELS  
# ========================================================  

suspicious = 0  

if pair_data.get("labels"):  

    labels_joined = " ".join(  
        pair_data.get("labels", [])  
    ).lower()  

    if "scam" in labels_joined:  
        suspicious += 1  

    if "rug" in labels_joined:  
        suspicious += 1  

if suspicious > 0:  
    conviction_score -= 20  
    penalties.append("suspicious_labels")  

# ========================================================  
# 🆕 UPGRADE 1: SYNTHETIC PUMP BLOCK  
# Catches: 光源 pattern — huge buyers, tiny sellers, LP collapse  
# ========================================================  

buyer_seller_ratio = buys / max(sells, 1)  

if buyer_seller_ratio > 20 and liquidity < 5000:  
    conviction_score -= 35  
    penalties.append("synthetic_pump_risk")  
    logging.info(f"🚨 SYNTHETIC PUMP: ratio={buyer_seller_ratio:.1f}, liq={liquidity}")  

# ========================================================  
# 🆕 UPGRADE 2: VOL/LIQ REALITY CHECK  
# Catches: LP=$1 but Volume=$2M — impossible organic market  
# ========================================================  

vol_liq_ratio = volume_5m / max(liquidity, 1)  

if vol_liq_ratio > 15:  
    conviction_score -= 25  
    penalties.append("unrealistic_volume")  
    logging.info(f"🚨 FAKE VOLUME: vol={volume_5m}, liq={liquidity}, ratio={vol_liq_ratio:.1f}")  

# ========================================================  
# 🆕 UPGRADE 3: FLASH PUMP TRAP (BONUS — extra safety)  
# Catches: 80%+ spike in 5m but volume < liquidity = fake first candle  
# ========================================================  

if price_change_5m > 80 and volume_5m < liquidity:  
    conviction_score -= 20  
    penalties.append("flash_pump")  
    logging.info(f"🚨 FLASH PUMP TRAP: price_5m={price_change_5m}%, vol={volume_5m}, liq={liquidity}")  

# ========================================================  
# 🆕 UPGRADE 4: CONTINUATION BONUS  
# ========================================================  

if (  
    conviction_score >= 55  
    and price_change_5m > 15  
    and buys > sells  
    and liquidity > 10000  
    and "flash_pump" not in penalties  
    and "synthetic_pump_risk" not in penalties  
):  
    conviction_score += 10  
    reasons.append("momentum_continuation")  
    logging.info(  
        f"✅ CONTINUATION BONUS: +10 | score now={conviction_score}"  
    )  

# ========================================================  
# FINAL SCORE CLAMP  
# ========================================================  

conviction_score = max(  
    0,  
    min(95, conviction_score)  
)  

# ========================================================  
# DEBUG BLOCK  
# ========================================================  

debug_data = {  
    "symbol": token_symbol,  
    "score": conviction_score,  
    "reasons": reasons,  
    "penalties": penalties,  
    "liq": liquidity,  
    "vol": volume_5m,  
    "buys": buys,  
    "sells": sells,  
    "fdv": fdv,  
    "price_change_5m": price_change_5m,  
}  

logging.info(  
    "🧠 SCORE DEBUG: %s",  
    debug_data  
)  

# ========================================================  
# HARD BLOCKS  
# ========================================================  

if suspicious > 0:  
    return (  
        False,  
        "SCAM_LABEL_RISK",  
        pool_age_seconds,  
        conviction_score,  
        reasons,  
        penalties  
    )  

# ========================================================  
# FINAL DECISION  
# ========================================================  

if conviction_score >= 75:  

    return (  
        True,  
        "HUNTER_ALPHA_CANDIDATE",  
        pool_age_seconds,  
        conviction_score,  
        reasons,  
        penalties  
    )  

if conviction_score >= 70:  

    return (  
        False,  
        "WATCHLIST",  
        pool_age_seconds,  
        conviction_score,  
        reasons,  
        penalties  
    )  

return (  
    False,  
    "LOW_CONVICTION",  
    pool_age_seconds,  
    conviction_score,  
    reasons,  
    penalties  
)

SURVIVAL_SECONDS = 300

# ====================================
# LOGGING
# ====================================

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s - %(levelname)s - %(message)s"
)

# ====================================
# APP
# ====================================

app = Flask(__name__)

# ====================================
# ENV
# ====================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

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
               label,  
               conviction_score,  
               reasons_json,  
               penalties_json,  
               tx_source  
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
        conviction_score INTEGER DEFAULT 0,  
        reasons_json TEXT,  
        penalties_json TEXT,  
        tx_source TEXT  
    )  
""")  

cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_mint ON alerts(mint)")  
cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")  

# ==========================================  
# POST-ALERT OUTCOMES TABLE  
# ==========================================  

cur.execute("""  
    CREATE TABLE IF NOT EXISTS alert_outcomes (  
        id INTEGER PRIMARY KEY AUTOINCREMENT,  
        mint TEXT,  
        symbol TEXT,  
        alerted_at TEXT,  
        checked_at TEXT,  
        check_window TEXT,  
        liq_at_alert REAL,  
        liq_at_check REAL,  
        liq_change_pct REAL,  
        price_at_alert TEXT,  
        price_at_check TEXT,  
        price_change_pct REAL,  
        survived INTEGER,  
        outcome_label TEXT  
    )  
""")  

cur.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_mint ON alert_outcomes(mint)")  
# ==========================================
# WHALE CACHE TABLE
# ==========================================

cur.execute("""
CREATE TABLE IF NOT EXISTS whale_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT,
    symbol TEXT,
    wallet TEXT,
    wallet_size REAL,
    liquidity REAL,
    wallet_ratio REAL,
    source TEXT,
    detected_at TEXT
)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_whale_cache_mint
ON whale_cache(mint)
""")

# =========================================
# V4 HISTORIAN SNAPSHOTS
# =========================================

cur.execute("""
CREATE TABLE IF NOT EXISTS coin_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT,
    symbol TEXT,
    age_min INTEGER,
    liquidity REAL,
    holders INTEGER,
    mcap REAL,
    judge_score INTEGER,
    judge_result TEXT,
    stage TEXT,
    snapshot_time TEXT
)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_snapshots_mint
ON coin_snapshots(mint)
""")
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

            logging.warning(
                f"DexScreener bad status: {res.status_code}"
            )

            return 0, None, None

        # ==========================================
        # SAFE JSON PARSE
        # ==========================================

        try:
            data = res.json() or {}

        except Exception:

            logging.warning(
                f"Invalid DexScreener JSON: {mint_address}"
            )

            return 0, None, None

        pairs = data.get("pairs") or []

        # ==========================================
        # SAFETY CHECK
        # ==========================================

        if not isinstance(pairs, list):

            logging.warning(
                f"Pairs not list: {mint_address}"
            )

            return 0, None, None

        if not pairs:

            logging.info(
                f"No pairs found: {mint_address}"
            )

            return 0, None, None

        # ==========================================
        # FILTER SOLANA PAIRS
        # ==========================================

        solana_pairs = [
            p for p in pairs
            if isinstance(p, dict)
            and p.get("chainId") == "solana"
        ]

        if not solana_pairs:

            logging.info(
                f"No Solana pairs: {mint_address}"
            )

            return 0, None, None

        best = max(
            solana_pairs,
            key=lambda x: float(
                x.get("liquidity", {}).get("usd") or 0
            )
        )

        real_liq = float(
            best.get("liquidity", {}).get("usd") or 0
        )

        dex_url = best.get("url")

        price_usd = best.get("priceUsd")

        return real_liq, dex_url, price_usd

    except Exception:

        logging.exception("DexScreener verify error")

        return 0, None, None

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

def build_telegram_message(
symbol,
liquidity,
volume,
price_change,
entry_label,
mint_address,
conviction_score,
shield_reason
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

return (  
    f"🚀 <b>Rocket Hunter Alert</b>\n\n"  
    f"{entry_label}\n"  
    f"🏷 Tag: 🧪 CONTROLLED OBSERVATION SIGNAL\n"  
    f"⏳ Survival Check Passed: {SURVIVAL_SECONDS} Seconds\n\n"  
    f"💎 <b>{clean_symbol} / SOL</b>\n"  
    f"🪪 Mint: <code>{short_mint}</code>\n\n"  
    f"💧 Liquidity: ${liquidity:,.0f}\n"  
    f"📊 Volume: ${volume:,.0f}\n"  
    f"{change_icon} Change: {price_change:.1f}%\n\n"  
    f"{risk}\n"  
    f"🛡️ Alpha Shield V3 | Score: {conviction_score}/100\n"  
    f"🧠 Result: <b>{shield_reason}</b>\n"  
    f"⚠️ DYOR. Early coins are high risk.\n"  
    f"✅ <i>Verified on DexScreener</i>"  
)
def send_discord_alert(message):
    try:
        if not DISCORD_WEBHOOK_URL:
            logging.warning("Discord webhook not configured")
            return False

        payload = {"content": message[:1900]}

        res = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10
        )

        if res.status_code in (200, 204):
            logging.info("✅ Discord Alert Sent")
            return True

        logging.error(f"Discord Error: {res.status_code} | {res.text}")
        return False

    except Exception as e:
        logging.error(f"Discord Exception: {e}")
        return False
def send_alert(
symbol,
liquidity,
volume,
dex_url,
gecko_url,
price_change,
entry_label,
mint_address,
conviction_score=0,
shield_reason=""
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
    f"🛡️ Alpha Shield V3 | Score: {conviction_score}/100\n"  
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
        send_discord_alert(message)
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
conviction_score=0,
reasons_json=None,
penalties_json=None,
tx_source=None
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
            conviction_score,  
            reasons_json,  
            penalties_json,  
            tx_source  
        )  
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)  
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
        conviction_score,  
        reasons_json,  
        penalties_json,  
        tx_source  
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

# POST-ALERT OUTCOME TRACKER

# ==========================================

Queue: list of dicts {mint, symbol, alerted_at, price_at_alert, liq_at_alert, checks_remaining}

OUTCOME_QUEUE = []
OUTCOME_LOCK  = threading.Lock()

CHECK_WINDOWS = [
("5m",  5  * 60),
("15m", 15 * 60),
("60m", 60 * 60),
]

def enqueue_outcome_tracking(mint, symbol, liq_at_alert, price_at_alert):
"""Call this right after a successful alert send."""
entry = {
"mint":           mint,
"symbol":         symbol,
"alerted_at":     datetime.utcnow().isoformat(),
"alerted_ts":     time.time(),
"liq_at_alert":   liq_at_alert,
"price_at_alert": price_at_alert or "0",
"checks_done":    [],   # list of window labels already saved
}
with OUTCOME_LOCK:
OUTCOME_QUEUE.append(entry)
logging.info(f"📋 Outcome tracking queued: {symbol}")

def outcome_tracker():
"""Background thread — checks queued alerts at 5m / 15m / 60m."""
logging.info("📋 Outcome Tracker started")

while True:  
    time.sleep(30)   # poll every 30s  

    now_ts  = time.time()  
    now_str = datetime.utcnow().isoformat()  

    with OUTCOME_LOCK:  
        queue_copy = list(OUTCOME_QUEUE)  

    to_remove = []  

    for entry in queue_copy:  
        elapsed = now_ts - entry["alerted_ts"]  

        for label, seconds in CHECK_WINDOWS:  
            if label in entry["checks_done"]:  
                continue  

            if elapsed < seconds:  
                continue  

            # Time to check this window  
            try:  
                real_liq, dex_url, price_now = verify_on_dexscreener(  
                    entry["mint"]  
                )  

                liq_alert = entry["liq_at_alert"] or 1  
                liq_change_pct = (  
                    (real_liq - liq_alert) / liq_alert * 100  
                    if liq_alert > 0 else 0  
                )  

                price_alert = float(entry["price_at_alert"] or 0)  
                price_now_f = float(price_now or 0)  
                price_change_pct = (  
                    (price_now_f - price_alert) / price_alert * 100  
                    if price_alert > 0 else 0  
                )  

                # Survived = liq still > 50% of original AND price > 50%  
                survived = int(  
                    real_liq >= liq_alert * 0.5  
                    and price_now_f >= price_alert * 0.5  
                )  

                outcome_label = "survived" if survived else "rugged"  

                with journal_db() as conn:  
                    conn.execute("""  
                        INSERT INTO alert_outcomes (  
                            mint, symbol, alerted_at, checked_at,  
                            check_window, liq_at_alert, liq_at_check,  
                            liq_change_pct, price_at_alert, price_at_check,  
                            price_change_pct, survived, outcome_label  
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)  
                    """, (  
                        entry["mint"],  
                        entry["symbol"],  
                        entry["alerted_at"],  
                        now_str,  
                        label,  
                        liq_alert,  
                        real_liq,  
                        round(liq_change_pct, 2),  
                        entry["price_at_alert"],  
                        str(price_now_f),  
                        round(price_change_pct, 2),  
                        survived,  
                        outcome_label  
                    ))  
                    conn.commit()  

                entry["checks_done"].append(label)  

                logging.info(  
                    f"📊 Outcome [{label}] {entry['symbol']} | "  
                    f"liq_chg={liq_change_pct:.1f}% | "  
                    f"price_chg={price_change_pct:.1f}% | "  
                    f"{outcome_label}"  
                )  

            except Exception:  
                logging.exception(f"Outcome check error: {entry['symbol']} [{label}]")  
                entry["checks_done"].append(label)  # skip on error  

        # Remove from queue when all 3 windows done  
        if len(entry["checks_done"]) >= len(CHECK_WINDOWS):  
            to_remove.append(entry)  

    if to_remove:  
        with OUTCOME_LOCK:  
            for e in to_remove:  
                try:  
                    OUTCOME_QUEUE.remove(e)  
                except ValueError:  
                    pass

# ==========================================

# /outcomes ENDPOINT

# ==========================================

@app.route("/outcomes")
def outcomes():
with journal_db() as conn:
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
SELECT symbol, check_window,
liq_change_pct, price_change_pct,
survived, outcome_label, checked_at
FROM alert_outcomes
ORDER BY id DESC
LIMIT 50
""")
rows = [dict(r) for r in cur.fetchall()]
return jsonify(rows), 200

@app.route("/survival_stats")
def survival_stats():
with journal_db() as conn:
cur = conn.cursor()

cur.execute("""  
        SELECT check_window,  
               COUNT(*) as total,  
               SUM(survived) as survived,  
               ROUND(AVG(price_change_pct), 2) as avg_price_chg,  
               ROUND(AVG(liq_change_pct), 2) as avg_liq_chg  
        FROM alert_outcomes  
        GROUP BY check_window  
    """)  
    rows = cur.fetchall()  

result = {}  
for r in rows:  
    window, total, surv, avg_p, avg_l = r  
    result[window] = {  
        "total":          total,  
        "survived":       surv,  
        "survival_rate":  round(surv / total * 100, 1) if total else 0,  
        "avg_price_chg":  avg_p,  
        "avg_liq_chg":    avg_l,  
    }  
return jsonify(result), 200

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

                # ── Timeframe: extract all separately ──  
                volume_m5  = float(vol_data.get("m5")  or 0)  
                volume_h1  = float(vol_data.get("h1")  or 0)  
                volume_h24 = float(vol_data.get("h24") or 0)  

                # Discovery: m5 must show live activity  
                # Fallback to h1/h24 only if m5 truly missing (new pool)  
                if volume_m5 >= 100:  
                    volume = volume_m5  
                elif volume_h1 > 0:  
                    volume = volume_h1  
                else:  
                    volume = volume_h24  

                if volume < MIN_VOLUME:  
                    continue  

                change_data = attr.get("price_change_percentage", {})  

                # Price change: m5 only — matches conviction engine  
                price_change_m5 = float(change_data.get("m5") or 0)  
                price_change = price_change_m5  

                # ── Transactions: strict m5, honest fallback ──  
                tx = attr.get("transactions", {})  

                tx_m5_raw  = tx.get("m5") or {}  
                tx_m15_raw = tx.get("m15") or {}  

                # Only use real m5 data for conviction engine  
                has_real_m5 = bool(  
                    tx_m5_raw.get("buys") or tx_m5_raw.get("sells")  
                )  
                has_real_m15 = bool(  
                    tx_m15_raw.get("buys") or tx_m15_raw.get("sells")  
                )  

                if has_real_m5:  
                    tx_source = tx_m5_raw  
                    tx_label  = "m5"  
                elif has_real_m15:  
                    tx_source = tx_m15_raw  
                    tx_label  = "m15_fallback"  
                else:  
                    # No recent activity — skip, not worth alerting  
                    logging.info(f"⏭️ No m5/m15 tx data: {symbol}")  
                    continue  

                logging.info(f"TX SOURCE: {tx_label}")  

                buys   = int(tx_source.get("buys")   or 0)  
                sells  = int(tx_source.get("sells")  or 0)  
                buyers = int(tx_source.get("buyers") or 0)  

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
                        "rejected",  
                        0,  
                        json.dumps([]),  
                        json.dumps(["low_dex_liquidity"]),  
                        tx_label  
                    )  

                    continue  

                pool_created_at_ms = pool_time.timestamp() * 1000.0  

                pair_data_v3 = {  
                    "baseToken": {  
                        "symbol": symbol,  
                        "address": mint_address,  
                    },  
                    "liquidity": {"usd": real_liq},  
                    "volume": {  
                        "m5":  volume_m5,  
                        "h24": volume_h24,  
                    },  
                    "pairCreatedAt": pool_created_at_ms,  
                    "txns": {  
                        "m5": {  
                            "buys":  buys,  
                            "sells": sells,  
                        }  
                    },  
                    "priceChange": {  
                        "m5": price_change_m5,  
                    },  
                    "fdv":      fdv,  
                    "labels":   attr.get("labels", []),  
                    "tx_label": tx_label,  
                }  

                (  
                    passed,  
                    shield_reason,  
                    _,  
                    conviction_score,  
                    reasons,  
                    penalties  
                ) = run_alpha_shield_v3(  
                    pair_data_v3,  
                    now_ts,  
                    buyers  
                )  

                logging.info(  
                    f"🛡️ V3: {symbol} | {shield_reason} | score={conviction_score}"  
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
                        "blocked",  
                        conviction_score,  
                        json.dumps(reasons),  
                        json.dumps(penalties),  
                        tx_label  
                    )  

                    logging.info(  
                        f"🚫 SHIELD BLOCKED: {symbol} | {shield_reason} | score={conviction_score}"  
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
                    mint_address,  
                    conviction_score,  
                    shield_reason  
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
                        shield_reason,  
                        True,  
                        "sent",  
                        conviction_score,  
                        json.dumps(reasons),  
                        json.dumps(penalties),  
                        tx_label  
                    )  

                    # ── Queue outcome tracking: 5m / 15m / 60m ──  
                    enqueue_outcome_tracking(  
                        mint_address,  
                        symbol,  
                        real_liq,  
                        _price_usd  
                    )  

                    alerts += 1  

                    time.sleep(3)  

                if alerts >= MAX_ALERTS_PER_SCAN:  
                    break  

            except Exception:  
                logging.exception("Pool Error")  

        logging.info(f"✅ Done | Alerts: {alerts}")  

        set_scan_state(  
            status="running",  
            last_alerts=alerts,  
            last_error=None  
        )  

    except Exception:  

        logging.exception("Scanner Error")  

        set_scan_state(  
            status="scanner_error",  
            last_alerts=alerts,  
            last_error="scanner_exception"  
        )  

    logging.info(f"⏳ Waiting {SCAN_INTERVAL}s...")  

    time.sleep(SCAN_INTERVAL)

# START ENGINE
# ====================================
if __name__ == "__main__":

    send_discord_alert("🚀 Captain Hook Test Message")

    Thread(target=scanner, daemon=True).start()

    Thread(target=outcome_tracker, daemon=True).start()

    app.run(
        host="0.0.0.0",
        port=PORT,
        use_reloader=False
    )
