#!/usr/bin/env python3
"""
Final bot_voice.py — exact UX requested.

Behavior changes only (kept the rest of the program intact):
 - /start message: "Masukkan password cuy... this bot isn't for public"
 - Password default: "najma"
 - After correct password bot responds: "masukkan Audio dan judul video yang akan diupload"
 - Accepts audio and title in any order. If only one is present it asks for the other.
 - When both present -> processes immediately and returns the YouTube link.
 - YouTube upload set to public and selfDeclaredMadeForKids = False.

You still need ffmpeg, google client credentials and (optionally) aria2c/pyrogram.
"""
import os
import time
import logging
import asyncio
import subprocess
import shutil
import sys
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Pyrogram (MTProto) import — optional fallback for large media
PYRO_CLIENT = None
try:
    from pyrogram import Client as PyroClient
    PYRO_AVAILABLE = True
except Exception:
    PYRO_AVAILABLE = False

# Optional Google libs for YouTube upload
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_AVAILABLE = True
except Exception:
    GOOGLE_AVAILABLE = False

# ------------------- CONFIG -------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "") or "8595012112:AAFQuxeJ0VHfXSQ9TPCjpZAF2UtDEB9te2Y"
IMAGE_FILE = os.environ.get("IMAGE_FILE", "image.jpg")
TEMP = os.environ.get("TEMP_DIR", "temp")
# requested password:
PASSWORD = os.environ.get("BOT_PASSWORD", "najma")
PENDING_TIMEOUT = 60 * 60 * 6  # 6 hours
MAX_PASSWORD_ATTEMPTS = 3
UPLOAD_TO_YOUTUBE = os.environ.get("UPLOAD_TO_YOUTUBE", "1") == "1"
CLIENT_SECRETS = os.environ.get("CLIENT_SECRETS", "client_secrets.json")
TOKEN_FILE = os.environ.get("YT_TOKEN_FILE", "token.json")
YT_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]

os.makedirs(TEMP, exist_ok=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if getattr(sys, "frozen", False) is False else os.path.dirname(sys.executable)
IMAGE_PATH = IMAGE_FILE if os.path.isabs(IMAGE_FILE) else os.path.join(BASE_DIR, IMAGE_FILE)

# pending_uploads[chat_id] = {
#   "status": one of {"awaiting_password","awaiting_both","awaiting_title","awaiting_audio","processing"},
#   "orig_path": str|None,
#   "title": str|None,
#   "attempts": int,
#   "timestamp": float,
#   "input_kind": str|None,
#   "doc_name": str|None
# }
pending_uploads = {}
_executor = ThreadPoolExecutor(max_workers=2)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------- helpers -------------------
def ffmpeg_exists() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False

def any_to_wav(orig: str, wav: str):
    r = subprocess.run(["ffmpeg", "-y", "-i", orig, wav], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr or "ffmpeg any->wav failed")

def wav_to_mp3(wav: str, mp3: str):
    r = subprocess.run(["ffmpeg", "-y", "-i", wav, mp3], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr or "ffmpeg wav->mp3 failed")

def make_video(image: str, mp3: str, mp4: str, max_width: int = 720):
    vf = f"scale='min(iw,{max_width})':-2,pad=ceil(iw/2)*2:ceil(ih/2)*2"
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image,
        "-i", mp3,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-vf", vf,
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        mp4
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        logger.error("ffmpeg failed: %s", r.stderr)
        raise RuntimeError(r.stderr or "ffmpeg make video failed")

def is_audio_document(msg) -> bool:
    try:
        doc = msg.document
        if not doc:
            return False
        mt = getattr(doc, "mime_type", "") or ""
        return mt.startswith("audio/") or mt.endswith("/ogg")
    except Exception:
        return False

def cleanup_pending_expired():
    now = time.time()
    to_remove = []
    for chat_id, info in list(pending_uploads.items()):
        if now - info.get("timestamp", 0) > PENDING_TIMEOUT:
            to_remove.append(chat_id)
    for chat_id in to_remove:
        info = pending_uploads.pop(chat_id, None)
        if info:
            path = info.get("orig_path")
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    logger.info("Removed expired temp file %s for chat %s", path, chat_id)
            except Exception:
                logger.warning("Failed to remove expired temp file %s", path)

# safe_send helper (retry small messages)
async def safe_send(bot, chat_id, text, **kwargs):
    last_exc = None
    for attempt in range(1, 4):
        try:
            return await bot.send_message(chat_id, text, **kwargs)
        except Exception as e:
            last_exc = e
            logger.warning("safe_send attempt %d failed: %s", attempt, e)
            await asyncio.sleep(1.5 * attempt)
    raise last_exc

# ------------------- aria2c helpers -------------------
def find_aria2c():
    env_path = os.environ.get("ARIA2C_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    bin_name = "aria2c.exe" if os.name == "nt" else "aria2c"
    return shutil.which(bin_name)

def aria2_download(file_url: str, dest_path: str, temp_dir: str, max_connections: int = 16) -> bool:
    aria2c = find_aria2c()
    if not aria2c:
        logger.debug("aria2c not found")
        return False
    os.makedirs(temp_dir, exist_ok=True)
    out_name = os.path.basename(dest_path)
    cmd = [
        aria2c, "--check-certificate=true", "-c",
        f"-x{max_connections}", f"-s{max_connections}",
        "--max-tries=0", "--retry-wait=5", "--timeout=600",
        "--min-split-size=1M", "--allow-overwrite=true", "--continue=true",
        "--dir", temp_dir, "--out", out_name, file_url
    ]
    logger.info("Running aria2c: %s", " ".join(cmd))
    try:
        completed = subprocess.run(cmd, check=False)
        if completed.returncode == 0:
            tmp_path = os.path.join(temp_dir, out_name)
            try:
                os.replace(tmp_path, dest_path)
            except Exception:
                shutil.copyfile(tmp_path, dest_path)
                try:
                    os.remove(tmp_path)
                except Exception:
                    logger.debug("Could not remove tmp file %s", tmp_path)
            logger.info("aria2c finished and saved to %s", dest_path)
            return True
        else:
            logger.error("aria2c exit code %s", completed.returncode)
            return False
    except Exception as e:
        logger.exception("aria2c failed: %s", e)
        return False

# ------------------- YouTube utils (sync) -------------------
def get_youtube_service(client_secrets: str = CLIENT_SECRETS, token_file: str = TOKEN_FILE):
    if not GOOGLE_AVAILABLE:
        raise RuntimeError("Google libraries not installed")
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, YT_SCOPE)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, YT_SCOPE)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def upload_video_to_youtube(path: str, title: str, description: str = "", privacy: str = "public",
                            client_secrets: str = CLIENT_SECRETS, token_file: str = TOKEN_FILE) -> str:
    """
    Upload file `path` to YouTube, default privacy 'public' and explicitly declare NOT made for kids.
    """
    yt = get_youtube_service(client_secrets, token_file)

    body = {
        "snippet": {
            "title": title,
            "description": description
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False
        }
    }

    logger.info("Uploading to YouTube with privacy=%s title=%r", privacy, title)
    media = MediaFileUpload(path, mimetype="video/*", resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while True:
        status, response = req.next_chunk()
        if status:
            logger.info("YouTube upload progress: %s%%", int(status.progress() * 100))
        if response:
            break

    if "id" in response:
        return f"https://youtu.be/{response['id']}"
    raise RuntimeError("YouTube upload failed: " + str(response))

# ------------------- processing pipeline (blocking) -------------------
def process_and_upload_sync(orig_path: str, title: str, chat_id: int) -> str:
    base = os.path.splitext(os.path.basename(orig_path))[0]
    wav = os.path.join(TEMP, f"{base}.wav")
    mp3 = os.path.join(TEMP, f"{base}.mp3")
    mp4 = os.path.join(TEMP, f"{base}.mp4")
    try:
        any_to_wav(orig_path, wav)
        wav_to_mp3(wav, mp3)
        if not os.path.exists(IMAGE_PATH):
            raise RuntimeError(f"Image file missing: {IMAGE_PATH}")
        make_video(IMAGE_PATH, mp3, mp4)
        if not UPLOAD_TO_YOUTUBE:
            raise RuntimeError("UPLOAD_TO_YOUTUBE disabled")
        if not GOOGLE_AVAILABLE:
            raise RuntimeError("Google libraries not installed")
        if not os.path.exists(CLIENT_SECRETS):
            raise RuntimeError("client_secrets.json not found")
        url = upload_video_to_youtube(mp4, title=title, description="Uploaded by bot", privacy="public")
        return url
    finally:
        for p in (orig_path, wav, mp3, mp4):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                logger.debug("cleanup failed for %s", p)

# ------------------- ERROR HANDLER -------------------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception: %s", context.error)
    try:
        if update and getattr(update, "message", None):
            await safe_send(context.bot, update.effective_chat.id, "Terjadi error di server. Cek log.")
    except Exception:
        pass

# ------------------- HANDLERS (UX) -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # exact message requested
    await safe_send(context.bot, update.effective_chat.id, "Masukkan password cuy... this bot isn't for public")
    logger.info("Received /start from chat_id=%s", update.effective_chat.id)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    cleanup_pending_expired()

    # If user sends the password and there is no pending entry -> create awaiting_both
    if text == PASSWORD and chat_id not in pending_uploads:
        pending_uploads[chat_id] = {
            "status": "awaiting_both",
            "orig_path": None,
            "title": None,
            "attempts": 0,
            "timestamp": time.time(),
            "input_kind": None,
            "doc_name": None
        }
        # exact requested follow-up message:
        await safe_send(context.bot, chat_id, "masukkan Audio dan judul video yang akan diupload")
        logger.info("Password accepted and created pending entry for chat %s", chat_id)
        return

    # If there's an entry, handle states
    if chat_id in pending_uploads:
        info = pending_uploads[chat_id]
        status = info.get("status", "awaiting_password")

        # awaiting_password (user sent audio before password) -> validate password
        if status == "awaiting_password":
            info.setdefault("attempts", 0)
            if text == PASSWORD:
                info["status"] = "awaiting_both"
                await safe_send(context.bot, chat_id, "masukkan Audio dan judul video yang akan diupload")
                logger.info("Password accepted for chat %s", chat_id)
                return
            else:
                info["attempts"] += 1
                attempts_left = MAX_PASSWORD_ATTEMPTS - info["attempts"]
                if attempts_left <= 0:
                    # cleanup
                    orig = info.get("orig_path")
                    try:
                        if orig and os.path.exists(orig):
                            os.remove(orig)
                    except Exception:
                        logger.debug("Could not remove file %s", orig)
                    pending_uploads.pop(chat_id, None)
                    await safe_send(context.bot, chat_id, "Password salah berulang kali. Proses dibatalkan.")
                    return
                else:
                    await safe_send(context.bot, chat_id, f"Password salah. (sisa percobaan: {attempts_left})")
                    return

        # awaiting_both / awaiting_title / awaiting_audio accept text as title
        if status in ("awaiting_both", "awaiting_title", "awaiting_audio"):
            title = text.strip()
            if not title:
                await safe_send(context.bot, chat_id, "Judul tidak boleh kosong.")
                return
            info["title"] = title[:200]
            info["timestamp"] = time.time()

            # If audio (orig_path) already present -> process now
            if info.get("orig_path"):
                info["status"] = "processing"
                orig_path = info.get("orig_path")
                await safe_send(context.bot, chat_id, "Audio dan judul lengkap. Memproses & mengupload ke YouTube...")
                logger.info("Starting background processing for chat %s (title=%s)", chat_id, info["title"])

                loop = asyncio.get_running_loop()
                future = loop.run_in_executor(_executor, lambda: process_and_upload_sync(orig_path, info["title"], chat_id))

                async def _notify_when_done(fut):
                    try:
                        url = await fut
                        await context.bot.send_message(chat_id, f"✅ Selesai! Video terupload: {url}")
                        logger.info("Upload successful for chat %s -> %s", chat_id, url)
                    except Exception as e:
                        await context.bot.send_message(chat_id, f"❌ Upload gagal: {e}")
                        logger.exception("Background upload failed for chat %s", chat_id)
                    finally:
                        pending_uploads.pop(chat_id, None)

                asyncio.create_task(_notify_when_done(future))
                return
            else:
                # Title present but audio missing -> ask for audio
                info["status"] = "awaiting_audio"
                await safe_send(context.bot, chat_id, "Judul diterima. Silakan kirim audionya sekarang.")
                logger.info("Title stored for chat %s, waiting for audio (title=%s)", chat_id, info["title"])
                return

        # processing -> inform user
        if status == "processing":
            await safe_send(context.bot, chat_id, "Proses sedang berjalan. Mohon tunggu.")
            return

    # No pending entry and not password -> instruct to /start
    await safe_send(context.bot, chat_id,
                    "Ketik /start untuk memulai. Setelah itu masukkan password, lalu kirim audio dan judul (boleh urutannya terbalik).")

async def handle_audio_generic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = update.effective_chat.id

    file_id = None
    input_kind = None
    doc_name = None

    if getattr(msg, "voice", None):
        file_id = msg.voice.file_id
        input_kind = "voice"
        doc_name = getattr(msg.voice, "file_unique_id", None)
    elif getattr(msg, "audio", None):
        file_id = msg.audio.file_id
        input_kind = "audio"
        doc_name = getattr(msg.audio, "file_name", None)
    elif is_audio_document(msg):
        file_id = msg.document.file_id
        input_kind = "document"
        doc_name = getattr(msg.document, "file_name", None)

    if not file_id:
        await safe_send(context.bot, chat_id, "Tipe file bukan audio. Kirim audio/voice note.")
        logger.info("Received non-audio file; ignored.")
        return

    if not ffmpeg_exists():
        await safe_send(context.bot, chat_id, "ffmpeg tidak ditemukan di PATH. Install ffmpeg dan coba lagi.")
        logger.error("ffmpeg not found in PATH.")
        return

    cleanup_pending_expired()

    base = str(uuid4())
    orig_path = os.path.join(TEMP, f"{base}.orig")
    try:
        # If there's pending entry and status is awaiting_both/awaiting_title/awaiting_audio attach file
        if chat_id in pending_uploads and pending_uploads[chat_id].get("status") in ("awaiting_both", "awaiting_audio", "awaiting_title"):
            await safe_send(context.bot, chat_id, "Audio diterima. Mengunduh dan akan diproses jika judul sudah ada.")
        else:
            # no pending entry or different state -> ask for password after receiving audio
            await safe_send(context.bot, chat_id, "Audio diterima. Silakan masukkan password untuk melanjutkan.")
        logger.info("Downloading file for chat %s: file_id=%s", chat_id, file_id)

        # robust get_file with retries (to avoid read timeouts)
        file_obj = None
        for attempt in range(1, 5):
            try:
                file_obj = await context.bot.get_file(file_id)
                break
            except Exception as e:
                from telegram.error import TimedOut
                import httpx
                is_timeout = isinstance(e, TimedOut) or "ReadTimeout" in repr(e) or isinstance(e, httpx.ReadTimeout)
                logger.warning("get_file attempt %d failed for chat %s: %s (timeout=%s)", attempt, chat_id, e, is_timeout)
                if attempt < 4 and is_timeout:
                    await asyncio.sleep(min(5 * attempt, 20))
                    continue
                else:
                    logger.exception("get_file permanently failed for chat %s", chat_id)
                    await safe_send(context.bot, chat_id, "Gagal mengambil file dari Telegram (timeout). Coba kirim ulang.")
                    return

        file_url = file_obj.file_path
        logger.info("Attempting aria2c download for chat %s: %s", chat_id, file_url)

        ok = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: aria2_download(file_url=file_url, dest_path=orig_path, temp_dir=TEMP, max_connections=16)
        )

        if not ok:
            logger.warning("aria2c failed; trying Pyrogram (MTProto) fallback for chat %s", chat_id)
            pyrogram_ok = False
            if PYRO_CLIENT is not None:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: PYRO_CLIENT.download_media(file_id, file_name=orig_path)
                    )
                    pyrogram_ok = os.path.exists(orig_path)
                    if pyrogram_ok:
                        logger.info("Downloaded via Pyrogram to %s for chat %s", orig_path, chat_id)
                except Exception as e:
                    logger.exception("Pyrogram download failed for chat %s: %s", chat_id, e)
                    pyrogram_ok = False

            if not pyrogram_ok:
                logger.warning("Pyrogram fallback failed or unavailable; using built-in download with retries.")
                download_ok = False
                for attempt in range(1, 7):
                    try:
                        file_obj = await context.bot.get_file(file_id)
                        await file_obj.download_to_drive(orig_path)
                        download_ok = True
                        logger.info("Downloaded audio to %s for chat %s (attempt %d)", orig_path, chat_id, attempt)
                        break
                    except Exception as e:
                        from telegram.error import TimedOut
                        is_timeout = isinstance(e, TimedOut) or "timed out" in str(e).lower() or "ReadTimeout" in repr(e)
                        logger.warning("Fallback download attempt %d failed for chat %s: %s (timeout=%s)", attempt, chat_id, e, is_timeout)
                        if attempt < 6 and is_timeout:
                            await asyncio.sleep(min(30, 2 ** attempt))
                            continue
                        else:
                            logger.exception("Download permanently failed for chat %s", chat_id)
                            await safe_send(context.bot, chat_id, "Gagal mengunduh audio setelah beberapa percobaan. Coba kirim ulang.")
                            return
                if not download_ok:
                    await safe_send(context.bot, chat_id, "Gagal mengunduh audio. Coba kirim ulang.")
                    return

        # Attach to existing pending entry if present and awaiting
        if chat_id in pending_uploads and pending_uploads[chat_id].get("status") in ("awaiting_both", "awaiting_audio", "awaiting_title"):
            info = pending_uploads[chat_id]
            info["orig_path"] = orig_path
            info["input_kind"] = input_kind
            info["doc_name"] = doc_name
            info["timestamp"] = time.time()

            # If title already present -> process immediately
            if info.get("title"):
                info["status"] = "processing"
                await safe_send(context.bot, chat_id, "Audio dan judul lengkap. Memproses & mengupload ke YouTube...")
                logger.info("Starting background processing for chat %s (title=%s)", chat_id, info["title"])

                loop = asyncio.get_running_loop()
                future = loop.run_in_executor(_executor, lambda: process_and_upload_sync(info["orig_path"], info["title"], chat_id))

                async def _notify_when_done(fut):
                    try:
                        url = await fut
                        await context.bot.send_message(chat_id, f"✅ Selesai! Video terupload: {url}")
                        logger.info("Upload successful for chat %s -> %s", chat_id, url)
                    except Exception as e:
                        await context.bot.send_message(chat_id, f"❌ Upload gagal: {e}")
                        logger.exception("Background upload failed for chat %s", chat_id)
                    finally:
                        pending_uploads.pop(chat_id, None)

                asyncio.create_task(_notify_when_done(future))
                return
            else:
                # No title yet -> ask for it
                info["status"] = "awaiting_title"
                await safe_send(context.bot, chat_id, "Audio diterima. Silakan kirim judul video.")
                logger.info("Audio stored for chat %s, waiting for title", chat_id)
                return
        else:
            # No pending entry: create awaiting_password state (audio before password)
            pending_uploads[chat_id] = {
                "status": "awaiting_password",
                "orig_path": orig_path,
                "title": None,
                "attempts": 0,
                "timestamp": time.time(),
                "input_kind": input_kind,
                "doc_name": doc_name
            }
            logger.info("Stored pending upload (awaiting password) for chat %s (path=%s)", chat_id, orig_path)
            await safe_send(context.bot, chat_id, "Audio diterima. Silakan masukkan password untuk melanjutkan.")
            return

    except Exception as e:
        logger.exception("Error while handling incoming audio")
        try:
            await safe_send(context.bot, chat_id, f"Terjadi error saat menerima audio: {e}")
        except Exception:
            logger.exception("safe_send also failed.")
        try:
            if os.path.exists(orig_path):
                os.remove(orig_path)
        except Exception:
            pass

# ------------------- MAIN -------------------
def main():
    global PYRO_CLIENT
    # find Request class in possible locations (compat with different PTB releases)
    TGRequest = None
    for module_path in ("telegram.utils.request", "telegram.request"):
        try:
            mod = __import__(module_path, fromlist=["Request"])
            TGRequest = getattr(mod, "Request")
            logger.info("Found Request class at %s", module_path)
            break
        except Exception:
            continue

    if TGRequest is not None:
        try:
            req = TGRequest(con_pool_size=16, connect_timeout=10.0, read_timeout=1800.0, pool_timeout=60.0)
            app_builder = ApplicationBuilder().token(BOT_TOKEN).request(req)
            logger.info("Using Request with extended timeouts.")
        except Exception as e:
            logger.exception("Failed to init Request: %s", e)
            app_builder = ApplicationBuilder().token(BOT_TOKEN)
    else:
        logger.warning("Request class not found; using Application defaults.")
        app_builder = ApplicationBuilder().token(BOT_TOKEN)

    # Start Pyrogram client (bot-mode) if configured
    if PYRO_AVAILABLE:
        try:
            tg_api_id = int(os.environ.get("TG_API_ID", "0")) or None
            tg_api_hash = os.environ.get("TG_API_HASH", "") or None
            if tg_api_id and tg_api_hash:
                pyro = PyroClient("pyro_session", api_id=tg_api_id, api_hash=tg_api_hash, bot_token=BOT_TOKEN)
                pyro.start()
                PYRO_CLIENT = pyro
                logger.info("Started Pyrogram client for MTProto downloads.")
            else:
                logger.info("TG_API_ID/TG_API_HASH not set — Pyrogram fallback disabled.")
        except Exception as e:
            logger.exception("Failed to start Pyrogram: %s", e)
            PYRO_CLIENT = None
    else:
        logger.info("Pyrogram not installed — MTProto fallback unavailable.")

    app = app_builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    audio_filter = filters.VOICE | filters.AUDIO | filters.Document.ALL
    app.add_handler(MessageHandler(audio_filter, handle_audio_generic))
    app.add_error_handler(global_error_handler)

    logger.info("Bot siap. Resolved IMAGE_PATH=%s", IMAGE_PATH)
    try:
        app.run_polling()
    finally:
        try:
            if PYRO_CLIENT is not None:
                PYRO_CLIENT.stop()
        except Exception:
            pass

if __name__ == "__main__":
    main()
