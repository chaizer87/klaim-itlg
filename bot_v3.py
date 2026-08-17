#!/usr/bin/env python3
"""
Interlink Labs Auto Claim Bot — Custom Version
Mining $ITLG automatically every 4 hours with Telegram notifications.

Features:
- Mining claim (4h cycle) — fully automatic
- Group mining (24h cycle) — auto
- Recovery (burned token reclaim) — every cycle
- Telegram notifications on every action
- Anti-detection: random fingerprint, human-like delays
- Auto-restart on crash (up to 50 retries)
- Token auto-refresh, auto-relogin

Usage:
  python bot.py              # Loop mode (auto-claim forever)
  python bot.py --once       # Single run then exit
  python bot.py --status     # Show dashboard
  python bot.py --login      # Force OTP login
  python bot.py --stop       # Graceful stop

Setup:
  Edit config.json with your credentials, then run.
"""

import sys, os, json, time, random, re, base64, hashlib, secrets
import imaplib, email
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    print("Run: pip install requests")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

VERSION = "3.0.0"
API_BASE = "https://prod.interlinklabs.ai/api/v1"
APP_VER = "5.0.5"
WIB = timezone(timedelta(hours=7))

MINING_INTERVAL = 4 * 3600   # 4 hours
GROUP_INTERVAL  = 24 * 3600  # 24 hours
OTP_TIMEOUT     = 180        # 3 min to grab OTP
OTP_POLL_DELAY  = 5          # seconds between IMAP checks
MAX_RETRIES     = 50         # auto-restart limit

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
TOKEN_FILE  = os.path.join(SCRIPT_DIR, "token.json")
STATE_FILE  = os.path.join(SCRIPT_DIR, "claim_state.json")
STOP_FILE   = os.path.join(SCRIPT_DIR, ".stop")
LOG_FILE    = os.path.join(SCRIPT_DIR, "bot.log")

# Device fingerprints (anti-detection)
DEVICES = [
    ("Redmi Note 8 Pro", "XiaoMi"), ("Redmi Note 11", "XiaoMi"),
    ("SM-G991B", "samsung"), ("SM-A525F", "samsung"),
    ("Pixel 6", "Google"), ("Pixel 7", "Google"),
    ("CPH2247", "OPPO"), ("V2057A", "vivo"),
    ("RMX3081", "Realme"), ("M2101K6G", "POCO"),
]

# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════

class Color:
    RST = "\033[0m"; BOLD = "\033[1m"
    RED = "\033[31m"; GRN = "\033[32m"
    YLW = "\033[33m"; CYN = "\033[36m"; DIM = "\033[2m"

ICONS = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️", "step": "➡️"}

def now_wib():
    return datetime.now(WIB)

def ts():
    return now_wib().strftime("%Y-%m-%d %H:%M:%S")

def log(level, msg):
    icon = ICONS.get(level, "ℹ️")
    line = f"{icon} [{ts()}] {msg}"
    # Terminal color
    color = {"ok": Color.GRN, "err": Color.RED, "warn": Color.YLW,
             "info": Color.DIM, "step": Color.CYN}.get(level, "")
    print(f"{color}{line}{Color.RST}")
    # File log
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
        # Trim to 500 lines
        with open(LOG_FILE) as f:
            lines = f.readlines()
        if len(lines) > 500:
            with open(LOG_FILE, "w") as f:
                f.writelines(lines[-500:])
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════
# CONFIG & STATE
# ═══════════════════════════════════════════════════════════════════════

def load_config():
    if not os.path.exists(CONFIG_FILE):
        log("err", "config.json not found! Run setup first.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    # Generate device ID if missing
    if not cfg.get("deviceId"):
        cfg["deviceId"] = secrets.token_hex(8)
        save_config(cfg)
    # Generate random device fingerprint if missing
    if not cfg.get("deviceModel"):
        dev = random.choice(DEVICES)
        cfg["deviceModel"] = dev[0]
        cfg["deviceBrand"] = dev[1]
        save_config(cfg)
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"history": [], "last_claim": 0, "balance": 0}

def save_state(claimed=None, balance=None):
    state = load_state()
    if claimed is not None:
        state["last_claim"] = claimed
        state["history"] = (state.get("history", []) + [claimed])[-10:]
    if balance is not None:
        state["balance"] = balance
    state["updated_at"] = int(time.time())
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ═══════════════════════════════════════════════════════════════════════
# TOKEN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def save_tokens(access, refresh):
    data = {"access": access, "refresh": refresh or "", "saved_at": int(time.time())}
    # Backup previous token
    if os.path.exists(TOKEN_FILE):
        try:
            import shutil
            shutil.copy2(TOKEN_FILE, os.path.join(SCRIPT_DIR, "token-backup.json"))
        except:
            pass
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    os.chmod(TOKEN_FILE, 0o600)

def load_tokens():
    try:
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        return data.get("access"), data.get("refresh")
    except:
        return None, None

def jwt_decode(token):
    """Decode JWT payload to get expiry."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except:
        return {}

def token_expired(token, buffer=300):
    exp = jwt_decode(token).get("exp")
    if not exp:
        return True
    return time.time() >= (exp - buffer)

# ═══════════════════════════════════════════════════════════════════════
# HTTP LAYER
# ═══════════════════════════════════════════════════════════════════════

def make_headers(cfg, token=None):
    """Build request headers mimicking Android app."""
    h = {
        "User-Agent": "okhttp/4.12.0",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip",
        "version": APP_VER,
        "x-platform": "android",
        "x-model": cfg.get("deviceModel", "Redmi Note 8 Pro"),
        "x-brand": cfg.get("deviceBrand", "XiaoMi"),
        "x-system-name": "Android",
        "x-bundle-id": "org.ai.interlinklabs.interlinkId",
        "x-unique-id": cfg["deviceId"],
        "x-device-id": cfg["deviceId"],
        "x-date": str(int(time.time() * 1000)),
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def api_get(path, token, cfg, params=None):
    r = requests.get(f"{API_BASE}{path}", params=params,
                     headers=make_headers(cfg, token), verify=False, timeout=30)
    return r.json() if r.status_code == 200 else {}

def api_post(path, data, token=None, cfg=None):
    body = json.dumps(data) if isinstance(data, dict) else str(data)
    headers = make_headers(cfg, token)
    headers["x-content-hash"] = base64.b64encode(
        hashlib.sha256(body.encode()).digest()
    ).decode()
    r = requests.post(f"{API_BASE}{path}", data=body,
                      headers=headers, verify=False, timeout=30)
    return r.json() if r.status_code in (200, 201) else {}

# ═══════════════════════════════════════════════════════════════════════
# AUTH — Login, Refresh, Session
# ═══════════════════════════════════════════════════════════════════════

def check_login_id(cfg):
    r = api_get(f"/auth/loginId-exist-check/{cfg['loginId']}", None, cfg)
    return r.get("statusCode") == 200

def check_passcode(cfg):
    r = api_post("/auth/check-passcode?v=2", {
        "loginId": str(cfg["loginId"]),
        "passcode": str(cfg["passcode"]),
        "deviceId": cfg["deviceId"]
    }, cfg=cfg)
    if r.get("statusCode") == 200:
        data = r.get("data", {})
        return data.get("email") or (data.get("verificationInfo") or [{}])[0].get("gmail")
    return None

def send_otp(cfg, email_addr):
    r = api_post("/auth/send-otp-email-verify-login", {
        "loginId": str(cfg["loginId"]),
        "passcode": str(cfg["passcode"]),
        "email": email_addr,
        "deviceId": cfg["deviceId"]
    }, cfg=cfg)
    return r.get("statusCode") == 200

def grab_otp(cfg, email_addr, after_ts):
    """Poll IMAP inbox for login OTP code."""
    time.sleep(5)
    deadline = time.time() + OTP_TIMEOUT
    while time.time() < deadline:
        mail = None
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email_addr, cfg["imapPassword"])
            mail.select("inbox")
            _, msgs = mail.search(None, "ALL")
            for eid in reversed(msgs[0].split()[-10:]):
                _, msg_data = mail.fetch(eid, "(RFC822)")
                for part in msg_data:
                    if not isinstance(part, tuple):
                        continue
                    msg = email.message_from_bytes(part[1])
                    try:
                        if parsedate_to_datetime(msg.get("Date", "")).timestamp() < after_ts - 30:
                            continue
                    except:
                        pass
                    subj = str(msg.get("Subject", "")).lower()
                    if "login" not in subj and "verification" not in subj:
                        continue
                    body = ""
                    if msg.is_multipart():
                        for p in msg.walk():
                            ct = p.get_content_type()
                            if ct == "text/plain":
                                try: body = p.get_payload(decode=True).decode(errors="ignore")
                                except: pass
                            elif ct == "text/html" and not body:
                                try: body = p.get_payload(decode=True).decode(errors="ignore")
                                except: pass
                    else:
                        try: body = msg.get_payload(decode=True).decode(errors="ignore")
                        except: pass
                    codes = re.findall(r"\b(\d{6})\b", body)
                    if codes:
                        return codes[0]
        except Exception as e:
            log("warn", f"IMAP error: {e}")
        finally:
            if mail:
                try: mail.logout()
                except: pass
        time.sleep(OTP_POLL_DELAY)
    return None

def verify_otp(cfg, otp):
    r = api_post("/auth/check-otp-email-verify-login?v=2", {
        "loginId": str(cfg["loginId"]),
        "otp": otp,
        "deviceId": cfg["deviceId"]
    }, cfg=cfg)
    if r.get("statusCode") == 200:
        data = r.get("data", {})
        return data.get("accessToken"), data.get("refreshToken")
    return None, None

def do_login(cfg):
    """Full OTP login flow. Returns (access, refresh) or (None, None)."""
    log("step", "Checking login ID...")
    if not check_login_id(cfg):
        log("err", f"Login ID {cfg['loginId']} not found.")
        return None, None

    log("step", "Checking passcode...")
    email_addr = check_passcode(cfg)
    if not email_addr and not cfg.get("email"):
        log("err", "Passcode wrong and no email in config.")
        return None, None
    email_addr = email_addr or cfg["email"]
    log("ok", f"Email: {email_addr}")

    if not cfg.get("imapPassword"):
        log("err", "imapPassword not set in config.json")
        return None, None

    for attempt in range(3):
        send_ts = time.time()
        log("step", f"Sending OTP (attempt {attempt+1}/3)...")
        if not send_otp(cfg, email_addr):
            time.sleep(5)
            continue
        log("info", "Waiting for OTP email...")
        otp = grab_otp(cfg, email_addr, send_ts)
        if not otp:
            continue
        log("step", f"Verifying OTP {otp}...")
        access, refresh = verify_otp(cfg, otp)
        if access:
            log("ok", "Login successful!")
            save_tokens(access, refresh)
            return access, refresh
        log("warn", "OTP expired, resending...")

    log("err", "Login failed after 3 attempts.")
    return None, None

def do_refresh(cfg, refresh_token):
    if not refresh_token:
        return None
    log("step", "Refreshing token...")
    r = api_post("/auth/token", {"refreshToken": refresh_token}, cfg=cfg)
    if r.get("statusCode") == 200:
        data = r.get("data", {})
        new_access = data.get("accessToken") or data.get("jwtToken")
        new_refresh = data.get("refreshToken")
        if new_access:
            log("ok", "Token refreshed.")
            save_tokens(new_access, new_refresh or refresh_token)
            return new_access
    return None

def get_session(cfg, allow_login=True):
    """Get valid token: stored → refresh → OTP login."""
    access, refresh = load_tokens()
    if access and not token_expired(access):
        return access
    if refresh:
        new_access = do_refresh(cfg, refresh)
        if new_access:
            return new_access
    if not allow_login:
        log("warn", "No valid token. Run: python bot.py --login")
        return None
    log("warn", "No valid token. Triggering OTP login...")
    access, refresh = do_login(cfg)
    return access

def ensure_token(cfg, token, buffer=300):
    """Validate token, refresh if needed, relogin if necessary."""
    if not token:
        return get_session(cfg)
    remaining = (jwt_decode(token).get("exp") or 0) - time.time()
    if remaining > buffer:
        return token
    # Token expiring → refresh
    _, refresh = load_tokens()
    if refresh:
        log("warn", f"Token expiring in {max(0,int(remaining/60))}min, refreshing...")
        new_access = do_refresh(cfg, refresh)
        if new_access:
            return new_access
    # Refresh failed → alert via Telegram
    send_tg(cfg, "⚠️ <b>ITLG Bot</b>\nToken expired! Run: python bot.py --login")
    log("err", "Token expired, refresh failed. Manual login needed.")
    return None

# ═══════════════════════════════════════════════════════════════════════
# TELEGRAM NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════

def send_tg(cfg, html_text):
    token = cfg.get("tgBotToken", "")
    chat_id = cfg.get("tgChatId", "")
    if not token or not chat_id:
        return
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat_id, "text": html_text, "parse_mode": "HTML"
        }, timeout=10)
        if r.status_code == 200:
            log("ok", "Telegram sent.")
    except Exception as e:
        log("warn", f"Telegram error: {e}")

def tg_claim(cfg, claimed, before, after, rate_claim, rate_day, group_rate):
    now = now_wib().strftime("%H:%M WIB")
    day_line = f"\n📈 Per day: ~{rate_day} ITLG" if rate_day else ""
    group_line = f"\n👥 Group: {group_rate}/day" if group_rate > 0 else ""
    text = (
        f"✅ ITLG Claim Success\n\n"
        f"💰 Claimed: +{claimed} ITLG\n"
        f"📊 Balance: {before} → {after} ITLG\n"
        f"⏱️ Per claim: {rate_claim} ITLG{day_line}{group_line}\n"
        f"🕐 {now}\n\n"
        f"Next claim in 4h."
    )
    send_tg(cfg, text)

# ═══════════════════════════════════════════════════════════════════════
# API — User Info, Balance, Claimable
# ═══════════════════════════════════════════════════════════════════════

def get_user_info(token, cfg):
    r = api_get("/auth/current-user-full?include=userInfo,token,isClaimable", token, cfg)
    return r.get("data") if r.get("statusCode") == 200 else None

def get_balance(token, cfg):
    data = get_user_info(token, cfg)
    return data.get("token", {}).get("interlinkGoldTokenAmount", 0) if data else None

def check_claimable(token, cfg):
    r = api_get("/token/check-is-claimable", token, cfg)
    return r.get("data", {})

# ═══════════════════════════════════════════════════════════════════════
# MINING CLAIM (4h cycle)
# ═══════════════════════════════════════════════════════════════════════

def trigger_ads(token, cfg, last_claim):
    try:
        r = api_get(f"/token/get-random-ads-mining-new?totalHhp=1&lastTimeClaim={last_claim}", token, cfg)
        return r.get("data", {}).get("timeRetry", 10) or 10
    except:
        return 10

def claim_airdrop(token, cfg):
    return api_post("/token/claim-airdrop", {}, token=token, cfg=cfg)

def attempt_mining_claim(cfg, token):
    """Try mining claim. Returns (token, claimed_bool)."""
    ic = check_claimable(token, cfg)
    if not ic.get("isClaimable"):
        nf = ic.get("nextFrame")
        if nf:
            remain = max(0, int((nf - time.time() * 1000) / 1000))
            log("info", f"Not claimable. Next in {fmt_cd(remain)}")
        return token, False

    # Human-like delay
    jitter = random.randint(30, 120)
    log("info", f"Claimable! Waiting {jitter}s (human-like)...")
    time.sleep(jitter)

    balance_before = get_balance(token, cfg)
    user = get_user_info(token, cfg)
    if not user:
        return token, False
    ti = user.get("token", {})
    last_claim = ti.get("lastClaimTime") or int(time.time() * 1000)
    group_rate = ti.get("groupMiningRate", 0) or 0

    # Trigger ads
    log("ok", "Triggering ads...")
    wait = trigger_ads(token, cfg, last_claim)
    time.sleep(wait + 5)

    # Claim
    log("step", "Claiming...")
    result = claim_airdrop(token, cfg)
    status = result.get("statusCode")

    if status == 200:
        time.sleep(2)
        balance_after = get_balance(token, cfg)
        claimed = (balance_after - balance_before) if balance_before and balance_after else None
        state = load_state()
        avg_per_claim = sum(state["history"][-10:]) / max(len(state["history"][-10:]), 1) if state["history"] else claimed
        per_day = round(avg_per_claim * 6, 1) if avg_per_claim else None
        save_state(claimed=claimed, balance=balance_after)
        log("ok", f"Claimed! +{claimed} ITLG | Balance: {balance_before} → {balance_after}")
        tg_claim(cfg, claimed, balance_before, balance_after, avg_per_claim, per_day, group_rate)
        return token, True

    if status == 400 and "TOO_EARLY" in str(result.get("message", "")).upper():
        log("info", "Already claimed. Syncing timer...")
        ic2 = check_claimable(token, cfg)
        nf = ic2.get("nextFrame")
        if nf:
            log("info", f"Next claim in {fmt_cd(max(0, int((nf - time.time() * 1000) / 1000)))}")
        return token, False

    if status == 500:
        log("warn", "Server error, retrying in 10s...")
        time.sleep(10)
        result2 = claim_airdrop(token, cfg)
        if result2.get("statusCode") == 200:
            time.sleep(2)
            balance_after = get_balance(token, cfg)
            claimed = (balance_after - balance_before) if balance_before and balance_after else None
            save_state(claimed=claimed, balance=balance_after)
            log("ok", f"Claimed on retry! +{claimed} ITLG")
            return token, True

    log("err", f"Claim failed ({status}): {result.get('message', '')}")
    return token, False

# ═══════════════════════════════════════════════════════════════════════
# GROUP MINING (24h cycle)
# ═══════════════════════════════════════════════════════════════════════

def attempt_group_claim(cfg, token):
    """Check + claim group mining. Returns (token, claimed, next_time_ms)."""
    r = api_post("/group-mining/get-list-group-mining", {}, token=token, cfg=cfg)
    if r.get("statusCode") != 200:
        return token, False, None

    data = r.get("data", {})
    groups = data.get("groups", [])
    next_time = data.get("nextTimeClaim")
    already_claimed = data.get("requesterHasClaimedToday", False)

    # Find claimable group
    claimable = None
    total_reward = 0
    for g in groups:
        total_reward += g.get("totalReward", 0)
        if g.get("canClaim"):
            claimable = g
            break

    if not claimable:
        if already_claimed:
            log("info", f"Group: already claimed today. {len(groups)} groups, pool: {total_reward}")
        else:
            log("info", f"Group: not ready. {len(groups)} groups, pool: {total_reward}")
        return token, False, next_time

    gid = claimable["groupId"]
    log("ok", f"Group claimable! Group: {gid}")

    jitter = random.randint(30, 120)
    log("info", f"Waiting {jitter}s before group claim...")
    time.sleep(jitter)

    balance_before = get_balance(token, cfg)
    r2 = api_post("/group-mining/claim-group-mining", {"groupId": gid}, token=token, cfg=cfg)
    if r2.get("statusCode") == 200:
        time.sleep(2)
        balance_after = get_balance(token, cfg)
        claimed = (balance_after - balance_before) if balance_before and balance_after else None
        log("ok", f"Group claimed! +{claimed} ITLG | Balance: {balance_before} → {balance_after}")
        send_tg(cfg, f"👥 Group Mining Claimed!\n💰 +{claimed} ITLG\n📊 {balance_before} → {balance_after}")
        return token, True, next_time

    if r2.get("statusCode") == 400 and "ALREADY" in str(r2.get("message", "")).upper():
        log("info", "Group: already claimed.")
        return token, False, next_time

    log("err", f"Group claim failed: {r2.get('message', '')}")
    return token, False, next_time

# ═══════════════════════════════════════════════════════════════════════
# RECOVERY (burned token reclaim)
# ═══════════════════════════════════════════════════════════════════════

def attempt_recovery(cfg, token):
    """Check + claim recoverable burned tokens. Returns (token, recovered_amount)."""
    r = api_get("/recovery/total-recoverable", token, cfg)
    if r.get("statusCode") != 200:
        return token, 0

    data = r.get("data", {})
    can_recover = data.get("canRecover", False)
    total = data.get("totalRecoverable", 0)

    if not can_recover or total <= 0:
        return token, 0

    log("ok", f"Recovery available! {total} ITLG recoverable.")

    # Get burn list
    r2 = api_get("/recovery/my", token, cfg)
    if r2.get("statusCode") != 200:
        return token, 0
    burns = [b for b in r2.get("data", {}).get("data", []) if b.get("isRecoverable")]
    if not burns:
        return token, 0

    balance_before = get_balance(token, cfg)
    recovered = 0
    for burn in burns:
        tid = burn.get("transactionId")
        if not tid:
            continue
        amt = burn.get("amount", 0)
        log("step", f"Recovering {amt} ITLG from {tid}...")
        r3 = api_post("/recovery/claim", {"transactionId": tid}, token=token, cfg=cfg)
        if r3.get("statusCode") in (200, 201):
            recovered += amt
            log("ok", f"Recovered +{amt} ITLG")
            time.sleep(2)
        else:
            log("warn", f"Recovery failed for {tid}: {r3.get('message', '')}")

    if recovered > 0:
        balance_after = get_balance(token, cfg)
        log("ok", f"Recovery complete! +{recovered} ITLG | {balance_before} → {balance_after}")
        send_tg(cfg, f"🔄 Recovery Complete!\n💰 +{recovered} ITLG recovered\n📊 {balance_before} → {balance_after}")

    return token, recovered

# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

def fmt_cd(seconds):
    """Format countdown: '2h 15m 30s'."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"

def show_dashboard(token, cfg):
    data = get_user_info(token, cfg)
    if not data:
        log("err", "Failed to fetch user info.")
        return None

    ui = data.get("userInfo", {})
    ti = data.get("token", {})
    ic = data.get("isClaimable", {})
    state = load_state()
    gold = ti.get("interlinkGoldTokenAmount", 0)
    total_ref = ti.get("totalReferral", 0)
    streak = ti.get("burningStreak", 0)
    burned = ti.get("burnedCycles", 0)
    recoverable = ti.get("itlgRecoverable", 0)
    group_rate = ti.get("groupMiningRate", 0) or 0

    history = state.get("history", [])
    avg = round(sum(history) / len(history), 1) if history else 0
    per_day = round(avg * 6, 1) if avg else 0

    W = 38
    print()
    print(f"  {Color.BOLD}╔{'═'*W}╗{Color.RST}")
    print(f"  {Color.BOLD}║{Color.RST}  {ui.get('username', 'N/A')[:30]:<34}  {Color.BOLD}║{Color.RST}")
    print(f"  {Color.BOLD}╠{'═'*W}╣{Color.RST}")
    print(f"  {Color.BOLD}║{Color.RST}  Balance        {gold:>28}  {Color.BOLD}║{Color.RST}")
    print(f"  {Color.BOLD}║{Color.RST}  Last claim     {str(state.get('last_claim', 0)) + ' ITLG':>28}  {Color.BOLD}║{Color.RST}")
    if avg:
        print(f"  {Color.BOLD}║{Color.RST}  Per claim      {str(avg) + ' ITLG':>28}  {Color.BOLD}║{Color.RST}")
        print(f"  {Color.BOLD}║{Color.RST}  Per day        {str(per_day) + ' ITLG':>28}  {Color.BOLD}║{Color.RST}")
    else:
        print(f"  {Color.BOLD}║{Color.RST}  Per claim      {'waiting first claim':>28}  {Color.BOLD}║{Color.RST}")
    print(f"  {Color.BOLD}║{Color.RST}  Group          {str(group_rate) + '/day':>28}  {Color.BOLD}║{Color.RST}")
    print(f"  {Color.BOLD}║{Color.RST}  Referral       {str(total_ref) + ' refs':>28}  {Color.BOLD}║{Color.RST}")
    print(f"  {Color.BOLD}║{Color.RST}  Streak/Burned  {f'{streak} / {burned}':>28}  {Color.BOLD}║{Color.RST}")
    if recoverable and recoverable > 0:
        print(f"  {Color.BOLD}║{Color.RST}  Recoverable    {str(recoverable) + ' ITLG':>28}  {Color.BOLD}║{Color.RST}")
    print(f"  {Color.BOLD}╚{'═'*W}╝{Color.RST}")
    return ic

# ═══════════════════════════════════════════════════════════════════════
# RUN MODES
# ═══════════════════════════════════════════════════════════════════════

def run_once(cfg):
    token = get_session(cfg, allow_login=False)
    if not token:
        return
    ic = show_dashboard(token, cfg)
    if ic and ic.get("isClaimable"):
        attempt_mining_claim(cfg, token)
    # Group mining
    log("info", "Checking group mining...")
    attempt_group_claim(cfg, token)
    # Recovery
    log("info", "Checking recovery...")
    attempt_recovery(cfg, token)

def run_loop(cfg):
    log("info", f"Starting Interlink Bot v{VERSION} (mining 4h + group 24h)")
    token = get_session(cfg)
    if not token:
        log("err", "No valid token. Run: python bot.py --login")
        raise RuntimeError("No valid token")

    # Initial checks
    ic = show_dashboard(token, cfg)
    if ic and ic.get("isClaimable"):
        token, _ = attempt_mining_claim(cfg, token)
    token, _, group_next = attempt_group_claim(cfg, token)
    token, recovered = attempt_recovery(cfg, token)

    # Get timers
    ic = check_claimable(token, cfg)
    mining_next = ic.get("nextFrame") or (time.time() * 1000 + MINING_INTERVAL * 1000)
    if not group_next:
        group_next = time.time() * 1000 + GROUP_INTERVAL * 1000

    log("info", f"Mining next: {fmt_cd(max(0,(mining_next - time.time()*1000)/1000))}")
    log("info", f"Group next:  {fmt_cd(max(0,(group_next - time.time()*1000)/1000))}")

    while True:
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)
            log("info", "Stop signal received. Exiting.")
            return

        now_ms = time.time() * 1000
        mining_rem = max(0, (mining_next - now_ms) / 1000)
        group_rem = max(0, (group_next - now_ms) / 1000)

        if mining_rem > 0 or group_rem > 0:
            print(f"\r  {Color.CYN}⏰ Mining: {fmt_cd(mining_rem)} | Group: {fmt_cd(group_rem)}{Color.RST}     ", end="", flush=True)

        # Mining claim
        if mining_rem <= 0:
            print()
            log("step", "Mining claim time!")
            time.sleep(random.randint(10, 60))
            token = ensure_token(cfg, token)
            if token:
                token, claimed = attempt_mining_claim(cfg, token)
                if claimed:
                    attempt_recovery(cfg, token)
                ic = check_claimable(token, cfg)
                mining_next = ic.get("nextFrame") or (time.time() * 1000 + MINING_INTERVAL * 1000)

        # Group mining
        if group_rem <= 0:
            print()
            log("step", "Group mining time!")
            time.sleep(random.randint(10, 60))
            token = ensure_token(cfg, token)
            if token:
                token, _, group_next = attempt_group_claim(cfg, token)
                if not group_next:
                    group_next = time.time() * 1000 + GROUP_INTERVAL * 1000

        time.sleep(10)

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(f"Interlink $ITLG Auto Claim Bot v{VERSION}")
    parser.add_argument("--once", action="store_true", help="Single run then exit")
    parser.add_argument("--status", action="store_true", help="Show dashboard")
    parser.add_argument("--login", action="store_true", help="Force OTP login")
    parser.add_argument("--stop", action="store_true", help="Stop the bot")
    args = parser.parse_args()

    if args.stop:
        with open(STOP_FILE, "w") as f:
            f.write("stop")
        log("ok", "Stop signal sent.")
        return

    cfg = load_config()

    if args.login:
        log("step", "Forcing login...")
        access, refresh = do_login(cfg)
        if access:
            log("ok", "Login successful! Token saved.")
        else:
            log("err", "Login failed.")
        return

    if args.status:
        token = get_session(cfg, allow_login=False)
        if token:
            show_dashboard(token, cfg)
        else:
            log("err", "No valid token. Run: python bot.py --login")
        return

    if args.once:
        run_once(cfg)
        return

    # Loop mode with auto-restart
    log("ok", f"Interlink Auto Claim Bot v{VERSION}")
    retries = 0
    while retries < MAX_RETRIES:
        try:
            run_loop(cfg)
            return  # Normal exit (stop signal)
        except KeyboardInterrupt:
            log("info", "Interrupted. Exiting.")
            return
        except Exception as e:
            retries += 1
            log("err", f"Crash ({retries}/{MAX_RETRIES}): {e}")
            send_tg(cfg, f"⚠️ ITLG Bot crashed! ({retries}/{MAX_RETRIES})\nAuto-restarting...")
            time.sleep(30)

    log("err", f"Max retries ({MAX_RETRIES}) reached. Stopping.")
    send_tg(cfg, f"❌ ITLG Bot stopped after {MAX_RETRIES} crashes!")

if __name__ == "__main__":
    import argparse
    main()
