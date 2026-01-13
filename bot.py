import logging
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

from bytez import Bytez
import db
from config import BOT_TOKEN, BYTEZ_KEY, ADMINS

# ---------- INIT ----------
logging.basicConfig(level=logging.INFO)

db.init()

sdk = Bytez(BYTEZ_KEY)
chat_model = sdk.model("openai/gpt-4.1")
video_model = sdk.model("openai/sora-2")

# ---------- HELPERS ----------

def is_admin(uid: int) -> bool:
    return uid in ADMINS

def generate_image(prompt: str):
    # CHANGE URL to your docker API endpoint
    url = "http://127.0.0.1:5000/generate"
    r = requests.post(url, json={"prompt": prompt}, timeout=180)
    if r.status_code != 200:
        return None
    data = r.json()
    return data.get("image_url") or data.get("path")

def short_answer(prompt: str) -> str:
    results = chat_model.run([
        {"role": "system", "content": "Reply very short. Only key points. No extra talk."},
        {"role": "user", "content": prompt},
    ])
    if results.error:
        return "AI error."
    return str(results.output)[:3500]

# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    db.add_user(user.id, user.username, user.full_name)

    if db.is_blocked(user.id):
        await update.message.reply_text("❌ You are blocked.")
        return

    msg = (
        f"👋 Hello {user.first_name}\n\n"
        "🤖 JARVIS AI\nMade by Hawsi-Bhai\n\n"
        "Commands:\n"
        "/chat <question>\n"
        "/img <prompt>\n"
        "/video <prompt>\n"
    )

    if is_admin(user.id):
        msg += (
            "\n🛠 Admin:\n"
            "/stats\n"
            "/block <id>\n"
            "/unblock <id>\n"
            "/setlimit <chat|img|video> <number>\n"
            "Reply to any msg: /broadcast\n"
        )

    await update.message.reply_text(msg)

# ---------- CHAT ----------

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if db.is_blocked(user_id):
        await update.message.reply_text("❌ You are blocked.")
        return

    if not context.args:
        await update.message.reply_text("Use: /chat your question")
        return

    if not db.can_use(user_id, "chat"):
        await update.message.reply_text("❌ Daily chat limit reached.")
        return

    prompt = " ".join(context.args)
    ans = short_answer(prompt)

    db.increase(user_id, "chat")
    await update.message.reply_text(ans)

# ---------- IMAGE ----------

async def img(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if db.is_blocked(user_id):
        await update.message.reply_text("❌ You are blocked.")
        return

    if not context.args:
        await update.message.reply_text("Use: /img description")
        return

    if not db.can_use(user_id, "img"):
        await update.message.reply_text("❌ Daily image limit reached.")
        return

    prompt = " ".join(context.args)
    await update.message.reply_text("🖼 Generating image...")

    try:
        result = generate_image(prompt)
    except:
        result = None

    if not result:
        await update.message.reply_text("Image generation failed.")
        return

    db.increase(user_id, "img")

    if str(result).startswith("http"):
        await update.message.reply_photo(result)
    else:
        await update.message.reply_photo(open(result, "rb"))

# ---------- VIDEO ----------

async def video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if db.is_blocked(user_id):
        await update.message.reply_text("❌ You are blocked.")
        return

    if not context.args:
        await update.message.reply_text("Use: /video description")
        return

    if not db.can_use(user_id, "video"):
        await update.message.reply_text("❌ Daily video limit reached.")
        return

    prompt = " ".join(context.args)
    await update.message.reply_text("🎬 Generating video... (slow)")

    results = video_model.run(prompt)

    if results.error:
        await update.message.reply_text("Video generation failed.")
        return

    db.increase(user_id, "video")

    await update.message.reply_text(f"Result:\n{results.output}")

# ---------- ADMIN ----------

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    s = db.stats()
    await update.message.reply_text(
        f"📊 Stats\nUsers: {s['total']}\nBlocked: {s['blocked']}"
    )

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid = int(context.args[0])
    db.block(uid, True)
    await update.message.reply_text("User blocked.")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid = int(context.args[0])
    db.block(uid, False)
    await update.message.reply_text("User unblocked.")

async def setlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cmd = context.args[0]
    val = int(context.args[1])
    db.set_limit(cmd, val)
    await update.message.reply_text("Limit updated.")

# ---------- BROADCAST ----------

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message with /broadcast")
        return

    con = db.connect()
    cur = con.cursor()
    cur.execute("SELECT chat_id FROM users WHERE blocked=0")
    users = [x[0] for x in cur.fetchall()]
    con.close()

    sent = 0
    failed = 0

    for uid in users:
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=update.message.chat_id,
                message_id=update.message.reply_to_message.message_id,
            )
            sent += 1
        except:
            failed += 1
            db.block(uid, True)

    await update.message.reply_text(f"Broadcast done.\nSent: {sent}\nFailed+Blocked: {failed}")

# ---------- MAIN ----------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chat", chat))
    app.add_handler(CommandHandler("img", img))
    app.add_handler(CommandHandler("video", video))

    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("setlimit", setlimit))
    app.add_handler(CommandHandler("broadcast", broadcast))

    print("Jarvis running...")
    app.run_polling()

if __name__ == "__main__":
    main()