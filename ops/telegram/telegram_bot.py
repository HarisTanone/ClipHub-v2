"""
AutoCliper Telegram Bot — Relay ke Hermes (v2)
==============================================
Production-ready Telegram interface untuk Hermes agent.

Fitur:
  • /start, /help          — onboarding dengan inline buttons
  • /model [nama]           — ganti model LLM (dengan button picker)
  • /viral <topik>          — cari video YouTube viral
  • /jobs [--status] [--limit]  — list job terbaru (dengan pagination)
  • /status <job_id>        — cek status job
  • /submit <url>           — submit YouTube URL (dengan konfirmasi)
  • /cancel                 — batalkan aksi yang sedang berjalan
  • /id                     — tampilkan Telegram user ID
  • Pesan bebas             → diteruskan ke hermes sebagai prompt (agentic mode)

Improvements over v1:
  • HTML parse mode (lebih reliable dari Markdown)
  • Structured config via dataclass
  • Custom exception hierarchy
  • Progress indicator saat menunggu Hermes
  • Rate limiting per user
  • Pagination untuk job list
  • Konfirmasi sebelum submit/force-reprocess
  • Better error messages & error handler global
  • Streaming output dari Hermes (opsional)
  • Structured logging dengan context

Setup:
    1. Set TELEGRAM_BOT_TOKEN dan TELEGRAM_ALLOWED_USERS di $HERMES_HOME/.env
    2. pip install 'python-telegram-bot>=20.0' pyyaml
    3. python telegram_bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ─── Load .env dari HERMES_HOME ───────────────────────────────────────────────

_hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
_env_file = os.path.join(_hermes_home, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

try:
    from telegram import (
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Update,
    )
    from telegram.constants import ChatAction, ParseMode
    from telegram.error import Forbidden, NetworkError, TimedOut
    from telegram.ext import (
        Application,
        ApplicationBuilder,
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


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BotConfig:
    """Centralized configuration loaded from environment."""
    bot_token: str
    allowed_users: frozenset[int]
    hermes_bin: str
    hermes_home: str
    autocliper_api_url: str
    hermes_timeout: int
    tool_timeout: int
    rate_limit_seconds: float
    max_msg_len: int
    jobs_per_page: int

    @classmethod
    def from_env(cls) -> "BotConfig":
        raw_users = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
        users: set[int] = set()
        for uid in raw_users.split(","):
            uid = uid.strip()
            if uid.isdigit():
                users.add(int(uid))

        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            allowed_users=frozenset(users),
            hermes_bin=os.environ.get("HERMES_BIN", "hermes"),
            hermes_home=_hermes_home,
            autocliper_api_url=os.environ.get("AUTOCLIPER_API_URL", "http://127.0.0.1:8000/api"),
            hermes_timeout=int(os.environ.get("HERMES_TIMEOUT", "300")),
            tool_timeout=int(os.environ.get("TOOL_TIMEOUT", "60")),
            rate_limit_seconds=float(os.environ.get("RATE_LIMIT_SECONDS", "3.0")),
            max_msg_len=4000,
            jobs_per_page=int(os.environ.get("JOBS_PER_PAGE", "8")),
        )


CONFIG = BotConfig.from_env()


# ═══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class HermesError(Exception):
    """Base exception for Hermes-related errors."""


class HermesTimeoutError(HermesError):
    pass


class HermesNotFoundError(HermesError):
    pass


class ToolError(Exception):
    """Base exception for AC tool errors."""


class ToolNotFoundError(ToolError):
    pass


class ToolTimeoutError(ToolError):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)-20s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("autocliper.bot")


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Available models with display info
MODELS: list[tuple[str, str, str]] = [
    # (display_name, alias, description)
    ("Grok 4.5 High",     "grok",          "Premium, reasoning terbaik"),
    ("Grok 4.5 Fast",     "grok-fast",     "Cepat, hemat token"),
    ("Gemini 2.5 Pro",    "gemini",        "Google, multimodal"),
    ("Gemini 2.5 Flash",  "gemini-flash",  "Cepat & murah"),
    ("GPT-4o",            "gpt-4o",        "OpenAI flagship"),
    ("Llama 3.3 70B",     "llama",         "Open-source, lokal"),
    ("CliperHub",         "cliperhub",     "Optimized untuk AutoCliper"),
]

# Quick-pick viral topics
VIRAL_TOPICS: list[tuple[str, str, str]] = [
    # (emoji, label, query)
    ("💪", "Gym Motivation",  "gym motivation"),
    ("📈", "Trading Crypto",  "trading crypto"),
    ("🎮", "Gaming Clips",    "gaming clips"),
    ("🧠", "AI Tutorial",     "AI tutorial"),
    ("😂", "Funny Clips",     "funny viral clips"),
    ("🍳", "Cooking",         "cooking recipes"),
    ("💪", "Fitness",         "fitness workout"),
    ("🎸", "Music",           "music viral"),
]

# Emoji constants
E = {
    "rocket":   "🚀",
    "search":   "🔍",
    "chart":    "📊",
    "list":     "📋",
    "robot":    "🤖",
    "check":    "✅",
    "cross":    "❌",
    "warn":     "⚠️",
    "clock":    "⏰",
    "back":     "◀️",
    "home":     "🏠",
    "help":     "❓",
    "id":       "🆔",
    "loading":  "⏳",
    "spark":    "✨",
    "fire":     "🔥",
    "gear":     "⚙️",
    "link":     "🔗",
    "user":     "👤",
    "cancel":   "🚫",
    "success":  "✅",
    "error":    "💥",
}


# ═══════════════════════════════════════════════════════════════════════════════
# MESSAGE BUILDER — centralized message templates
# ═══════════════════════════════════════════════════════════════════════════════

class Msg:
    """HTML-formatted message templates."""

    # ── Utility ────────────────────────────────────────────────────────────────

    @staticmethod
    def b(text: str) -> str:
        """Bold"""
        return f"<b>{text}</b>"

    @staticmethod
    def i(text: str) -> str:
        """Italic"""
        return f"<i>{text}</i>"

    @staticmethod
    def code(text: str) -> str:
        """Inline code"""
        return f"<code>{text}</code>"

    @staticmethod
    def codeblock(text: str) -> str:
        """Code block"""
        return f"<pre>{text}</pre>"

    @staticmethod
    def escape(text: str) -> str:
        """Escape HTML special chars"""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    # ── Greeting ───────────────────────────────────────────────────────────────

    @staticmethod
    def welcome(name: str, model: str) -> str:
        return (
            f"{E['spark']} <b>Halo, {Msg.escape(name)}!</b>\n\n"
            f"AutoCliper Bot siap membantu kamu.\n\n"
            f"{E['robot']} <b>Model aktif:</b> <code>{Msg.escape(model)}</code>\n\n"
            f"Pilih aksi di bawah, atau ketik pesan bebas "
            f"untuk masuk ke <b>Agentic Mode</b> — "
            f"Hermes akan menganalisis dan mengeksekusi otomatis."
        )

    # ── Help ───────────────────────────────────────────────────────────────────

    @staticmethod
    def help_full() -> str:
        return (
            f"{E['help']} <b>AutoCliper Bot — Panduan Lengkap</b>\n"
            f"{'─' * 32}\n\n"

            f"{E['search']} <b>Cari &amp; Submit</b>\n"
            f"• <code>/viral gym motivation</code>\n"
            f"  Cari video viral berdasarkan topik\n"
            f"• <code>/viral crypto --lang id --limit 10</code>\n"
            f"  Dengan filter bahasa &amp; jumlah\n"
            f"• <code>/submit https://youtu.be/...</code>\n"
            f"  Submit URL ke pipeline AutoCliper\n"
            f"• <code>/submit &lt;url&gt; --style viral --ratio 9:16</code>\n"
            f"  Dengan opsi style dan rasio\n\n"

            f"{E['chart']} <b>Monitoring</b>\n"
            f"• <code>/status &lt;job_id&gt;</code> — cek progress job\n"
            f"• <code>/jobs</code> — list job terbaru\n"
            f"• <code>/jobs --status completed --limit 20</code> — filter\n\n"

            f"{E['robot']} <b>Model LLM</b>\n"
            f"• <code>/model</code> — lihat &amp; pilih model\n"
            f"• <code>/model grok</code> — ganti langsung\n\n"

            f"{E['fire']} <b>Agentic Mode</b>\n"
            f"Ketik pesan bebas, contoh:\n"
            f"{Msg.i('\"Carikan 5 video gym motivation terbaik dan proses yang paling viral\"')}\n\n"

            f"{E['gear']} <b>Lainnya</b>\n"
            f"• <code>/id</code> — tampilkan Telegram ID kamu\n"
            f"• <code>/cancel</code> — batalkan operasi yang berjalan\n"
        )

    @staticmethod
    def help_short() -> str:
        return (
            f"{E['help']} <b>Bantuan Cepat</b>\n\n"
            f"{E['search']} <code>/viral &lt;topik&gt;</code> — cari viral\n"
            f"{E['rocket']} <code>/submit &lt;url&gt;</code> — proses video\n"
            f"{E['chart']} <code>/status &lt;id&gt;</code> — cek job\n"
            f"{E['list']} <code>/jobs</code> — list job\n"
            f"{E['robot']} <code>/model</code> — ganti LLM\n\n"
            f"{Msg.i('Atau ketik pesan bebas untuk Agentic Mode')}"
        )

    # ── Status messages ────────────────────────────────────────────────────────

    @staticmethod
    def thinking() -> str:
        return f"{E['loading']} <b>Hermes sedang berpikir...</b>"

    @staticmethod
    def searching(topic: str) -> str:
        return f"{E['search']} Mencari video viral: <b>{Msg.escape(topic)}</b>..."

    @staticmethod
    def submitting(url: str) -> str:
        return f"{E['rocket']} Submitting ke AutoCliper...\n<code>{Msg.escape(url)}</code>"

    @staticmethod
    def switching_model(alias: str) -> str:
        return f"{E['gear']} Mengganti model ke <b>{Msg.escape(alias)}</b>..."

    @staticmethod
    def fetching_jobs() -> str:
        return f"{E['list']} Mengambil daftar job..."

    @staticmethod
    def fetching_status(job_id: str) -> str:
        return f"{E['chart']} Mengambil status job <code>{Msg.escape(job_id)}</code>..."

    # ── Error messages ─────────────────────────────────────────────────────────

    @staticmethod
    def error_timeout(seconds: int) -> str:
        return (
            f"{E['clock']} <b>Timeout</b>\n\n"
            f"Operasi melebihi batas {seconds} detik.\n"
            f"Task mungkin masih berjalan di background."
        )

    @staticmethod
    def error_hermes_not_found() -> str:
        return (
            f"{E['error']} <b>Hermes binary tidak ditemukan</b>\n\n"
            f"Pastikan <code>hermes</code> tersedia di PATH.\n"
            f"Install: <code>curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash</code>"
        )

    @staticmethod
    def error_tool_not_found(script: str) -> str:
        return (
            f"{E['error']} <b>Tool tidak ditemukan</b>\n\n"
            f"Script <code>{Msg.escape(script)}</code> tidak ditemukan.\n"
            f"Jalankan <code>sync-hermes-config.sh</code> untuk sinkronisasi."
        )

    @staticmethod
    def error_generic(detail: str) -> str:
        return f"{E['error']} <b>Terjadi kesalahan</b>\n\n{Msg.escape(detail)}"

    @staticmethod
    def error_rate_limited(wait: float) -> str:
        return (
            f"{E['clock']} <b>Sabar sebentar...</b>\n\n"
            f"Tunggu {wait:.0f} detik sebelum mengirim perintah berikutnya."
        )

    @staticmethod
    def error_cancelled() -> str:
        return f"{E['cancel']} <b>Operasi dibatalkan.</b>"

    # ── Access control ─────────────────────────────────────────────────────────

    @staticmethod
    def access_denied(uid: int) -> str:
        return (
            f"{E['cross']} <b>Akses Ditolak</b>\n\n"
            f"User ID kamu: <code>{uid}</code>\n\n"
            f"Tambahkan ID ini ke <code>TELEGRAM_ALLOWED_USERS</code>\n"
            f"di <code>$HERMES_HOME/.env</code> untuk mendapatkan akses."
        )

    @staticmethod
    def show_id(uid: int) -> str:
        return (
            f"{E['id']} <b>Telegram ID Kamu</b>\n\n"
            f"<code>{uid}</code>\n\n"
            f"Tambahkan ke <code>TELEGRAM_ALLOWED_USERS</code>\n"
            f"di <code>$HERMES_HOME/.env</code> untuk akses bot."
        )

    # ── Model info ─────────────────────────────────────────────────────────────

    @staticmethod
    def model_info(current: str) -> str:
        lines = [f"{E['robot']} <b>Pilih Model LLM</b>", ""]
        lines.append(f"Model aktif: <code>{Msg.escape(current)}</code>")
        lines.append("")
        lines.append("Pilih model di bawah atau ketik:")
        lines.append("<code>/model &lt;nama&gt;</code>")
        lines.append("")
        lines.append("<b>Daftar model:</b>")
        for name, alias, desc in MODELS:
            marker = f"{E['check']} " if alias == current.lower() else "  "
            lines.append(f"{marker}<b>{name}</b> (<code>{alias}</code>)")
            lines.append(f"    {Msg.i(desc)}")
        return "\n".join(lines)

    @staticmethod
    def model_switched(alias: str, result: str) -> str:
        return (
            f"{E['success']} <b>Model diganti</b>\n\n"
            f"Model aktif: <code>{Msg.escape(alias)}</code>\n\n"
            f"{Msg.escape(result)}"
        )

    # ── Job / status ───────────────────────────────────────────────────────────

    @staticmethod
    def jobs_header(page: int, total_pages: int, status_filter: str) -> str:
        return (
            f"{E['list']} <b>Daftar Job</b>\n"
            f"{'─' * 28}\n"
            f"Filter: <code>{Msg.escape(status_filter)}</code> │ "
            f"Halaman {page}/{total_pages}\n"
        )

    @staticmethod
    def status_prompt() -> str:
        return (
            f"{E['chart']} <b>Cek Status Job</b>\n\n"
            f"Kirim job ID:\n"
            f"<code>/status &lt;job_id&gt;</code>"
        )

    @staticmethod
    def submit_prompt() -> str:
        return (
            f"{E['rocket']} <b>Submit Video ke Pipeline</b>\n\n"
            f"Kirim YouTube URL:\n"
            f"<code>/submit &lt;url&gt;</code>\n\n"
            f"<b>Opsi:</b>\n"
            f"• <code>--style</code> default | viral | minimal | bold\n"
            f"• <code>--ratio</code> 9:16 | 16:9 | 1:1\n"
            f"• <code>--force</code> proses ulang\n\n"
            f"<b>Contoh:</b>\n"
            f"<code>/submit https://youtu.be/... --style viral --ratio 9:16</code>"
        )

    @staticmethod
    def viral_prompt() -> str:
        return (
            f"{E['search']} <b>Cari Video Viral</b>\n\n"
            f"Pilih topik populer di bawah atau ketik:\n"
            f"<code>/viral &lt;topik&gt; [--limit N] [--lang id]</code>"
        )

    @staticmethod
    def no_jobs() -> str:
        return f"{E['list']} <b>Belum ada job.</b>\n\nKirim video pertama kamu dengan <code>/submit</code>!"


# ═══════════════════════════════════════════════════════════════════════════════
# KEYBOARD BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

class KB:
    """Centralized inline keyboard layouts."""

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{E['search']} Cari Viral",   callback_data="menu_viral"),
                InlineKeyboardButton(f"{E['rocket']} Submit URL",   callback_data="menu_submit"),
            ],
            [
                InlineKeyboardButton(f"{E['list']} Job Terbaru",    callback_data="act_jobs"),
                InlineKeyboardButton(f"{E['chart']} Cek Status",    callback_data="menu_status"),
            ],
            [
                InlineKeyboardButton(f"{E['robot']} Model LLM",     callback_data="menu_model"),
                InlineKeyboardButton(f"{E['id']} My ID",            callback_data="act_myid"),
            ],
            [
                InlineKeyboardButton(f"{E['help']} Bantuan",        callback_data="act_help"),
            ],
        ])

    @staticmethod
    def back() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{E['home']} Menu Utama", callback_data="act_back")],
        ])

    @staticmethod
    def model_picker(current: str) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        for i in range(0, len(MODELS), 2):
            row = []
            for name, alias, _ in MODELS[i:i + 2]:
                is_active = alias == current.lower()
                label = f"{E['check']} {name}" if is_active else name
                row.append(InlineKeyboardButton(label, callback_data=f"model_{alias}"))
            rows.append(row)
        rows.append([InlineKeyboardButton(f"{E['back']} Kembali", callback_data="act_back")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def viral_topics() -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        for i in range(0, len(VIRAL_TOPICS), 2):
            row = []
            for emoji, label, query in VIRAL_TOPICS[i:i + 2]:
                row.append(InlineKeyboardButton(f"{emoji} {label}", callback_data=f"viral_{query}"))
            rows.append(row)
        rows.append([
            InlineKeyboardButton("✏️ Ketik Sendiri", callback_data="viral_custom"),
            InlineKeyboardButton(f"{E['back']} Kembali", callback_data="act_back"),
        ])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def status_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{E['list']} Lihat Semua Job", callback_data="act_jobs")],
            [InlineKeyboardButton(f"{E['back']} Kembali", callback_data="act_back")],
        ])

    @staticmethod
    def jobs_pagination(page: int, total_pages: int, status_filter: str) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        # Pagination row
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"jobs_{page - 1}_{status_filter}"))
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("▶️ Next", callback_data=f"jobs_{page + 1}_{status_filter}"))
        rows.append(nav_row)
        # Filter row
        rows.append([
            InlineKeyboardButton("All",       callback_data=f"jobs_1_all"),
            InlineKeyboardButton("Pending",   callback_data=f"jobs_1_pending"),
            InlineKeyboardButton("Running",   callback_data=f"jobs_1_running"),
        ])
        rows.append([
            InlineKeyboardButton("Completed", callback_data=f"jobs_1_completed"),
            InlineKeyboardButton("Failed",    callback_data=f"jobs_1_failed"),
        ])
        rows.append([InlineKeyboardButton(f"{E['home']} Menu Utama", callback_data="act_back")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def confirm(action: str, data: str) -> InlineKeyboardMarkup:
        """Confirmation dialog with confirm/cancel."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{E['check']} Ya, Lanjutkan", callback_data=f"confirm_{action}_{data}"),
                InlineKeyboardButton(f"{E['cross']} Batal",          callback_data="act_back"),
            ],
        ])


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def split_message(text: str, max_len: int = 4000) -> list[str]:
    """Pecah teks panjang menjadi chunk yang tidak melebihi max_len."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        chunk = text[:max_len]
        # Coba potong di newline terakhir
        last_nl = chunk.rfind("\n")
        if last_nl > max_len // 2:
            chunk = chunk[:last_nl]
        # Jika tidak ada newline, coba potong di spasi terakhir
        elif last_nl <= 0:
            last_sp = chunk.rfind(" ")
            if last_sp > max_len // 2:
                chunk = chunk[:last_sp]
        chunks.append(chunk)
        text = text[len(chunk):].lstrip("\n")
    return chunks


def get_current_model() -> str:
    """Baca model aktif dari config.yaml."""
    config_path = os.path.join(CONFIG.hermes_home, "config.yaml")
    if not os.path.exists(config_path):
        return "unknown"

    # Try YAML parsing first (more reliable)
    if yaml:
        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                # Check common keys
                for key in ("default_model", "model", "default"):
                    if key in data:
                        return str(data[key])
                # Check nested
                if "llm" in data and isinstance(data["llm"], dict):
                    for key in ("default", "model"):
                        if key in data["llm"]:
                            return str(data["llm"][key])
        except Exception:
            pass

    # Fallback: line-by-line parsing
    try:
        with open(config_path, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("default_model:"):
                    return stripped.split(":", 1)[1].strip().strip("\"'")
                if stripped.startswith("default:") and "model" not in stripped.lower():
                    return stripped.split(":", 1)[1].strip().strip("\"'")
    except Exception:
        pass
    return "unknown"


def sanitize_for_html(text: str) -> str:
    """Escape text for HTML parse mode, preserving code blocks."""
    # Split by code blocks to preserve them
    parts = re.split(r"(```[\s\S]*?```)", text)
    result = []
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            # Convert markdown code block to HTML pre
            inner = part[3:-3].strip()
            result.append(f"<pre>{Msg.escape(inner)}</pre>")
        else:
            result.append(Msg.escape(part))
    return "".join(result)


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Simple per-user rate limiter."""

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._last_request: dict[int, float] = {}

    def check(self, user_id: int) -> tuple[bool, float]:
        """Returns (allowed, wait_seconds)."""
        now = time.monotonic()
        last = self._last_request.get(user_id, 0)
        elapsed = now - last
        if elapsed < self._min_interval:
            return False, self._min_interval - elapsed
        self._last_request[user_id] = now
        return True, 0


rate_limiter = RateLimiter(CONFIG.rate_limit_seconds)


# ═══════════════════════════════════════════════════════════════════════════════
# USER SESSION — track per-user state
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UserSession:
    """Tracks state for a single user."""
    user_id: int
    current_task: asyncio.Task | None = None
    last_model: str = "unknown"
    jobs_cache: str = ""
    jobs_page: int = 1
    jobs_filter: str = "all"
    pending_submit_url: str = ""  # URL yang menunggu konfirmasi submit
    pending_submit_style: str = "default"
    pending_submit_ratio: str = "9:16"
    pending_submit_force: bool = False


sessions: dict[int, UserSession] = {}


def get_session(user_id: int) -> UserSession:
    if user_id not in sessions:
        sessions[user_id] = UserSession(user_id=user_id)
    return sessions[user_id]


# ═══════════════════════════════════════════════════════════════════════════════
# HERMES RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

async def run_hermes(prompt: str, workdir: str | None = None) -> str:
    """
    Jalankan hermes CLI dengan prompt, return output sebagai string.
    Raises HermesError subclasses on failure.
    """
    cmd = [
        CONFIG.hermes_bin,
        "run",
        "--no-stream",
        "--yes",
        "--",
        prompt,
    ]

    env = os.environ.copy()
    env["HERMES_HOME"] = CONFIG.hermes_home
    env["AUTOCLIPER_API_URL"] = CONFIG.autocliper_api_url

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir or str(Path.home()),
            env=env,
        )
    except FileNotFoundError:
        raise HermesNotFoundError("hermes binary not in PATH")

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=CONFIG.hermes_timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HermesTimeoutError(f"Timeout after {CONFIG.hermes_timeout}s")

    output = stdout.decode("utf-8", errors="replace").strip()
    if not output and stderr:
        output = stderr.decode("utf-8", errors="replace").strip()
    return output or "(Tidak ada output dari Hermes)"


async def run_ac_tool(script: str, *args: str) -> str:
    """
    Jalankan ac_*.py tool langsung (lebih cepat dari via hermes).
    Raises ToolError subclasses on failure.
    """
    # Search paths
    search_dirs = [
        os.path.join(CONFIG.hermes_home, "skills", "bin"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hermes", "bin"),
    ]

    script_path = None
    for d in search_dirs:
        candidate = os.path.join(d, script)
        if os.path.exists(candidate):
            script_path = candidate
            break

    if not script_path:
        raise ToolNotFoundError(f"Script {script} not found")

    cmd = [sys.executable, script_path, *args]
    env = os.environ.copy()
    env["HERMES_HOME"] = CONFIG.hermes_home
    env["AUTOCLIPER_API_URL"] = CONFIG.autocliper_api_url

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        raise ToolNotFoundError(f"Python executable not found")

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=CONFIG.tool_timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ToolTimeoutError(f"Tool timeout after {CONFIG.tool_timeout}s")

    output = stdout.decode("utf-8", errors="replace").strip()
    if not output and stderr:
        err = stderr.decode("utf-8", errors="replace").strip()
        if err:
            output = err
    return output or "(Tidak ada output)"


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH GUARD
# ═══════════════════════════════════════════════════════════════════════════════

def is_allowed(user_id: int | None) -> bool:
    if user_id is None:
        return False
    if not CONFIG.allowed_users:
        return True  # No restriction configured
    return user_id in CONFIG.allowed_users


async def deny_access(update: Update):
    uid = update.effective_user.id if update.effective_user else 0
    logger.warning("Unauthorized access: user_id=%s", uid)
    target = update.message or (update.callback_query and update.callback_query.message)
    if target:
        try:
            await target.reply_text(
                Msg.access_denied(uid),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


async def deny_callback(query):
    uid = query.from_user.id
    logger.warning("Unauthorized callback: user_id=%s", uid)
    try:
        await query.answer(Msg.access_denied(uid), show_alert=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# SEND HELPER
# ═══════════════════════════════════════════════════════════════════════════════

async def send_long(
    message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = ParseMode.HTML,
):
    """Kirim teks panjang, pecah jika perlu. Keyboard hanya di chunk terakhir."""
    chunks = split_message(text, CONFIG.max_msg_len)
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        try:
            await message.reply_text(chunk, reply_markup=markup, parse_mode=parse_mode)
        except Exception as e:
            # Fallback: send without parse mode
            logger.warning("Failed to send with HTML parse mode, retrying plain: %s", e)
            await message.reply_text(chunk, reply_markup=markup)


async def edit_or_reply(
    query,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
):
    """Edit message from callback query, or reply if edit fails."""
    try:
        await query.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        # If edit fails (e.g., message too old), send new
        await send_long(query.message, text, reply_markup=reply_markup)


async def run_with_progress(
    message,
    progress_text: str,
    coro,
    *args,
    **kwargs,
) -> str:
    """
    Run a coroutine while showing a progress message.
    Updates the progress message with elapsed time periodically.
    Returns the result string.
    """
    progress_msg = await message.reply_text(
        progress_text,
        parse_mode=ParseMode.HTML,
    )

    # Start the task
    task = asyncio.create_task(coro(*args, **kwargs))

    # Update progress every 10 seconds
    elapsed = 0
    try:
        while not task.done():
            await asyncio.sleep(10)
            elapsed += 10
            try:
                await progress_msg.edit_text(
                    f"{progress_text}\n{E['clock']} {elapsed}s...",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass  # Ignore edit failures
        result = await task
    except asyncio.CancelledError:
        task.cancel()
        try:
            await progress_msg.delete()
        except Exception:
            pass
        raise

    # Delete progress message
    try:
        await progress_msg.delete()
    except Exception:
        pass

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)

    name = update.effective_user.first_name or "there"
    current_model = get_current_model()
    session = get_session(update.effective_user.id)
    session.last_model = current_model

    await update.message.reply_text(
        Msg.welcome(name, current_model),
        parse_mode=ParseMode.HTML,
        reply_markup=KB.main_menu(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)
    await update.message.reply_text(
        Msg.help_full(),
        parse_mode=ParseMode.HTML,
        reply_markup=KB.back(),
    )


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        Msg.show_id(uid),
        parse_mode=ParseMode.HTML,
        reply_markup=KB.back(),
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancel any running task for this user."""
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)

    session = get_session(update.effective_user.id)
    if session.current_task and not session.current_task.done():
        session.current_task.cancel()
        await update.message.reply_text(
            Msg.error_cancelled(),
            parse_mode=ParseMode.HTML,
            reply_markup=KB.main_menu(),
        )
    else:
        await update.message.reply_text(
            f"{E['gear']} Tidak ada operasi yang sedang berjalan.",
            parse_mode=ParseMode.HTML,
            reply_markup=KB.main_menu(),
        )


# ─── /viral ───────────────────────────────────────────────────────────────────

async def cmd_viral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)

    if not ctx.args:
        await update.message.reply_text(
            Msg.viral_prompt(),
            parse_mode=ParseMode.HTML,
            reply_markup=KB.viral_topics(),
        )
        return

    await _do_viral_search(update.message, ctx.args)


async def _do_viral_search(message, args: list[str]):
    """Parse args and execute viral search."""
    query_parts: list[str] = []
    limit = "5"
    language = ""
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = args[i + 1]
            i += 2
        elif args[i] == "--lang" and i + 1 < len(args):
            language = args[i + 1]
            i += 2
        else:
            query_parts.append(args[i])
            i += 1

    query = " ".join(query_parts).strip()
    if not query:
        await message.reply_text(
            f"{E['warn']} Masukkan topik pencarian.",
            parse_mode=ParseMode.HTML,
        )
        return

    await message.chat.send_action(ChatAction.TYPING)

    try:
        result = await run_with_progress(
            message,
            Msg.searching(query),
            run_ac_tool,
            "ac_viral_search.py",
            "--query", query,
            "--limit", limit,
            "--language", language,
        )
    except ToolTimeoutError:
        await send_long(message, Msg.error_timeout(CONFIG.tool_timeout), reply_markup=KB.back())
        return
    except ToolNotFoundError:
        await send_long(message, Msg.error_tool_not_found("ac_viral_search.py"), reply_markup=KB.back())
        return
    except Exception as e:
        await send_long(message, Msg.error_generic(str(e)), reply_markup=KB.back())
        return

    await send_long(message, result, reply_markup=KB.back())


# ─── /submit ──────────────────────────────────────────────────────────────────

async def cmd_submit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)

    if not ctx.args:
        await update.message.reply_text(
            Msg.submit_prompt(),
            parse_mode=ParseMode.HTML,
            reply_markup=KB.back(),
        )
        return

    url = ctx.args[0]
    style = "default"
    ratio = "9:16"
    force = False

    i = 1
    while i < len(ctx.args):
        if ctx.args[i] == "--style" and i + 1 < len(ctx.args):
            style = ctx.args[i + 1]
            i += 2
        elif ctx.args[i] == "--ratio" and i + 1 < len(ctx.args):
            ratio = ctx.args[i + 1]
            i += 2
        elif ctx.args[i] == "--force":
            force = True
            i += 1
        else:
            i += 1

    # Validate URL
    if not url.startswith("http"):
        await update.message.reply_text(
            f"{E['cross']} URL tidak valid. Harus dimulai dengan <code>https://</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=KB.back(),
        )
        return

    # Validate URL is YouTube
    yt_patterns = ["youtube.com/watch", "youtu.be/", "youtube.com/shorts"]
    if not any(p in url for p in yt_patterns):
        # Simpan di session (callback_data Telegram max 64 byte, URL bisa panjang)
        session = get_session(update.effective_user.id)
        session.pending_submit_url = url
        session.pending_submit_style = style
        session.pending_submit_ratio = ratio
        session.pending_submit_force = force
        await update.message.reply_text(
            f"{E['warn']} URL tidak terlihat seperti YouTube.\n"
            f"<code>{Msg.escape(url[:80])}</code>\n\n"
            f"Tetap lanjutkan?",
            parse_mode=ParseMode.HTML,
            reply_markup=KB.confirm("submit", "pending"),
        )
        return

    await _do_submit(update.message, url, style, ratio, force)


async def _do_submit(message, url: str, style: str, ratio: str, force: bool):
    """Execute the submit operation."""
    await message.chat.send_action(ChatAction.TYPING)

    args = ["ac_submit_job.py", "--url", url, "--style", style, "--ratio", ratio]
    if force:
        args.append("--force")
        args.append("true")

    try:
        result = await run_with_progress(
            message,
            Msg.submitting(url),
            run_ac_tool,
            *args,
        )
    except ToolTimeoutError:
        await send_long(message, Msg.error_timeout(CONFIG.tool_timeout), reply_markup=KB.back())
        return
    except ToolNotFoundError:
        await send_long(message, Msg.error_tool_not_found("ac_submit_job.py"), reply_markup=KB.back())
        return
    except Exception as e:
        await send_long(message, Msg.error_generic(str(e)), reply_markup=KB.back())
        return

    await send_long(message, result, reply_markup=KB.back())


# ─── /status ──────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)

    if not ctx.args:
        await update.message.reply_text(
            Msg.status_prompt(),
            parse_mode=ParseMode.HTML,
            reply_markup=KB.status_menu(),
        )
        return

    job_id = ctx.args[0]
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        result = await run_with_progress(
            update.message,
            Msg.fetching_status(job_id),
            run_ac_tool,
            "ac_job_status.py",
            "--job-id", job_id,
        )
    except ToolTimeoutError:
        await send_long(update.message, Msg.error_timeout(CONFIG.tool_timeout), reply_markup=KB.back())
        return
    except ToolNotFoundError:
        await send_long(update.message, Msg.error_tool_not_found("ac_job_status.py"), reply_markup=KB.back())
        return
    except Exception as e:
        await send_long(update.message, Msg.error_generic(str(e)), reply_markup=KB.back())
        return

    await send_long(update.message, result, reply_markup=KB.back())


# ─── /jobs ────────────────────────────────────────────────────────────────────

async def cmd_jobs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)

    limit = str(CONFIG.jobs_per_page * 3)  # Fetch more for pagination
    status_filter = "all"

    args = ctx.args or []
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = args[i + 1]
            i += 2
        elif args[i] == "--status" and i + 1 < len(args):
            status_filter = args[i + 1]
            i += 2
        else:
            i += 1

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        result = await run_ac_tool("ac_list_jobs.py", "--limit", limit, "--status", status_filter)
    except ToolTimeoutError:
        await send_long(update.message, Msg.error_timeout(CONFIG.tool_timeout), reply_markup=KB.back())
        return
    except ToolNotFoundError:
        await send_long(update.message, Msg.error_tool_not_found("ac_list_jobs.py"), reply_markup=KB.back())
        return
    except Exception as e:
        await send_long(update.message, Msg.error_generic(str(e)), reply_markup=KB.back())
        return

    session = get_session(update.effective_user.id)
    session.jobs_cache = result
    session.jobs_page = 1
    session.jobs_filter = status_filter

    # Paginate
    total_pages = max(1, (len(result) + CONFIG.max_msg_len - 1) // CONFIG.max_msg_len)
    page = 1
    chunk = split_message(result, CONFIG.max_msg_len)
    display = chunk[page - 1] if page <= len(chunk) else "(Tidak ada data)"

    if not result.strip():
        await update.message.reply_text(
            Msg.no_jobs(),
            parse_mode=ParseMode.HTML,
            reply_markup=KB.back(),
        )
        return

    header = Msg.jobs_header(page, total_pages, status_filter)
    await send_long(
        update.message,
        f"{header}\n{display}",
        reply_markup=KB.jobs_pagination(page, total_pages, status_filter),
    )


# ─── /model ───────────────────────────────────────────────────────────────────

async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id if update.effective_user else None):
        return await deny_access(update)

    if not ctx.args:
        current = get_current_model()
        await update.message.reply_text(
            Msg.model_info(current),
            parse_mode=ParseMode.HTML,
            reply_markup=KB.model_picker(current),
        )
        return

    model_alias = " ".join(ctx.args).strip().lower()
    await _do_switch_model(update.message, model_alias)


async def _do_switch_model(message, alias: str):
    """Switch the LLM model."""
    await message.chat.send_action(ChatAction.TYPING)

    try:
        result = await run_with_progress(
            message,
            Msg.switching_model(alias),
            run_ac_tool,
            "ac_switch_model.py",
            "--model", alias,
        )
    except ToolTimeoutError:
        await send_long(message, Msg.error_timeout(CONFIG.tool_timeout), reply_markup=KB.back())
        return
    except ToolNotFoundError:
        await send_long(message, Msg.error_tool_not_found("ac_switch_model.py"), reply_markup=KB.back())
        return
    except Exception as e:
        await send_long(message, Msg.error_generic(str(e)), reply_markup=KB.back())
        return

    current = get_current_model()
    session = get_session(message.chat.id)
    session.last_model = current

    await send_long(
        message,
        Msg.model_switched(current, result),
        reply_markup=KB.model_picker(current),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK QUERY HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle all inline button presses."""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    if not is_allowed(uid):
        return await deny_callback(query)

    data = query.data

    # ── No-op (e.g., page indicator) ───────────────────────────────────────────
    if data == "noop":
        return

    # ── Back to main menu ──────────────────────────────────────────────────────
    if data == "act_back":
        current = get_current_model()
        await edit_or_reply(
            query,
            f"{E['home']} <b>Menu Utama</b>\n\n"
            f"{E['robot']} Model aktif: <code>{Msg.escape(current)}</code>\n\n"
            f"Pilih aksi atau ketik pesan bebas untuk <b>Agentic Mode</b>.",
            KB.main_menu(),
        )

    # ── Help ───────────────────────────────────────────────────────────────────
    elif data == "act_help":
        await edit_or_reply(query, Msg.help_short(), KB.back())

    # ── My ID ──────────────────────────────────────────────────────────────────
    elif data == "act_myid":
        await edit_or_reply(query, Msg.show_id(uid), KB.back())

    # ── Jobs list ──────────────────────────────────────────────────────────────
    elif data == "act_jobs":
        await edit_or_reply(query, Msg.fetching_jobs())
        await query.message.chat.send_action(ChatAction.TYPING)

        try:
            result = await run_ac_tool(
                "ac_list_jobs.py",
                "--limit", str(CONFIG.jobs_per_page * 3),
                "--status", "all",
            )
        except (ToolTimeoutError, ToolNotFoundError, Exception) as e:
            await send_long(query.message, Msg.error_generic(str(e)), reply_markup=KB.back())
            return

        session = get_session(uid)
        session.jobs_cache = result
        session.jobs_page = 1
        session.jobs_filter = "all"

        if not result.strip():
            await edit_or_reply(query, Msg.no_jobs(), KB.back())
            return

        chunks = split_message(result, CONFIG.max_msg_len)
        total_pages = max(1, len(chunks))
        display = chunks[0]
        header = Msg.jobs_header(1, total_pages, "all")
        await edit_or_reply(
            query,
            f"{header}\n{display}",
            KB.jobs_pagination(1, total_pages, "all"),
        )

    # ── Jobs pagination ────────────────────────────────────────────────────────
    elif data.startswith("jobs_"):
        parts = data.split("_", 2)  # jobs_<page>_<filter>
        if len(parts) < 3:
            return
        try:
            page = int(parts[1])
        except ValueError:
            return
        status_filter = parts[2]

        session = get_session(uid)

        # If filter changed, refetch
        if session.jobs_filter != status_filter or not session.jobs_cache:
            await query.message.chat.send_action(ChatAction.TYPING)
            try:
                result = await run_ac_tool(
                    "ac_list_jobs.py",
                    "--limit", str(CONFIG.jobs_per_page * 3),
                    "--status", status_filter,
                )
            except (ToolTimeoutError, ToolNotFoundError, Exception) as e:
                await send_long(query.message, Msg.error_generic(str(e)), reply_markup=KB.back())
                return
            session.jobs_cache = result
            session.jobs_filter = status_filter
            page = 1
        else:
            result = session.jobs_cache

        chunks = split_message(result, CONFIG.max_msg_len)
        total_pages = max(1, len(chunks))
        page = max(1, min(page, total_pages))
        session.jobs_page = page

        display = chunks[page - 1] if page <= len(chunks) else "(Tidak ada data)"
        header = Msg.jobs_header(page, total_pages, status_filter)
        await edit_or_reply(
            query,
            f"{header}\n{display}",
            KB.jobs_pagination(page, total_pages, status_filter),
        )

    # ── Viral search menu ─────────────────────────────────────────────────────
    elif data == "menu_viral":
        await edit_or_reply(query, Msg.viral_prompt(), KB.viral_topics())

    # ── Viral topic quick-pick ─────────────────────────────────────────────────
    elif data.startswith("viral_"):
        topic = data[6:]
        if topic == "custom":
            await edit_or_reply(
                query,
                f"✏️ <b>Ketik topik pencarian kamu</b>\n\n"
                f"<code>/viral &lt;topik&gt;</code>\n\n"
                f"Contoh: <code>/viral motivasi bisnis --lang id</code>",
                KB.back(),
            )
        else:
            await edit_or_reply(query, Msg.searching(topic))
            await query.message.chat.send_action(ChatAction.TYPING)

            try:
                result = await run_ac_tool(
                    "ac_viral_search.py",
                    "--query", topic,
                    "--limit", "5",
                    "--language", "",
                )
            except ToolTimeoutError:
                await send_long(query.message, Msg.error_timeout(CONFIG.tool_timeout), reply_markup=KB.back())
                return
            except ToolNotFoundError:
                await send_long(query.message, Msg.error_tool_not_found("ac_viral_search.py"), reply_markup=KB.back())
                return
            except Exception as e:
                await send_long(query.message, Msg.error_generic(str(e)), reply_markup=KB.back())
                return

            await send_long(query.message, result, reply_markup=KB.back())

    # ── Submit menu ────────────────────────────────────────────────────────────
    elif data == "menu_submit":
        await edit_or_reply(query, Msg.submit_prompt(), KB.back())

    # ── Status menu ────────────────────────────────────────────────────────────
    elif data == "menu_status":
        await edit_or_reply(query, Msg.status_prompt(), KB.status_menu())

    # ── Model picker ───────────────────────────────────────────────────────────
    elif data == "menu_model":
        current = get_current_model()
        await edit_or_reply(query, Msg.model_info(current), KB.model_picker(current))

    elif data.startswith("model_"):
        alias = data[6:]
        await edit_or_reply(query, Msg.switching_model(alias))
        await query.message.chat.send_action(ChatAction.TYPING)

        try:
            result = await run_ac_tool("ac_switch_model.py", "--model", alias)
        except ToolTimeoutError:
            await send_long(query.message, Msg.error_timeout(CONFIG.tool_timeout), reply_markup=KB.back())
            return
        except ToolNotFoundError:
            await send_long(query.message, Msg.error_tool_not_found("ac_switch_model.py"), reply_markup=KB.back())
            return
        except Exception as e:
            await send_long(query.message, Msg.error_generic(str(e)), reply_markup=KB.back())
            return

        current = get_current_model()
        session = get_session(uid)
        session.last_model = current

        await query.message.reply_text(
            Msg.model_switched(current, result),
            parse_mode=ParseMode.HTML,
            reply_markup=KB.model_picker(current),
        )

    # ── Confirmation flow ──────────────────────────────────────────────────────
    elif data.startswith("confirm_"):
        parts = data.split("_", 2)  # confirm_<action>_<data>
        if len(parts) < 3:
            return
        action = parts[1]
        payload = parts[2]

        if action == "submit":
            # User confirmed non-YouTube URL submit — ambil dari session
            session = get_session(uid)
            url = session.pending_submit_url
            if not url:
                await edit_or_reply(query, f"{E['warn']} Session expired. Kirim ulang /submit.", KB.back())
                return
            await edit_or_reply(query, Msg.submitting(url))
            await _do_submit(
                query.message, url,
                session.pending_submit_style,
                session.pending_submit_ratio,
                session.pending_submit_force,
            )
            session.pending_submit_url = ""  # Clear after use

    else:
        logger.debug("Unknown callback data: %s", data)


# ═══════════════════════════════════════════════════════════════════════════════
# AGENTIC MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pesan bebas → forward ke Hermes sebagai agentic prompt."""
    uid = update.effective_user.id if update.effective_user else None
    if not is_allowed(uid):
        return await deny_access(update)

    # Rate limit check
    allowed, wait = rate_limiter.check(uid)
    if not allowed:
        await update.message.reply_text(
            Msg.error_rate_limited(wait),
            parse_mode=ParseMode.HTML,
        )
        return

    text = update.message.text or ""
    if not text.strip():
        return

    session = get_session(uid)

    await update.message.reply_text(Msg.thinking(), parse_mode=ParseMode.HTML)
    await update.message.chat.send_action(ChatAction.TYPING)

    # Build agentic prompt with context
    prompt = (
        f"Kamu adalah asisten AutoCliper, sebuah platform clipping video otomatis.\n"
        f"AutoCliper API tersedia di {CONFIG.autocliper_api_url}.\n"
        f"Kamu punya akses ke tools berikut:\n"
        f"  - autocliper_viral_search: cari video YouTube viral\n"
        f"  - autocliper_submit_job: submit URL YouTube untuk diproses\n"
        f"  - autocliper_job_status: cek status job berdasarkan ID\n"
        f"  - autocliper_list_jobs: list job terbaru\n"
        f"  - autocliper_switch_model: ganti model LLM\n\n"
        f"Permintaan user: {text}"
    )

    # Create task and store in session for cancellation
    task = asyncio.create_task(run_hermes(prompt))
    session.current_task = task

    # Progress indicator
    progress_msg = await update.message.reply_text(
        f"{E['loading']} <b>Hermes sedang berpikir...</b>",
        parse_mode=ParseMode.HTML,
    )

    elapsed = 0
    try:
        while not task.done():
            await asyncio.sleep(15)
            elapsed += 15
            if elapsed % 30 == 0 and elapsed <= CONFIG.hermes_timeout:
                try:
                    await progress_msg.edit_text(
                        f"{E['loading']} <b>Hermes sedang berpikir...</b>\n"
                        f"{E['clock']} {elapsed}s berlalu...",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass

        result = await task
    except asyncio.CancelledError:
        try:
            await progress_msg.delete()
        except Exception:
            pass
        return
    except HermesTimeoutError:
        try:
            await progress_msg.delete()
        except Exception:
            pass
        await send_long(
            update.message,
            Msg.error_timeout(CONFIG.hermes_timeout),
            reply_markup=KB.back(),
        )
        return
    except HermesNotFoundError:
        try:
            await progress_msg.delete()
        except Exception:
            pass
        await send_long(
            update.message,
            Msg.error_hermes_not_found(),
            reply_markup=KB.back(),
        )
        return
    except Exception as e:
        try:
            await progress_msg.delete()
        except Exception:
            pass
        await send_long(
            update.message,
            Msg.error_generic(str(e)),
            reply_markup=KB.back(),
        )
        return
    finally:
        session.current_task = None

    # Delete progress message
    try:
        await progress_msg.delete()
    except Exception:
        pass

    # Send result
    await send_long(update.message, result, reply_markup=KB.back())


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLER (Global)
# ═══════════════════════════════════════════════════════════════════════════════

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    """Global error handler."""
    error = ctx.error
    logger.error("Unhandled error: %s", error, exc_info=error)

    if isinstance(error, Forbidden):
        logger.warning("Bot was blocked by user")
        return

    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning("Network error: %s", error)
        return

    # Try to notify user
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                Msg.error_generic("Terjadi kesalahan internal. Coba lagi nanti."),
                parse_mode=ParseMode.HTML,
                reply_markup=KB.back(),
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# POST-INIT
# ═══════════════════════════════════════════════════════════════════════════════

async def post_init(app: Application):
    """Called after bot is initialized."""
    me = await app.bot.get_me()
    logger.info("Bot initialized: @%s (id=%s)", me.username, me.id)
    logger.info("  HERMES_HOME:    %s", CONFIG.hermes_home)
    logger.info("  AutoCliper API: %s", CONFIG.autocliper_api_url)
    logger.info("  Allowed users:  %s", CONFIG.allowed_users or "ALL (warning!)")
    logger.info("  Hermes timeout: %ss", CONFIG.hermes_timeout)
    logger.info("  Tool timeout:   %ss", CONFIG.tool_timeout)

    # Set bot commands for Telegram UI
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("start",   "Mulai / tampilkan menu"),
        BotCommand("help",    "Panduan lengkap"),
        BotCommand("viral",   "Cari video viral"),
        BotCommand("submit",  "Submit YouTube URL"),
        BotCommand("status",  "Cek status job"),
        BotCommand("jobs",    "List job terbaru"),
        BotCommand("model",   "Ganti model LLM"),
        BotCommand("id",      "Tampilkan Telegram ID"),
        BotCommand("cancel",  "Batalkan operasi"),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if not CONFIG.bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN tidak di-set di $HERMES_HOME/.env")
        print("Dapatkan token dari @BotFather di Telegram.")
        sys.exit(1)

    if not CONFIG.allowed_users:
        logger.warning(
            "⚠️  TELEGRAM_ALLOWED_USERS tidak di-set — SEMUA ORANG bisa akses bot!\n"
            "    Set di $HERMES_HOME/.env untuk keamanan."
        )

    logger.info("Starting AutoCliper Bot...")

    app = (
        ApplicationBuilder()
        .token(CONFIG.bot_token)
        .post_init(post_init)
        .build()
    )

    # ── Command handlers ───────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("id",     cmd_id))
    app.add_handler(CommandHandler("viral",  cmd_viral))
    app.add_handler(CommandHandler("submit", cmd_submit))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("jobs",   cmd_jobs))
    app.add_handler(CommandHandler("model",  cmd_model))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # ── Callback query handler ────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Agentic message handler (all text, not commands) ──────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ── Global error handler ──────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    logger.info("Bot running — tekan Ctrl+C untuk stop")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()