import os
import sys
import logging
import hashlib
import time
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("StudyApkModPWBot")

# In-memory store to keep callback_data small (<64 bytes)
DATA_STORE = {}

def store_data(data_type: str, **kwargs) -> str:
    """Stores param dict in memory and returns a short hash key."""
    key = hashlib.md5(f"{data_type}:{kwargs}:{time.time()}".encode()).hexdigest()[:12]
    DATA_STORE[key] = {"type": data_type, **kwargs}
    return f"{data_type}:{key}"

def get_data(key_str: str) -> dict:
    parts = key_str.split(":", 1)
    if len(parts) == 2 and parts[1] in DATA_STORE:
        return DATA_STORE[parts[1]]
    return {}

# Default PenPencil Headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "client_type": "WEB",
    "randomid": "a1b2c3d4e5f6g7h8",
    "origin": "https://pw.live",
    "referer": "https://pw.live/",
}

async def fetch_json(url: str):
    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        res = await client.get(url)
        if res.status_code == 200:
            return res.json()
        raise Exception(f"HTTP {res.status_code}")

def extract_list(raw_data):
    if not raw_data:
        return []
    if isinstance(raw_data, list):
        return raw_data
    if isinstance(raw_data, dict):
        if isinstance(raw_data.get("data"), list) and len(raw_data["data"]) > 0:
            return raw_data["data"]
        if isinstance(raw_data.get("subjects"), list) and len(raw_data["subjects"]) > 0:
            return raw_data["subjects"]
        if isinstance(raw_data.get("batchSubject"), list) and len(raw_data["batchSubject"]) > 0:
            return raw_data["batchSubject"]
        
        inner = raw_data.get("data")
        if isinstance(inner, dict):
            if isinstance(inner.get("subjects"), list) and len(inner["subjects"]) > 0:
                return inner["subjects"]
            if isinstance(inner.get("batchSubject"), list) and len(inner["batchSubject"]) > 0:
                return inner["batchSubject"]
            if isinstance(inner.get("contents"), list) and len(inner["contents"]) > 0:
                return inner["contents"]
            if isinstance(inner.get("lectures"), list) and len(inner["lectures"]) > 0:
                return inner["lectures"]
            if isinstance(inner.get("topics"), list) and len(inner["topics"]) > 0:
                return inner["topics"]
            
            for k, v in inner.items():
                if isinstance(v, list) and len(v) > 0:
                    return v

        for k, v in raw_data.items():
            if isinstance(v, list) and len(v) > 0:
                return v

    return []

async def fetch_subjects(batch_id: str):
    urls = [
        f"https://api.penpencil.co/v3/batches/{batch_id}/details",
        f"https://devcoderz-player.vercel.app/api/subjects?batchId={batch_id}",
        f"https://proxy.streamvideo.co.in/fetch/api.penpencil.co/v3/batches/{batch_id}/details",
        f"https://api.penpencil.co/v2/batches/{batch_id}/subject",
    ]
    for url in urls:
        try:
            data = await fetch_json(url)
            sub_list = extract_list(data)
            if sub_list:
                return sub_list
        except Exception:
            continue
    return []

async def fetch_topics(batch_id: str, subject_id: str, page: int = 1):
    urls = [
        f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/topics?page={page}",
        f"https://proxy.streamvideo.co.in/fetch/api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/topics?page={page}",
    ]
    for url in urls:
        try:
            data = await fetch_json(url)
            topic_list = extract_list(data)
            if topic_list:
                return topic_list
        except Exception:
            continue
    return []

async def fetch_contents(batch_id: str, subject_id: str, tag_id: str, content_type: str, page: int = 1):
    mapped_type = (
        "dpp" if content_type in ["DppNotes", "dpp"]
        else "notes" if content_type == "notes"
        else "videos" if content_type in ["videos", "lectures"]
        else "DppVideos"
    )
    urls = [
        f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/contents?tag={tag_id}&contentType={content_type}&page={page}",
        f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/contents?tag={tag_id}&contentType={mapped_type}&page={page}",
        f"https://devcoderz-player.vercel.app/api/lectures?batchId={batch_id}&subjectId={subject_id}&contentType={mapped_type}&tag={tag_id}&page={page}",
        f"https://proxy.streamvideo.co.in/fetch/api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/contents?tag={tag_id}&contentType={content_type}&page={page}",
    ]
    for url in urls:
        try:
            data = await fetch_json(url)
            items = extract_list(data)
            if items:
                return items
        except Exception:
            continue
    return []

# Command: /start or /batchid or /start <batchId>
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split()
    
    batch_id = ""
    if len(parts) > 1:
        batch_id = parts[1].strip()
    elif text.startswith("/batchid"):
        batch_id = text.replace("/batchid", "").strip()
    elif text.startswith("/"):
        possible_id = text[1:].strip()
        if len(possible_id) >= 12 and not possible_id.isdigit():
            batch_id = possible_id

    if not batch_id:
        await update.message.reply_text(
            "👋 *Welcome to Study Apk Mod PW Bot!*\n\n"
            "To view subjects and lectures for a batch, send the command:\n"
            "`/batchid <batchId>` or `/start <batchId>`\n\n"
            "💡 You can also pick courses from our Web Catalog!",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text(f"⏳ *Fetching Subjects for Batch:* `{batch_id}`...", parse_mode="Markdown")

    subjects = await fetch_subjects(batch_id)
    if not subjects:
        await msg.edit_text(f"❌ Could not load subjects for batch `{batch_id}`. Please check batch ID.", parse_mode="Markdown")
        return

    keyboard = []
    for sub in subjects:
        sub_id = sub.get("_id") or sub.get("id") or sub.get("subjectId") or ""
        sub_name = sub.get("subjectName") or sub.get("name") or sub.get("title") or "Subject"
        if sub_id:
            cb_key = store_data("subj", batch_id=batch_id, subject_id=sub_id, subject_name=sub_name)
            keyboard.append([InlineKeyboardButton(f"📘 {sub_name}", callback_data=cb_key)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg.edit_text(
        f"🎯 *Batch ID:* `{batch_id}`\n\n"
        "👇 Select a **Subject** below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Callback: Subject Selected -> Fetch Topics
async def handle_subject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = get_data(query.data)
    batch_id = data.get("batch_id")
    subject_id = data.get("subject_id")
    subject_name = data.get("subject_name", "Subject")

    if not batch_id or not subject_id:
        await query.edit_message_text("❌ Session expired. Please send `/start <batchId>` again.")
        return

    await query.edit_message_text(f"⏳ *Loading Topics for:* {subject_name}...", parse_mode="Markdown")

    topics = await fetch_topics(batch_id, subject_id)
    if not topics:
        await query.edit_message_text(f"❌ No topics found for subject *{subject_name}*.", parse_mode="Markdown")
        return

    keyboard = []
    for top in topics:
        top_id = top.get("_id") or top.get("id") or top.get("tagId") or ""
        top_name = top.get("name") or top.get("title") or top.get("topic") or "Topic"
        if top_id:
            cb_key = store_data("top", batch_id=batch_id, subject_id=subject_id, topic_id=top_id, topic_name=top_name)
            keyboard.append([InlineKeyboardButton(f"📁 {top_name}", callback_data=cb_key)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📘 *Subject:* {subject_name}\n"
        "👇 Select a **Topic / Chapter** below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Callback: Topic Selected -> Show Content Tabs (Lectures, Notes, DPP, Solution)
async def handle_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = get_data(query.data)
    batch_id = data.get("batch_id")
    subject_id = data.get("subject_id")
    topic_id = data.get("topic_id")
    topic_name = data.get("topic_name", "Topic")

    if not batch_id or not subject_id or not topic_id:
        await query.edit_message_text("❌ Session expired. Please send `/start <batchId>` again.")
        return

    cb_lec = store_data("tab", batch_id=batch_id, subject_id=subject_id, topic_id=topic_id, topic_name=topic_name, content_type="videos")
    cb_not = store_data("tab", batch_id=batch_id, subject_id=subject_id, topic_id=topic_id, topic_name=topic_name, content_type="notes")
    cb_dpp = store_data("tab", batch_id=batch_id, subject_id=subject_id, topic_id=topic_id, topic_name=topic_name, content_type="DppNotes")
    cb_sol = store_data("tab", batch_id=batch_id, subject_id=subject_id, topic_id=topic_id, topic_name=topic_name, content_type="DppVideos")

    keyboard = [
        [InlineKeyboardButton("🎥 Lectures", callback_data=cb_lec), InlineKeyboardButton("📝 Notes", callback_data=cb_not)],
        [InlineKeyboardButton("📄 DPP Notes", callback_data=cb_dpp), InlineKeyboardButton("🎬 DPP Solutions", callback_data=cb_sol)],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📁 *Topic:* {topic_name}\n\n"
        "👇 Select a **Content Type**:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Callback: Content Tab Selected -> Fetch Contents (Lectures / Notes / DPP)
async def handle_tab_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = get_data(query.data)
    batch_id = data.get("batch_id")
    subject_id = data.get("subject_id")
    topic_id = data.get("topic_id")
    topic_name = data.get("topic_name", "Topic")
    content_type = data.get("content_type", "videos")

    if not batch_id or not subject_id or not topic_id:
        await query.edit_message_text("❌ Session expired. Please send `/start <batchId>` again.")
        return

    type_label = (
        "Lectures 🎥" if content_type == "videos"
        else "Notes 📝" if content_type == "notes"
        else "DPP Notes 📄" if content_type == "DppNotes"
        else "DPP Solutions 🎬"
    )

    await query.edit_message_text(f"⏳ *Loading {type_label} for:* {topic_name}...", parse_mode="Markdown")

    items = await fetch_contents(batch_id, subject_id, topic_id, content_type)
    if not items:
        await query.edit_message_text(f"❌ No {type_label} found in *{topic_name}*.", parse_mode="Markdown")
        return

    keyboard = []
    if content_type in ["videos", "DppVideos"]:
        for item in items[:25]:
            title = item.get("topic") or item.get("title") or item.get("name") or "Lecture Video"
            
            raw_vid = item.get("_id") or item.get("id") or ""
            if not raw_vid and "video" in item and isinstance(item["video"], dict):
                raw_vid = item["video"].get("_id") or item["video"].get("id") or ""

            cb_key = store_data("lec", batch_id=batch_id, video_id=raw_vid, title=title)
            keyboard.append([InlineKeyboardButton(f"▶️ {title}", callback_data=cb_key)])
    else:
        # Notes / DPP PDFs
        for item in items[:25]:
            title = item.get("topic") or item.get("title") or item.get("name") or "PDF Document"
            pdf_url = ""
            if item.get("attachment") and isinstance(item["attachment"], dict):
                pdf_url = item["attachment"].get("baseUrl", "") + item["attachment"].get("key", "")
            elif item.get("pdfUrl"):
                pdf_url = item["pdfUrl"]
            elif item.get("url"):
                pdf_url = item["url"]

            if pdf_url:
                keyboard.append([InlineKeyboardButton(f"📄 {title}", url=pdf_url)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📂 *Topic:* {topic_name}\n"
        f"🏷️ *Type:* {type_label}\n\n"
        "👇 Select an item below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Callback: Lecture Clicked -> Show Download Button ONLY
async def handle_lecture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = get_data(query.data)
    batch_id = data.get("batch_id")
    video_id = data.get("video_id")
    title = data.get("title", "Lecture Video")

    if not batch_id or not video_id:
        await query.edit_message_text("❌ Video details missing.")
        return

    # Link format: https://t.me/AS_MultiverseRoBot?start={batchId}_{videoId}
    download_url = f"https://t.me/AS_MultiverseRoBot?start={batch_id}_{video_id}"

    keyboard = [
        [InlineKeyboardButton("📥 Download / Watch Lecture", url=download_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🎬 *Lecture:* {title}\n"
        f"📌 *Batch ID:* `{batch_id}`\n\n"
        "👇 Click the download button below to get video link:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def main():
    if not BOT_TOKEN:
        logger.error("❌ ERROR: BOT_TOKEN environment variable is missing! Please set BOT_TOKEN in Railway variables.")
        sys.exit(1)

    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler(["start", "batchid"], start_command))
    application.add_handler(MessageHandler(filters.Regex(r"^/[a-zA-Z0-9_-]+"), start_command))

    # Callback Query handlers
    application.add_handler(CallbackQueryHandler(handle_subject_callback, pattern=r"^subj:"))
    application.add_handler(CallbackQueryHandler(handle_topic_callback, pattern=r"^top:"))
    application.add_handler(CallbackQueryHandler(handle_tab_callback, pattern=r"^tab:"))
    application.add_handler(CallbackQueryHandler(handle_lecture_callback, pattern=r"^lec:"))

    logger.info("Bot started successfully. Listening for incoming commands...")
    application.run_polling()

if __name__ == "__main__":
    main()
