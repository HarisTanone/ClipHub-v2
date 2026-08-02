"""
AutoCliper Telegram Bot — Relay ke Hermes
==========================================
Bot ini bertindak sebagai interface Telegram untuk Hermes agent.
Setiap pesan dari user authorized diteruskan ke hermes CLI sebagai prompt,
dan responnya dikirim balik ke Telegram.

Fitur:
- /start, /help           — onboarding
- /model <nama>           — ganti model LLM
- /viral <topik>          — cari video YouTube viral
- /jobs                   — list job terbaru
- /status <job_id>        — cek status job
- /submit <url>           — submit YouTube URL
- Pesan bebas             → diteruskan ke hermes sebagai prompt (agentic mode)

Setup:
    1. Set TELEGRAM_BOT_TOKEN dan TELEGRAM_ALLOWED_USERS di $HERMES_HOME/.env
    2. pip install python-telegram-bot httpx
    3. python telegram_bot.py
"""
import asyncio
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path

# ─── Load .env dari HERMES_HOME ───────────────────────────────────────────────
_hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
_env_file = os.path.join(_hermes_home, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

try:
    from telegram import Update
    from telegram.constants import ChatAction, ParseMode
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    print("ERROR: python-telegram-bot tidak terinstall.")
    print("Install: pip install 'python-telegram-bot>=20.0'")
    sys.exit(1)

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# Comma-separated Telegram user IDs yang diizinkan
ALLOWED_USERS_RAW = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
ALLOWED_USERS: set[int] = set()
for uid in ALLOWED_USERS_RAW.split(","):
    uid = uid.strip()
    if uid.isdigit():
        ALLOWED_USERS.add(int(uid))

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")
HERMES_HOME = _hermes_home
AUTOCLIPER_API_URL = os.environ.get("AUTOCLIPER_API_URL", "http://127.0.0.1:8000/api")

# Timeout untuk hermes run (detik) — agentic tasks bisa lama
HERMES_TIMEOUT = int(os.environ.get("HERMES_TIMEOUT", "300"))
# Maks panjang pesan Telegram (4096 karakter)
MAX_MSG_LEN = 4000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("autocliper_bot")


# ─── Auth Guard ───────────────────────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True  # Kalau tidak dikonfigurasi, semua bisa (hati-hati!)
    return update.effective_user.id in ALLOWED_USERS


async def deny(update: Update):
    uid = update.effective_user.id
    logger.warning(f"Unauthorized access attempt: user_id={uid}")
    await update.message.reply_text(
        f"⛔ Akses ditolak. User ID kamu: `{uid}`\n"
        "Tambahkan ID ini ke `TELEGRAM_ALLOWED_USERS` di `.hermes/.env`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Hermes Runner ────────────────────────────────────────────────────────────

async def run_hermes(prompt: str, workdir: str = None) -> str:
    """Jalankan hermes dengan prompt, return output sebagai string."""
    cmd = [
        HERMES_BIN,
        "run",
        "--no-stream",          # output sekaligus, tidak streaming
        "--yes",                # auto-approve tool calls (trust karena sudah auth via Telegram)
        "--",
        prompt,
    ]

    env = os.environ.copy()
    env["HERMES_HOME"] = HERMES_HOME
    env["AUTOCLIPER_API_URL"] = AUTOCLIPER_API_URL

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir or str(Path.home()),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=HERMES_TIMEOUT
        )
        output = stdout.decode("utf-8", errors="replace").strip()
        if not output and stderr:
            output = stderr.decode("utf-8", errors="replace").strip()
        return output or "(Tidak ada output dari Hermes)"
    except asyncio.TimeoutError:
        proc.kill()
        return f"⏰ Timeout setelah {HERMES_TIMEOUT}s. Task mungkin masih berjalan di background."
    except FileNotFoundError:
        return (
            f"❌ `hermes` binary tidak ditemukan di PATH.\n"
            f"Install: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`"
        )
    except Exception as e:
        return f"❌ Error menjalankan Hermes: {e}"


async def run_ac_tool(script: str, *args) -> str:
    """Jalankan ac_*.py tool langsung (lebih cepat dari via hermes)."""
    bin_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "hermes",
        "bin",
    )
    # Cari di HERMES_HOME/skills/bin juga (setelah sync)
    hermes_bin = os.path.join(HERMES_HOME, "skills", "bin")

    script_path = None
    for search_dir in [hermes_bin, bin_dir]:
        candidate = os.path.join(search_dir, script)
        if os.path.exists(candidate):
            script_path = candidate
            break

    if not script_path:
        return f"❌ Script `{script}` tidak ditemukan. Jalankan `sync-hermes-config.sh` dulu."

    cmd = [sys.executable, script_path] + list(args)
    env = os.environ.copy()
    env["HERMES_HOME"] = HERMES_HOME
    env["AUTOCLIPER_API_URL"] = AUTOCLIPER_API_URL

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace").strip()
        return output or "(Tidak ada output)"
    except asyncio.TimeoutError:
        return "⏰ Tool timeout setelah 60s."
    except Exception as e:
        return f"❌ Error: {e}"


# ─── Helper ───────────────────────────────────────────────────────────────────

def split_message(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    """Pecah teks panjang jadi beberapa chunk."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunk = text[:max_len]
        # Potong di newline terakhir supaya tidak putus di tengah kalimat
        last_nl = chunk.rfind("\n")
        if last_nl > max_len // 2:
            chunk = chunk[:last_nl]
        chunks.append(chunk)
        text = text[len(chunk):].lstrip("\n")
    return chunks


async def send_long(update: Update, text: str):
    """Kirim teks panjang, pecah jika perlu."""
    for chunk in split_message(text):
        await update.message.reply_text(chunk)


def _get_current_model() -> str:
    """Ambil model yang sedang aktif di config.yaml"""
    config_path = os.path.join(HERMES_HOME, "config.yaml")
    if not os.path.exists(config_path):
        return "unknown (config tidak ditemukan)"
    try:
        with open(config_path, "r") as f:
            for line in f:
                if line.strip().startswith("default:") and "model:" not in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "unknown"


# ─── Command Handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Halo *{name}*! AutoCliper Bot siap.\n\n"
        "*Perintah cepat:*\n"
        "🔍 `/viral <topik>` — cari video viral\n"
        "🚀 `/submit <url>` — submit ke pipeline\n"
        "📊 `/status <job_id>` — cek progress\n"
        "📋 `/jobs` — list job terbaru\n"
        "🔄 `/model <nama>` — ganti LLM model\n"
        "🆔 `/myid` — lihat Telegram ID kamu\n\n"
        "*Atau ketik bebas* → Hermes akan analisis dan eksekusi 🤖",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)
    await update.message.reply_text(
        "*AutoCliper Bot — Panduan*\n\n"
        "*Cari & Submit:*\n"
        "• `/viral gym motivation` — cari video viral topik gym\n"
        "• `/viral crypto news --lang id` — filter bahasa Indonesia\n"
        "• `/submit https://youtube.com/watch?v=...` — proses video\n"
        "• `/submit <url> --style viral --ratio 9:16`\n\n"
        "*Monitor:*\n"
        "• `/status abc123` — progress job tertentu\n"
        "• `/jobs` — semua job terbaru\n"
        "• `/jobs --status completed` — filter selesai\n\n"
        "*Konfigurasi:*\n"
        "• `/model grok` — pakai Grok (default)\n"
        "• `/model gemini` — pakai Gemini Pro\n"
        "• `/model gpt-4o` — pakai GPT-4o\n"
        "• `/model llama` — pakai Llama 70B (Groq)\n"
        "• `/model cliperhub` — pakai 9router CliperHub\n\n"
        "*Agentic Mode:*\n"
        "Ketik pesan bebas dan Hermes akan:\n"
        "• Cari video viral sesuai niche\n"
        "• Rekomendasikan mana yang worth diproses\n"
        "• Submit langsung ke AutoCliper\n"
        "• Laporan saat selesai\n\n"
        "_Contoh: \"Carikan 5 video gym motivation terbaik minggu ini "
        "dan proses yang paling viral\"_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"Telegram ID kamu: `{uid}`\n"
        "Tambahkan ke `TELEGRAM_ALLOWED_USERS` di `.hermes/.env` untuk akses bot.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_viral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: `/viral <topik> [--limit N] [--lang id]`", parse_mode=ParseMode.MARKDOWN)
        return

    # Parse args sederhana
    query_parts = []
    limit = "5"
    language = ""
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = args[i + 1]; i += 2
        elif args[i] == "--lang" and i + 1 < len(args):
            language = args[i + 1]; i += 2
        else:
            query_parts.append(args[i]); i += 1

    query = " ".join(query_parts)
    if not query:
        await update.message.reply_text("Masukkan topik pencarian.")
        return

    await update.message.reply_text(f"🔍 Mencari video viral: *{query}*...", parse_mode=ParseMode.MARKDOWN)
    await update.message.chat.send_action(ChatAction.TYPING)

    result = await run_ac_tool(
        "ac_viral_search.py",
        "--query", query,
        "--limit", limit,
        "--language", language,
    )
    await send_long(update, result)


async def cmd_submit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage: `/submit <youtube_url> [--style default|viral|minimal|bold] [--ratio 9:16|16:9|1:1]`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    url = args[0]
    style = "default"
    ratio = "9:16"
    force = "false"

    i = 1
    while i < len(args):
        if args[i] == "--style" and i + 1 < len(args):
            style = args[i + 1]; i += 2
        elif args[i] == "--ratio" and i + 1 < len(args):
            ratio = args[i + 1]; i += 2
        elif args[i] == "--force":
            force = "true"; i += 1
        else:
            i += 1

    if not url.startswith("http"):
        await update.message.reply_text("URL tidak valid. Harus dimulai dengan `https://`", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text(f"🚀 Submitting ke AutoCliper...\n`{url}`", parse_mode=ParseMode.MARKDOWN)
    await update.message.chat.send_action(ChatAction.TYPING)

    result = await run_ac_tool(
        "ac_submit_job.py",
        "--url", url,
        "--style", style,
        "--ratio", ratio,
        "--force", force,
    )
    await send_long(update, result)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    if not ctx.args:
        await update.message.reply_text("Usage: `/status <job_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    job_id = ctx.args[0]
    await update.message.chat.send_action(ChatAction.TYPING)

    result = await run_ac_tool("ac_job_status.py", "--job-id", job_id)
    await send_long(update, result)


async def cmd_jobs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    limit = "10"
    status_filter = "all"

    args = ctx.args or []
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = args[i + 1]; i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            status_filter = args[i + 1]; i += 2
        else:
            i += 1

    await update.message.chat.send_action(ChatAction.TYPING)
    result = await run_ac_tool("ac_list_jobs.py", "--limit", limit, "--status", status_filter)
    await send_long(update, result)


async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    if not ctx.args:
        # Tampilkan model yang sedang dipakai
        current = _get_current_model()
        await update.message.reply_text(
            f"🤖 *Model saat ini:* `{current}`\n\n"
            "*Ganti model:* `/model <nama>`\n\n"
            "*Alias tersedia:*\n"
            "• `grok` → gcli/grok-4.5-high\n"
            "• `grok-fast` → gcli/grok-4.5-fast\n"
            "• `gemini` → gcli/gemini-2.5-pro\n"
            "• `gemini-flash` → gcli/gemini-2.5-flash\n"
            "• `gpt-4o` → openai/gpt-4o\n"
            "• `llama` → groq/llama-3.3-70b\n"
            "• `cliperhub` → CliperHub\n\n"
            "💡 Atau pakai nama model langsung dari 9router.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    model = " ".join(ctx.args)
    await update.message.chat.send_action(ChatAction.TYPING)
    result = await run_ac_tool("ac_switch_model.py", "--model", model)
    await send_long(update, result)



# ─── Agentic Message Handler ──────────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pesan bebas → forward ke Hermes sebagai agentic prompt."""
    if not is_allowed(update):
        return await deny(update)

    text = update.message.text or ""
    if not text.strip():
        return

    await update.message.reply_text("🤖 Hermes sedang berpikir...")
    await update.message.chat.send_action(ChatAction.TYPING)

    # Sertakan context AutoCliper dalam prompt supaya hermes tahu konteksnya
    prompt = (
        f"Kamu adalah asisten AutoCliper. "
        f"AutoCliper API tersedia di {AUTOCLIPER_API_URL}. "
        f"Kamu punya tools: autocliper_viral_search, autocliper_submit_job, "
        f"autocliper_job_status, autocliper_list_jobs, autocliper_switch_model. "
        f"User request: {text}"
    )

    result = await run_hermes(prompt)
    await send_long(update, result)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN tidak di-set di $HERMES_HOME/.env")
        print("Dapatkan token dari @BotFather di Telegram.")
        sys.exit(1)

    if not ALLOWED_USERS:
        logger.warning(
            "TELEGRAM_ALLOWED_USERS tidak di-set — semua orang bisa akses bot! "
            "Set di $HERMES_HOME/.env untuk keamanan."
        )

    logger.info(f"Starting AutoCliper Bot...")
    logger.info(f"HERMES_HOME: {HERMES_HOME}")
    logger.info(f"AutoCliper API: {AUTOCLIPER_API_URL}")
    logger.info(f"Allowed users: {ALLOWED_USERS or 'ALL (tidak aman!)'}")

    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("viral", cmd_viral))
    app.add_handler(CommandHandler("submit", cmd_submit))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("model", cmd_model))

    # Agentic mode: semua pesan teks biasa
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot running — tekan Ctrl+C untuk stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
