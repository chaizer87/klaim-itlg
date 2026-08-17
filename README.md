# 🤖 Interlink Auto Claim Bot v3.0

```
 ██╗███╗   ██╗████████╗███████╗██╗          ██╗   ██╗ ██████╗ ████████╗███████╗
 ██║████╗  ██║╚══██╔══╝██╔════╝██║          ██║   ██║██╔═══██╗╚══██╔══╝██╔════╝
 ██║██╔██╗ ██║   ██║   █████╗  ██║          ██║   ██║██║   ██║   ██║   ███████╗
 ██║██║╚██╗██║   ██║   ██╔══╝  ██║          ╚██╗ ██╔╝██║   ██║   ██║   ╚════██║
 ██║██║ ╚████║   ██║   ███████╗███████╗     ╚████╔╝ ╚██████╔╝   ██║   ███████║
 ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚══════╝      ╚═══╝   ╚═════╝    ╚═╝   ╚══════╝
```

Auto-claim $ITLG dari Interlink Labs. Mining, group mining & recovery — fully automatic, crash-proof.

**Single Python script.** Login once with OTP, then it claims forever.

## ⚡ Quick Start

```bash
# Clone
git clone https://github.com/kaidev-pro/itlg-claim.git
cd itlg-claim

# Install
pip install requests

# Setup (interactive)
python3 setup.py

# Run!
python3 bot_v3.py
```

## 🔗 Referral

Mau daftar Interlink Labs? Pakai link referral gue 👇

**https://interlinklabs.ai/0454113933**

## 📋 Apa yang Kamu Butuhkan

| Field | Deskripsi | Contoh | Cara Dapat |
|-------|-----------|--------|------------|
| **loginId** | ID Interlink (angka, bukan email) | `0454113933` | Buka app → Profile |
| **passcode** | 6 digit angka | `221120` | Pilih saat sign up |
| **email** | Gmail terdaftar | `you@gmail.com` | Email saat signup |
| **imapPassword** | Gmail App Password (16 huruf) | `abcd efgh ijkl mnop` | [Buat di sini](https://myaccount.google.com/apppasswords) |
| **tgBotToken** | Token Telegram bot (opsional) | `123456:ABC-DEF...` | [@BotFather](https://t.me/BotFather) |
| **tgChatId** | User ID Telegram (opsional) | `123456789` | [@userinfobot](https://t.me/userinfobot) |

## 🎯 Commands

```bash
python3 bot_v3.py              # Loop mode (auto-claim forever)
python3 bot_v3.py --once       # Single run, check + claim, exit
python3 bot_v3.py --status     # Dashboard
python3 bot_v3.py --login      # Force login (OTP)
python3 bot_v3.py --stop       # Graceful stop
```

## 🤖 Fitur Bot v3.0

| Feature | Interval | Status |
|---------|----------|--------|
| Mining claim | 4 jam | ✅ Auto + human delay 10-120s |
| Group mining | 24 jam | ✅ Auto + human delay 30-120s |
| Recovery | Setiap cycle | ✅ Auto-check + claim |
| Token refresh | Auto | ✅ JWT auto-refresh |
| Telegram notif | Setiap claim | ✅ Claim + crash alert |
| Auto-restart | Crash handler | ✅ 50x retry, 30s delay |
| Anti-detection | Per claim | ✅ Random fingerprint |

## 📊 Status Output

```
  ╔══════════════════════════════════════╗
  ║  kai                                 ║
  ╠══════════════════════════════════════╣
  ║  Balance                       1795  ║
  ║  Last claim                  15 ITLG  ║
  ║  Per claim               15.0 ITLG  ║
  ║  Per day                 90.0 ITLG  ║
  ║  Group                      75/day  ║
  ║  Referral                   0 refs  ║
  ║  Streak/Burned               0 / 0  ║
  ╚══════════════════════════════════════╝
```

## 🔐 Anti-Detection

- **Random device fingerprint** — setiap akun dapat random phone model (Samsung, Xiaomi, Pixel, OPPO, dll)
- **Human-like timing** — tunggu 10-120 detik sebelum claim
- **No constant polling** — cek tiap 10 detik, bukan tiap 1 detik
- **Same endpoint as app** — pakai API yang sama dengan official app

## 🔄 Login Methods

### Method 1: OTP (Email)
```bash
python3 setup.py          # isi loginId, passcode, email, imapPassword
python3 bot_v3.py --login # kirim OTP ke email, auto grab
```

### Method 2: Face Photo
```bash
python3 setup.py --face   # isi loginId, passcode + selfie
python3 bot.py --login-face  # upload photo → face verify → login
```

## 📁 Files

```
bot_v3.py              # Bot v3.0 (custom)
bot.py                 # Bot v2.2 (original)
setup.py               # Interactive setup
config.json            # Config lo (gitignored)
token.json             # Saved token (gitignored)
claim_state.json       # Claim history (gitignored)
```

## ⚠️ Troubleshooting

### OTP Gak Sampai?
1. **Cek Spam/Junk** — Gmail kadang route ke Spam
2. **Tunggu 1-2 menit** — Interlink kadang lambat
3. **Verifikasi App Password** — harus App Password, bukan password Gmail
4. **Login dari app dulu** — buka Interlink app, login, lalu jalankan bot

### Bot Crash?
Auto-restart aktif (max 50 retries). Kalau gak recoverable, cek Telegram alert.

### Token Expired?
Bot auto-refresh. Kalau refresh gagal, running `python3 bot_v3.py --login`.

## 📈 ROI Calculator

| Timeframe | Per Claim | Daily (6x) | Weekly | Monthly |
|-----------|-----------|------------|--------|---------|
| Average | 15 ITLG | 90 ITLG | 630 ITLG | 2,700 ITLG |

> Mining gratis, cuma modal waktu & konsistensi.

## 📜 License

MIT

## ☕ Support

Kalau script-nya bermanfaat, kasih star ⭐ atau share ke teman!

Referral: **https://interlinklabs.ai/0454113933**

---

**Built with ❤️ by kaidev-pro**
