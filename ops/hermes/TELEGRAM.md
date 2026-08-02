# AutoCliper Telegram Bot — Panduan Setup

Bot Telegram yang terhubung ke Hermes agent untuk mengontrol AutoCliper:
mencari video viral, submit ke pipeline, memantau progress, dan ganti model LLM.

---

## Arsitektur

```
Telegram User
     ↓ pesan
Telegram Bot (ops/telegram/telegram_bot.py)
     ↓ /viral, /submit, /status → direct tool call (cepat)
     ↓ pesan bebas → hermes run --yes (agentic)
Hermes Agent (gateway:9119, toolset: autocliper)
     ↓ tool calls
AutoCliper API (FastAPI :8000)
     ↓
Pipeline (download → transkrip → AI → render)
     ↓ hasil
Telegram User (notifikasi job selesai)
```

---

## Step 1: Buat Bot di Telegram

1. Buka Telegram, cari **@BotFather**
2. Kirim `/newbot`
3. Ikuti instruksi, beri nama dan username bot
4. Copy **token** yang diberikan (format: `1234567890:ABCdefGHI...`)

---

## Step 2: Konfigurasi

Edit `$HERMES_HOME/.env` (default: `~/.hermes/.env`):

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNO...
TELEGRAM_ALLOWED_USERS=123456789,987654321   # Telegram User ID, pisah koma

# AutoCliper API
AUTOCLIPER_API_URL=http://127.0.0.1:8000/api
AUTOCLIPER_EMAIL=admin@autocliper.com        # Email login AutoCliper
AUTOCLIPER_PASSWORD=YourSecurePassword123!  # Password login AutoCliper
```

> **Cara dapat Telegram User ID:**
> 1. Kirim pesan ke **@userinfobot**
> 2. Atau jalankan bot dulu, kirim `/myid` — bot akan balas dengan ID kamu

---

## Step 3: Deploy

### Cara Cepat (manual)

```bash
# Dari root project di server
bash scripts/setup-telegram-bot.sh
```

Script ini akan:
- Install Python dependencies (python-telegram-bot, httpx)
- Sync Hermes config + AutoCliper toolset
- Install dan start systemd service `autocliper-telegram-bot`

### Manual (tanpa systemd)

```bash
cd ops/telegram
python3 -m venv venv
venv/bin/pip install -r requirements.txt
HERMES_HOME=~/.hermes venv/bin/python telegram_bot.py
```

---

## Step 4: Verifikasi

```bash
# Cek service berjalan
systemctl status autocliper-telegram-bot

# Lihat log
journalctl -u autocliper-telegram-bot -f

# Test di Telegram
/start
/myid
/help
```

---

## Perintah Bot

| Perintah | Fungsi |
|---|---|
| `/start` | Welcome message + ringkasan perintah |
| `/help` | Panduan lengkap |
| `/myid` | Tampilkan Telegram User ID kamu |
| `/viral <topik>` | Cari video YouTube viral |
| `/viral <topik> --limit 10` | Cari dengan jumlah hasil lebih banyak |
| `/viral <topik> --lang id` | Filter konten bahasa Indonesia |
| `/submit <url>` | Submit YouTube URL ke pipeline |
| `/submit <url> --style viral --ratio 9:16` | Submit dengan opsi |
| `/submit <url> --force` | Proses ulang URL yang sudah pernah diproses |
| `/status <job_id>` | Cek progress job |
| `/jobs` | List 10 job terbaru |
| `/jobs --status completed` | Filter job selesai |
| `/model grok` | Ganti ke Grok 4.5 High |
| `/model gemini` | Ganti ke Gemini 2.5 Pro |
| `/model gpt-4o` | Ganti ke GPT-4o |
| `/model llama` | Ganti ke Llama 70B (Groq) |
| `/model cliperhub` | Ganti ke 9router CliperHub |

**Agentic mode** — ketik pesan bebas, Hermes akan analisis dan eksekusi:

> "Carikan 5 video tentang trading crypto terbaru, pilih yang paling viral dan proses langsung"

> "Status semua job yang sedang berjalan"

> "Ganti ke model yang paling hemat tapi tetap bagus untuk analisis konten"

---

## Model LLM yang Tersedia

| Alias | Model Lengkap | Keterangan |
|---|---|---|
| `grok` / `grok-high` | `gcli/grok-4.5-high` | Default, terbaik untuk analisis |
| `grok-fast` | `gcli/grok-4.5-fast` | Lebih cepat, biaya lebih rendah |
| `gemini` / `gemini-pro` | `gcli/gemini-2.5-pro` | Google Gemini Pro |
| `gemini-flash` | `gcli/gemini-2.5-flash` | Gemini cepat |
| `gpt-4o` | `openai/gpt-4o` | OpenAI GPT-4o |
| `llama` | `groq/llama-3.3-70b` | Llama via Groq (gratis) |
| `cliperhub` | `CliperHub` | 9router model combo |

---

## Troubleshooting

**Bot tidak merespons:**
```bash
journalctl -u autocliper-telegram-bot -f
# Cek TELEGRAM_BOT_TOKEN sudah benar
```

**"Akses ditolak":**
```bash
# Kirim /myid ke bot untuk dapat User ID kamu
# Tambahkan ke TELEGRAM_ALLOWED_USERS di ~/.hermes/.env
# Restart: systemctl restart autocliper-telegram-bot
```

**Tool `hermes` tidak ditemukan (agentic mode gagal):**
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
# Atau cek: which hermes
```

**`autocliper_job_status` error — tidak bisa login:**
```bash
# Pastikan AUTOCLIPER_EMAIL dan AUTOCLIPER_PASSWORD di ~/.hermes/.env benar
# Test manual:
HERMES_HOME=~/.hermes python3 ~/.hermes/skills/bin/ac_list_jobs.py
```

**Sync ulang toolset setelah update:**
```bash
bash scripts/sync-hermes-config.sh
systemctl restart autocliper-telegram-bot
```

---

## File Structure

```
ops/
├── hermes/
│   ├── config.yaml              # Hermes config (toolsets: autocliper)
│   ├── env.example              # Template env vars
│   ├── autocliper_tools.yaml    # Custom toolset definition
│   ├── TELEGRAM.md              # Dokumen ini
│   └── bin/                     # CLI scripts (di-copy ke HERMES_HOME/skills/bin/)
│       ├── ac_auth.py           # Shared JWT auth helper
│       ├── ac_viral_search.py   # Cari video viral
│       ├── ac_submit_job.py     # Submit job ke pipeline
│       ├── ac_job_status.py     # Cek progress job
│       ├── ac_list_jobs.py      # List jobs
│       └── ac_switch_model.py   # Ganti model LLM
└── telegram/
    ├── telegram_bot.py          # Bot utama
    └── requirements.txt         # python-telegram-bot, httpx

scripts/
├── sync-hermes-config.sh        # Sync config + toolset ke HERMES_HOME
└── setup-telegram-bot.sh        # Install + deploy bot sebagai systemd service
```
