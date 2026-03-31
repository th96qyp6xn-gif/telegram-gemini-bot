import os
import io
import json
import requests
import speech_recognition as sr
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# ========== КОНФИГУРАЦИЯ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Хранилище ролей (в памяти, можно заменить на файл/БД)
user_roles = {}  # chat_id -> role_text

# ========== ФУНКЦИЯ ЗАПРОСА К DEEPSEEK (с поддержкой файлов) ==========
def ask_deepseek(prompt, role=None, file_url=None):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if role:
        messages.append({"role": "system", "content": role})
    
    # Если есть файл (изображение или документ), отправляем ссылку на него
    if file_url:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": file_url}}
            ]
        })
    else:
        messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": False,
        "max_tokens": 4096
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return f"Ошибка DeepSeek: {response.text}"

# ========== РАСПОЗНАВАНИЕ ГОЛОСА ==========
def transcribe_audio(file_path):
    """Конвертирует голосовое сообщение в текст (русский язык)"""
    r = sr.Recognizer()
    with sr.AudioFile(file_path) as source:
        audio = r.record(source)
    try:
        text = r.recognize_google(audio, language="ru-RU")
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        return None

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Привет! Я бот на DeepSeek.\n\n"
        "📝 **Возможности:**\n"
        "• Текстовые сообщения\n"
        "• 🎤 Голосовые сообщения (русский язык)\n"
        "• 🖼 Изображения (анализ)\n"
        "• 📄 Документы (анализ текста)\n"
        "• 👥 Роли: `/role <описание>`\n\n"
        "Просто отправьте файл, фото или голосовое — я отвечу!"
    )

async def role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        current = user_roles.get(chat_id, "❌ не задана")
        await update.message.reply_text(f"Текущая роль:\n{current}")
        return
    role_text = " ".join(context.args)
    user_roles[chat_id] = role_text
    await update.message.reply_text(f"✅ Роль установлена:\n{role_text}")

# ========== ОБРАБОТКА ВСЕХ ТИПОВ СООБЩЕНИЙ ==========
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений"""
    chat_id = update.effective_chat.id
    role = user_roles.get(chat_id)
    
    # Скачиваем файл
    voice_file = await update.message.voice.get_file()
    file_path = f"voice_{chat_id}_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    
    await update.message.chat.send_action(action="typing")
    await update.message.reply_text("🎤 Распознаю голос...")
    
    # Распознаём
    transcribed = transcribe_audio(file_path)
    os.remove(file_path)
    
    if transcribed:
        await update.message.reply_text(f"📝 Вы сказали: {transcribed}")
        reply = ask_deepseek(transcribed, role=role)
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("❌ Не удалось распознать голос. Попробуйте чётче или текстом.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изображений (с анализом)"""
    chat_id = update.effective_chat.id
    role = user_roles.get(chat_id)
    
    # Получаем файл самого большого размера
    photo = update.message.photo[-1]
    file = await photo.get_file()
    
    # Получаем ссылку на файл (Telegram временная)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
    
    await update.message.chat.send_action(action="typing")
    await update.message.reply_text("🖼 Анализирую изображение...")
    
    # Запрашиваем у DeepSeek анализ
    prompt = "Опиши подробно, что изображено на этой картинке. Если есть текст, прочитай его."
    reply = ask_deepseek(prompt, role=role, file_url=file_url)
    await update.message.reply_text(reply)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка документов (PDF, TXT, DOCX и др.)"""
    chat_id = update.effective_chat.id
    role = user_roles.get(chat_id)
    
    doc = update.message.document
    file = await doc.get_file()
    
    # Скачиваем файл
    file_path = f"doc_{chat_id}_{update.message.message_id}_{doc.file_name}"
    await file.download_to_drive(file_path)
    
    await update.message.chat.send_action(action="typing")
    await update.message.reply_text(f"📄 Анализирую файл: {doc.file_name}...")
    
    # Читаем содержимое текстовых файлов
    if doc.file_name.endswith(('.txt', '.py', '.json', '.md', '.csv')):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()[:10000]  # Ограничиваем для токенов
            prompt = f"Проанализируй содержимое файла:\n\n{content}"
            reply = ask_deepseek(prompt, role=role)
        except Exception as e:
            reply = f"Ошибка чтения файла: {e}"
    else:
        # Для нетекстовых файлов (PDF, DOCX и т.д.) — просим DeepSeek проанализировать по имени и контексту
        prompt = f"Файл: {doc.file_name}. Что это за файл? Предположи его содержимое и дай рекомендации."
        reply = ask_deepseek(prompt, role=role)
    
    os.remove(file_path)
    await update.message.reply_text(reply)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обычные текстовые сообщения"""
    chat_id = update.effective_chat.id
    user_text = update.message.text
    role = user_roles.get(chat_id)
    
    await update.message.chat.send_action(action="typing")
    reply = ask_deepseek(user_text, role=role)
    await update.message.reply_text(reply)

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("role", role_command))
    
    # Обработчики сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Запуск вебхука
    port = int(os.environ.get("PORT", 8080))
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TELEGRAM_TOKEN,
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main()
