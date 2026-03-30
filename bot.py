import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

user_roles = {}

def ask_gemini(prompt, role=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    if role:
        payload = {
            "system_instruction": {"parts": [{"text": role}]},
            "contents": [{"parts": [{"text": prompt}]}]
        }
    else:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    else:
        return f"Ошибка Gemini: {response.text}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот на Gemini. Просто пиши текст.\n"
        "/role <текст> — задать роль\n"
        "/role — показать текущую роль"
    )

async def role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        current = user_roles.get(chat_id, "не задана")
        await update.message.reply_text(f"Текущая роль: {current}")
        return
    role_text = " ".join(context.args)
    user_roles[chat_id] = role_text
    await update.message.reply_text(f"Роль установлена: {role_text}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    role = user_roles.get(chat_id)

    await update.message.chat.send_action(action="typing")
    reply = ask_gemini(user_text, role=role)
    await update.message.reply_text(reply)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("role", role_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", 8080))
    app.run_webhook(listen="0.0.0.0", port=port, url_path=TELEGRAM_TOKEN)

if __name__ == "__main__":
    main()
