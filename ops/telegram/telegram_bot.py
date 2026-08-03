"""
AutoCliper Telegram Bot — Relay ke Hermes
==========================================
Bot ini bertindak sebagai interface Telegram untuk Hermes agent.
Setiap pesan dari user authorized diteruskan ke hermes CLI sebagai prompt,
dan responnya dikirim balik ke Telegram.

Fitur:
- /start, /help           — onboarding dengan inline buttons
- /model <nama>           — ganti model LLM (dengan button picker)
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
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.constants import ChatAction, ParseMode
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
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


# ─── Inline Keyboard Layouts ─────────────────────────────────────────────────

def kb_main_menu() -> InlineKeyboardMarkup:
    """Keyboard utama: menu aksi."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Cari Viral", callback_data="menu_viral"),
            InlineKeyboardButton("🚀 Submit URL", callback_data="menu_submit"),
        ],
        [
            InlineKeyboardButton("📋 Job Terbaru", callback_data="act_jobs"),
            InlineKeyboardButton("📊 Cek Status", callback_data="menu_status"),
        ],
        [
            InlineKeyboardButton("🤖 Model LLM", callback_data="menu_model"),
            InlineKeyboardButton("🆔 My ID", callback_data="act_myid"),
        ],
        [
            InlineKeyboardButton("❓ Bantuan", callback_data="act_help"),
        ],
    ])


def kb_model_picker(current: str) -> InlineKeyboardMarkup:
    """Keyboard pilihan model LLM."""
    models = [
        ("Grok 4.5 High", "grok"),
        ("Grok 4.5 Fast", "grok-fast"),
        ("Gemini 2.5 Pro", "gemini"),
        ("Gemini 2.5 Flash", "gemini-flash"),
        ("GPT-4o", "gpt-4o"),
        ("Llama 70B", "llama"),
        ("CliperHub", "cliperhub"),
    ]
    rows = []
    for i in range(0, len(models), 2):
        row = []
        for name, alias in models[i:i + 2]:
            # Tandai model aktif dengan ✓
            label = f"✓ {name}" if alias in current.lower() or name.lower() in current.lower() else name
            row.append(InlineKeyboardButton(label, callback_data=f"model_{alias}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀️ Kembali", callback_data="act_back")])
    return InlineKeyboardMarkup(rows)


def kb_viral_suggestions() -> InlineKeyboardMarkup:
    """Keyboard topik viral populer sebagai quick-pick."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💪 Gym Motivation", callback_data="viral_gym motivation"),
            InlineKeyboardButton("📈 Trading Crypto", callback_data="viral_trading crypto"),
        ],
        [
            InlineKeyboardButton("🎮 Gaming", callback_data="viral_gaming clips"),
            InlineKeyboardButton("🧠 AI Tutorial", callback_data="viral_AI tutorial"),
        ],
        [
            InlineKeyboardButton("😂 Funny Clips", callback_data="viral_funny viral clips"),
            InlineKeyboardButton("🍳 Cooking", callback_data="viral_cooking recipes"),
        ],
        [
            InlineKeyboardButton("✏️ Ketik sendiri...", callback_data="viral_custom"),
            InlineKeyboardButton("◀️ Kembali", callback_data="act_back"),
        ],
    ])


def kb_back() -> InlineKeyboardMarkup:
    """Keyboard kembali ke menu utama."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Menu Utama", callback_data="act_back")],
    ])


# ─── Auth Guard ───────────────────────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True  # Kalau tidak dikonfigurasi, semua bisa (hati-hati!)
    user = update.effective_user
    return user is not None and user.id in ALLOWED_USERS


async def deny(update: Update):
    uid = update.effective_user.id
    logger.warning(f"Unauthorized access attempt: user_id={uid}")
    target = update.message or (update.callback_query and update.callback_query.message)
    if target:
        await target.reply_text(
            f"⛔ Akses ditolak. User ID kamu: `{uid}`\n"
            "Tambahkan ID ini ke `TELEGRAM_ALLOWED_USERS` di `.hermes/.env`",
            parse_mode=ParseMode.MARKDOWN,
        )


async def deny_callback(query):
    uid = query.from_user.id
    logger.warning(f"Unauthorized callback: user_id={uid}")
    await query.answer(f"⛔ Akses ditolak. ID: {uid}", show_alert=True)


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


async def send_long(message, text: str, reply_markup=None):
    """Kirim teks panjang, pecah jika perlu. Message bisa dari update.message atau query.message."""
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        # Keyboard hanya di chunk terakhir
        markup = reply_markup if i == len(chunks) - 1 else None
        await message.reply_text(chunk, reply_markup=markup)


def _get_current_model() -> str:
    """Ambil model yang sedang aktif di config.yaml"""
    config_path = os.path.join(HERMES_HOME, "config.yaml")
    if not os.path.exists(config_path):
        return "unknown"
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
    current_model = _get_current_model()
    await update.message.reply_text(
        f"👋 Halo *{name}*! AutoCliper Bot siap.\n\n"
        f"🤖 Model aktif: `{current_model}`\n\n"
        "Pilih aksi di bawah atau *ketik pesan bebas*\n"
        "untuk mode agentic — Hermes akan analisis\n"
        "dan eksekusi otomatis. 🚀",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_main_menu(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)
    await _send_help(update.message)


async def _send_help(message):
    """Kirim pesan bantuan lengkap."""
    await message.reply_text(
        "📖 *AutoCliper Bot — Panduan*\n\n"
        "*🔍 Cari & Submit:*\n"
        "• `/viral gym motivation` — cari video viral\n"
        "• `/viral crypto --lang id` — filter bahasa\n"
        "• `/submit <url>` — proses video\n"
        "• `/submit <url> --style viral --ratio 9:16`\n\n"
        "*📊 Monitor:*\n"
        "• `/status <job_id>` — progress job\n"
        "• `/jobs` — semua job terbaru\n"
        "• `/jobs --status completed` — filter\n\n"
        "*🤖 Model:*\n"
        "• `/model` — lihat model aktif + pilih\n"
        "• `/model grok` — ganti langsung\n\n"
        "*💬 Agentic Mode:*\n"
        "Ketik pesan bebas, contoh:\n"
        "_\"Carikan 5 video gym motivation terbaik "
        "dan proses yang paling viral\"_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_back(),
    )


async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🆔 Telegram ID kamu: `{uid}`\n\n"
        "Tambahkan ke `TELEGRAM_ALLOWED_USERS`\n"
        "di `$HERMES_HOME/.env` untuk akses bot.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_back(),
    )


async def cmd_viral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    args = ctx.args
    if not args:
        # Tampilkan tombol topik populer
        await update.message.reply_text(
            "🔍 *Cari Video Viral*\n\n"
            "Pilih topik di bawah atau ketik:\n"
            "`/viral <topik> [--limit N] [--lang id]`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_viral_suggestions(),
        )
        return

    await _do_viral_search(update.message, ctx.args)


async def _do_viral_search(message, args: list):
    """Eksekusi pencarian viral."""
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
        await message.reply_text("Masukkan topik pencarian.")
        return

    await message.reply_text(f"🔍 Mencari video viral: *{query}*...", parse_mode=ParseMode.MARKDOWN)
    await message.chat.send_action(ChatAction.TYPING)

    result = await run_ac_tool(
        "ac_viral_search.py",
        "--query", query,
        "--limit", limit,
        "--language", language,
    )
    await send_long(message, result, reply_markup=kb_back())


async def cmd_submit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    args = ctx.args
    if not args:
        await update.message.reply_text(
            "🚀 *Submit Video ke Pipeline*\n\n"
            "Kirim YouTube URL:\n"
            "`/submit <url>`\n\n"
            "Opsi tambahan:\n"
            "• `--style` default｜viral｜minimal｜bold\n"
            "• `--ratio` 9:16｜16:9｜1:1\n"
            "• `--force` proses ulang",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_back(),
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
        await update.message.reply_text(
            "❌ URL tidak valid. Harus dimulai dengan `https://`",
            parse_mode=ParseMode.MARKDOWN,
        )
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
    await send_long(update.message, result, reply_markup=kb_back())


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    if not ctx.args:
        await update.message.reply_text(
            "📊 *Cek Status Job*\n\n"
            "Kirim job ID:\n"
            "`/status <job_id>`\n\n"
            "Atau lihat daftar job dulu:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Lihat Semua Job", callback_data="act_jobs")],
                [InlineKeyboardButton("◀️ Kembali", callback_data="act_back")],
            ]),
        )
        return

    job_id = ctx.args[0]
    await update.message.chat.send_action(ChatAction.TYPING)

    result = await run_ac_tool("ac_job_status.py", "--job-id", job_id)
    await send_long(update.message, result, reply_markup=kb_back())


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
    await send_long(update.message, result, reply_markup=kb_back())


async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return await deny(update)

    if not ctx.args:
        await _send_model_picker(update.message)
        return

    model = " ".join(ctx.args)
    await update.message.chat.send_action(ChatAction.TYPING)
    result = await run_ac_tool("ac_switch_model.py", "--model", model)
    # Setelah ganti, tampilkan picker lagi dengan status baru
    current = _get_current_model()
    await update.message.reply_text(result)
    await update.message.reply_text(
        f"🤖 Model aktif: `{current}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_back(),
    )


async def _send_model_picker(message):
    """Tampilkan model picker dengan model saat ini."""
    current = _get_current_model()
    await message.reply_text(
        f"🤖 *Model LLM*\n\n"
        f"Model aktif: `{current}`\n\n"
        "Pilih model di bawah atau ketik:\n"
        "`/model <nama>`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_model_picker(current),
    )


# ─── Callback Query Handler (Tombol) ─────────────────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle semua inline button presses."""
    query = update.callback_query
    await query.answer()  # Acknowledge button press

    if not ALLOWED_USERS or query.from_user.id in ALLOWED_USERS:
        pass
    else:
        return await deny_callback(query)

    data = query.data

    # ─── Menu navigasi ────────────────────────────────────────────────────
    if data == "act_back":
        current_model = _get_current_model()
        await query.message.edit_text(
            f"🏠 *Menu Utama*\n\n"
            f"🤖 Model aktif: `{current_model}`\n\n"
            "Pilih aksi atau ketik pesan bebas\n"
            "untuk mode agentic.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main_menu(),
        )

    elif data == "act_help":
        await query.message.edit_text(
            "📖 *AutoCliper Bot — Panduan*\n\n"
            "*🔍 Cari & Submit:*\n"
            "• `/viral gym motivation` — cari viral\n"
            "• `/submit <url>` — proses video\n\n"
            "*📊 Monitor:*\n"
            "• `/status <job_id>` — progress\n"
            "• `/jobs` — list job terbaru\n\n"
            "*🤖 Model:*\n"
            "• `/model` — lihat + pilih model\n\n"
            "*💬 Agentic Mode:*\n"
            "Ketik pesan bebas, Hermes eksekusi otomatis!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_back(),
        )

    elif data == "act_myid":
        uid = query.from_user.id
        await query.message.edit_text(
            f"🆔 Telegram ID kamu: `{uid}`\n\n"
            "Tambahkan ke `TELEGRAM_ALLOWED_USERS`\n"
            "di `$HERMES_HOME/.env` untuk akses bot.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_back(),
        )

    elif data == "act_jobs":
        await query.message.edit_text("📋 Mengambil daftar job...")
        await query.message.chat.send_action(ChatAction.TYPING)
        result = await run_ac_tool("ac_list_jobs.py", "--limit", "10", "--status", "all")
        await send_long(query.message, result, reply_markup=kb_back())

    # ─── Menu viral ───────────────────────────────────────────────────────
    elif data == "menu_viral":
        await query.message.edit_text(
            "🔍 *Cari Video Viral*\n\n"
            "Pilih topik populer atau ketik:\n"
            "`/viral <topik> [--limit N] [--lang id]`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_viral_suggestions(),
        )

    elif data.startswith("viral_"):
        topic = data[6:]  # Setelah "viral_"
        if topic == "custom":
            await query.message.edit_text(
                "✏️ Ketik topik pencarian kamu:\n"
                "`/viral <topik>`\n\n"
                "Contoh: `/viral motivasi bisnis --lang id`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb_back(),
            )
        else:
            await query.message.edit_text(f"🔍 Mencari video viral: *{topic}*...", parse_mode=ParseMode.MARKDOWN)
            await query.message.chat.send_action(ChatAction.TYPING)
            result = await run_ac_tool("ac_viral_search.py", "--query", topic, "--limit", "5", "--language", "")
            await send_long(query.message, result, reply_markup=kb_back())

    # ─── Menu submit ──────────────────────────────────────────────────────
    elif data == "menu_submit":
        await query.message.edit_text(
            "🚀 *Submit Video ke Pipeline*\n\n"
            "Kirim YouTube URL:\n"
            "`/submit <url>`\n\n"
            "Opsi:\n"
            "• `--style` viral｜default｜minimal｜bold\n"
            "• `--ratio` 9:16｜16:9｜1:1\n"
            "• `--force` proses ulang\n\n"
            "Contoh:\n"
            "`/submit https://youtube.com/watch?v=... --style viral`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_back(),
        )

    # ─── Menu status ──────────────────────────────────────────────────────
    elif data == "menu_status":
        await query.message.edit_text(
            "📊 *Cek Status Job*\n\n"
            "Kirim job ID:\n"
            "`/status <job_id>`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Lihat Semua Job", callback_data="act_jobs")],
                [InlineKeyboardButton("◀️ Kembali", callback_data="act_back")],
            ]),
        )

    # ─── Menu & aksi model ────────────────────────────────────────────────
    elif data == "menu_model":
        current = _get_current_model()
        await query.message.edit_text(
            f"🤖 *Model LLM*\n\n"
            f"Model aktif: `{current}`\n\n"
            "Pilih model:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_model_picker(current),
        )

    elif data.startswith("model_"):
        alias = data[6:]  # Setelah "model_"
        await query.message.edit_text(f"🔄 Mengganti model ke *{alias}*...", parse_mode=ParseMode.MARKDOWN)
        await query.message.chat.send_action(ChatAction.TYPING)
        result = await run_ac_tool("ac_switch_model.py", "--model", alias)
        # Tampilkan hasil + picker baru
        current = _get_current_model()
        await query.message.reply_text(result)
        await query.message.reply_text(
            f"🤖 Model aktif: `{current}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_model_picker(current),
        )


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
    await send_long(update.message, result, reply_markup=kb_back())


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

    # Register handlers — command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("viral", cmd_viral))
    app.add_handler(CommandHandler("submit", cmd_submit))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("model", cmd_model))

    # Callback handler — inline button presses
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Agentic mode: semua pesan teks biasa
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot running — tekan Ctrl+C untuk stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
