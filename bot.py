from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"



import json
import sqlite3
# ... и дальше весь остальной твой код
import json
import random
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# === РАБОТА С БАЗОЙ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect('quiz_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            score INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def update_user_score(user_id, username, first_name, add_score):
    conn = sqlite3.connect('quiz_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT score FROM stats WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    if row:
        new_score = row[0] + add_score
        cursor.execute('''
            UPDATE stats 
            SET score = ?, username = ?, first_name = ? 
            WHERE user_id = ?
        ''', (new_score, username, first_name, user_id))
    else:
        cursor.execute('''
            INSERT INTO stats (user_id, username, first_name, score) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, add_score))
        
    conn.commit()
    conn.close()

def get_top_users():
    conn = sqlite3.connect('quiz_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT first_name, username, score FROM stats ORDER BY score DESC LIMIT 10')
    rows = cursor.fetchall()
    conn.close()
    return rows

# === ЗАГРУЗКА ВОПРОСОВ ===
def load_questions():
    with open('books.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# === ГЛАВНОЕ МЕНЮ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎮 Начать викторину", callback_data="select_book")],
        [InlineKeyboardButton("🏆 Топ-10 игроков", callback_data="show_top")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "👋 **Главное меню**\n\nВыберите действие:"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# === ВЫБОР КНИГИ ===
async def select_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_questions()
    keyboard = []
    
    for book_id, book_info in data.items():
        keyboard.append([InlineKeyboardButton(book_info['title'], callback_data=f"start_{book_id}")])
        
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text("📖 Выберите тему/книгу для викторины:", reply_markup=reply_markup)

# === СТАРТ ТЕСТА ===
async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    book_id = query.data.replace("start_", "")
    data = load_questions()
    
    all_questions = data[book_id]['questions']
    quiz_questions = random.sample(all_questions, min(10, len(all_questions)))
    
    context.user_data['quiz'] = {
        'questions': quiz_questions,
        'current_index': 0,
        'score': 0
    }
    
    await send_question(query.message, context)

# === ОТПРАВКА ВОПРОСА С КНОПКАМИ A, B, C, D ===
async def send_question(message, context: ContextTypes.DEFAULT_TYPE):
    quiz_data = context.user_data['quiz']
    index = quiz_data['current_index']
    total = len(quiz_data['questions'])
    
    if index >= total:
        score = quiz_data['score']
        user = message.chat
        
        update_user_score(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "Игрок",
            add_score=score
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Пройти еще раз", callback_data="select_book")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.edit_text(
            f"🎉 **Тест завершён!**\n\nВаш результат: **{score} из {total}**.\nВсе очки зачтены в общий рейтинг!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    q = quiz_data['questions'][index]
    letters = ["A", "B", "C", "D"]
    
    # Текст вопроса + варианты ответов A, B, C, D
    question_text = f"❓ **Вопрос {index + 1}/{total}:**\n{q['question']}\n\n"
    for i, option in enumerate(q['options']):
        question_text += f"**{letters[i]}.** {option}\n"
    
    # Компактные кнопки [ A ] [ B ] [ C ] [ D ]
    keyboard = []
    row = []
    for i in range(len(q['options'])):
        row.append(InlineKeyboardButton(f" [ {letters[i]} ] ", callback_data=f"answer_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.edit_text(question_text, reply_markup=reply_markup, parse_mode="Markdown")

# === ОБРАБОТКА ОТВЕТА  ===
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected_option = int(query.data.replace("answer_", ""))
    
    quiz_data = context.user_data.get('quiz')
    if not quiz_data:
        await query.answer("Сессия истекла. Нажмите /start", show_alert=True)
        return

    current_question = quiz_data['questions'][quiz_data['current_index']]
    
    # Засчитываем балл без показа верного ответа
    if selected_option == current_question['correct_id']:
        quiz_data['score'] += 1
        
    await query.answer("Ответ принят! 👌")
        
    quiz_data['current_index'] += 1
    await send_question(query.message, context)

# === ТОП-10 ИГРОКОВ ===
async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    top_users = get_top_users()
    
    if not top_users:
        text = "🏆 **Рейтинг игроков пуст.** Начните викторину первым!"
    else:
        text = "🏆 **Топ-10 лучших игроков:**\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (first_name, username, score) in enumerate(top_users):
            prefix = medals[i] if i < 3 else f"{i+1}."
            name = f"@{username}" if username else first_name
            text += f"{prefix} {name} — **{score}** очков\n"
            
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

def main():
    init_db()  # Создание БД при старте
    
    TOKEN = "8935367454:AAH2j3AwJgtZcMDuCEEtLYWV8qbuZ_vCKKA"
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_book, pattern="^select_book$"))
    app.add_handler(CallbackQueryHandler(start_quiz, pattern="^start_"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    app.add_handler(CallbackQueryHandler(show_top, pattern="^show_top$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^main_menu$"))
    
    print("Бот запущен...")
   import threading
    threading.Thread(target=app.run_polling, daemon=True).start()


    main()
