import asyncio
import logging
import sqlite3
import random
import time
import json
from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Конфигурация
TOKEN = "7991920232:AAFgSw82BeYdJ0imvYoaNkashAtoMd9gyC0"
START_BALANCE = 2500
BONUS_AMOUNT = 2500
BONUS_COOLDOWN = 5 * 3600
ROBBERY_COOLDOWN = 5 * 60
CHAT_LINK = "https://t.me/AlIynQgYuB84OTY6"
CHANNEL_LINK = "https://t.me/adecvtek"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class GameStates(StatesGroup):
    cards = State()
    field = State()

# База данных
def init_db():
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 2500,
            last_bonus INTEGER DEFAULT 0,
            last_robbery INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_states (
            user_id INTEGER PRIMARY KEY,
            game_type TEXT,
            game_data TEXT,
            updated_at INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Вспомогательные функции
def get_user(user_id: int, username: str = None):
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        current_time = int(time.time())
        cursor.execute('INSERT INTO users (user_id, username, balance, last_bonus, last_robbery, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                      (user_id, username, START_BALANCE, 0, 0, current_time))
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
    conn.close()
    return user

def update_balance(user_id: int, amount: int):
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def get_balance(user_id: int) -> int:
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else START_BALANCE

def save_game_state(user_id: int, game_type: str, data: dict):
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO game_states (user_id, game_type, game_data, updated_at) VALUES (?, ?, ?, ?)',
                  (user_id, game_type, json.dumps(data), int(time.time())))
    conn.commit()
    conn.close()

def get_game_state(user_id: int):
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT game_type, game_data FROM game_states WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0], json.loads(result[1])
    return None, None

def clear_game_state(user_id: int):
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM game_states WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def generate_cards():
    buttons = ['💣', '✅', '✅']
    random.shuffle(buttons)
    return buttons

def get_multiplier(level: int) -> float:
    multipliers = {1: 1.33, 2: 1.66, 3: 2.0, 4: 3.0, 5: 5.0}
    return multipliers.get(level, 1.0)

def cards_keyboard(buttons):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=buttons[0], callback_data="cards_0")],
        [InlineKeyboardButton(text=buttons[1], callback_data="cards_1")],
        [InlineKeyboardButton(text=buttons[2], callback_data="cards_2")],
        [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="cards_collect")]
    ])
    return keyboard

def field_keyboard(opened, mines):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for row in range(5):
        row_buttons = []
        for col in range(5):
            if (row, col) in opened:
                if (row, col) in mines:
                    row_buttons.append(InlineKeyboardButton(text="💣", callback_data="field_no"))
                else:
                    row_buttons.append(InlineKeyboardButton(text="✅", callback_data="field_no"))
            else:
                row_buttons.append(InlineKeyboardButton(text="?", callback_data=f"field_{row}_{col}"))
        keyboard.inline_keyboard.append(row_buttons)
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data="field_collect")])
    return keyboard

# Команды без слеша (обработка текста)
@dp.message(lambda message: message.text and message.text.lower().startswith('карты'))
async def cards_command(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Укажите ставку!\n\nПример: карты 200")
        return
    
    try:
        bet = int(parts[1])
    except ValueError:
        await message.answer("❌ Ставка должна быть числом!\n\nПример: карты 200")
        return
    
    if bet <= 0:
        await message.answer("🚫 НУ БЛЯДЬ БОЛЬШЕ СТАВЬ 🚫")
        return
    
    balance = get_balance(message.from_user.id)
    
    if bet > balance:
        await message.answer(f"❌ Недостаточно средств!\n💰 Баланс: {balance} TONN\n🎲 Ставка: {bet} TONN")
        return
    
    update_balance(message.from_user.id, -bet)
    
    buttons = generate_cards()
    
    save_game_state(message.from_user.id, "cards", {
        'bet': bet,
        'level': 1,
        'buttons': buttons,
        'win': 0
    })
    
    text = f"🎴 Карты {bet}\n\nTONN\n@{message.from_user.username}, вы начали игру карты!\n\n"
    text += f"Уровень 1 | Множитель x1.33\n💰 Ставка: {bet} TONN"
    
    await message.answer(text, reply_markup=cards_keyboard(buttons))

@dp.message(lambda message: message.text and message.text.lower().startswith('поле'))
async def field_command(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Укажите ставку!\n\nПример: поле 100")
        return
    
    try:
        bet = int(parts[1])
    except ValueError:
        await message.answer("❌ Ставка должна быть числом!\n\nПример: поле 100")
        return
    
    if bet <= 0:
        await message.answer("🚫 НУ БЛЯДЬ БОЛЬШЕ СТАВЬ 🚫")
        return
    
    balance = get_balance(message.from_user.id)
    
    if bet > balance:
        await message.answer(f"❌ Недостаточно средств!\n💰 Баланс: {balance} TONN\n🎲 Ставка: {bet} TONN")
        return
    
    update_balance(message.from_user.id, -bet)
    
    # Генерируем поле 5x5 с 5 минами
    mines = []
    positions = list(range(25))
    random.shuffle(positions)
    for i in range(5):
        pos = positions[i]
        row = pos // 5
        col = pos % 5
        mines.append((row, col))
    
    save_game_state(message.from_user.id, "field", {
        'bet': bet,
        'mines': mines,
        'win': 0,
        'opened': []
    })
    
    text = f"🎲 ПОЛЕ {bet}\n\nTONN\n@{message.from_user.username}, вы начали игру поле!\n"
    text += f"💰 Ставка: {bet} TONN | За клетку +20 TONN\n\n"
    text += f"5 мин спрятаны на поле. Найди сокровища!"
    
    await message.answer(text, reply_markup=field_keyboard([], mines))

@dp.message(lambda message: message.text and message.text.lower().startswith('казино'))
async def casino_command(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Укажите ставку!\n\nПример: казино 200")
        return
    
    try:
        bet = int(parts[1])
    except ValueError:
        await message.answer("❌ Ставка должна быть числом!\n\nПример: казино 200")
        return
    
    if bet <= 0:
        await message.answer("🚫 НУ БЛЯДЬ БОЛЬШЕ СТАВЬ 🚫")
        return
    
    balance = get_balance(message.from_user.id)
    
    if bet > balance:
        await message.answer(f"❌ Недостаточно средств!\n💰 Баланс: {balance} TONN\n🎰 Ставка: {bet} TONN")
        return
    
    update_balance(message.from_user.id, -bet)
    
    msg = await message.answer(
        f"🎰 КРУЧУ КАЗИНО 🎰\n\n"
        f"💵 Ставка: {bet} TONN\n\n"
        f"Крутим... крутим... крутим..."
    )
    
    await asyncio.sleep(3)
    
    result = random.random()
    if result < 0.7:
        win = 0
        text = f"🎰 КРУЧУ КАЗИНО 🎰\n\n❌ ВЫ ПРОИГРАЛИ ❌\n\n💵 Ставка: {bet} TONN"
    elif result < 0.9:
        multiplier = random.choice([2, 3, 5])
        win = int(bet * multiplier)
        update_balance(message.from_user.id, win)
        text = f"🎰 КРУЧУ КАЗИНО 🎰\n\n🎉 ВЫ ВЫИГРАЛИ! 🎉\n\n💵 Выиграно: {win} TONN\n📌 Поставлено: {bet} TONN\n✨ Множитель: x{multiplier}"
    else:
        win = int(bet * 10)
        update_balance(message.from_user.id, win)
        text = f"🎰 КРУЧУ КАЗИНО 🎰\n\n🔥 ДЖЕКПОТ! 🔥\n🎉 ВЫ ВЫИГРАЛИ ДЖЕКПОТ! 🎉\n\n💵 Выиграно: {win} TONN\n📌 Поставлено: {bet} TONN\n✨ Множитель: x10"
    
    await msg.edit_text(text)

@dp.message(lambda message: message.text and message.text.lower() in ['ограбить', 'ограбить казну'])
async def robbery_command(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    current_time = int(time.time())
    last_robbery = user[4] or 0
    
    if current_time - last_robbery < ROBBERY_COOLDOWN:
        remaining = ROBBERY_COOLDOWN - (current_time - last_robbery)
        minutes = remaining // 60
        seconds = remaining % 60
        await message.answer(f"⏰ Подождите {minutes} мин {seconds} сек до следующего ограбления!")
        return
    
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET last_robbery = ? WHERE user_id = ?', (current_time, message.from_user.id))
    conn.commit()
    conn.close()
    
    fail_scenarios = [
        "вас заметили когда заходили в сейф",
        "вас заметили когда перерезали провода",
        "вас заметили когда отключали сигнализацию",
        "вас заметили когда выходили из казны",
        "сработала скрытая камера",
        "охранник услышал шум",
        "собака вас учуяла",
        "вы наступили на лазерную ловушку",
        "дверь захлопнулась и вы застряли"
    ]
    
    success = random.choice([True, False])
    
    if success:
        win = random.randint(100, 10000)
        update_balance(message.from_user.id, win)
        text = f"🏃‍♀️ ВЫ УКРАЛИ АЛМАЗ 🏃‍♀️\n\n👮‍♂️ Полиция вас не смогла догнать\n\n💵 Получено: {win} TONN"
    else:
        scenario = random.choice(fail_scenarios)
        text = f"👮‍♂️ ВАС ПОЙМАЛИ 👮‍♂️\n\nНе смог ограбить :( 0 TONN\n\nКак заметили: {scenario}"
    
    await message.answer(text)

@dp.message(lambda message: message.text and message.text.lower() in ['б', 'баланс'])
async def balance_command(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    current_time = int(time.time())
    last_bonus = user[3] or 0
    
    if current_time - last_bonus >= BONUS_COOLDOWN:
        bonus_text = f"\n\n🎁 Бонус доступен! Напиши бонус"
    else:
        remaining = BONUS_COOLDOWN - (current_time - last_bonus)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        bonus_text = f"\n\n⏰ Бонус через {hours}ч {minutes}мин"
    
    await message.answer(f"💰 Баланс: {user[2]} TONN{bonus_text}")

@dp.message(lambda message: message.text and message.text.lower() == 'бонус')
async def bonus_command(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    current_time = int(time.time())
    last_bonus = user[3] or 0
    
    if current_time - last_bonus < BONUS_COOLDOWN:
        remaining = BONUS_COOLDOWN - (current_time - last_bonus)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await message.answer(f"⏰ Бонус будет доступен через {hours}ч {minutes}мин")
        return
    
    update_balance(message.from_user.id, BONUS_AMOUNT)
    
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', (current_time, message.from_user.id))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Получено {BONUS_AMOUNT} TONN!\n💰 Баланс: {get_balance(message.from_user.id)} TONN")

@dp.message(lambda message: message.text and message.text.lower() == 'топ')
async def top_command(message: Message):
    conn = sqlite3.connect('tonn_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10')
    top_users = cursor.fetchall()
    conn.close()
    
    if not top_users:
        await message.answer("🏆 ТОП ИГРОКОВ TONN 🏆\n\nПока нет игроков. Стань первым!")
        return
    
    text = "🏆 ТОП ИГРОКОВ TONN 🏆\n\n"
    for i, user in enumerate(top_users, 1):
        username = user[1] or f"user{user[0]}"
        text += f"{i}. @{username} — {user[2]} TONN\n"
    
    await message.answer(text)

@dp.message(lambda message: message.text and message.text.lower().startswith('т'))
async def transfer_command(message: Message):
    if not message.reply_to_message:
        await message.answer("❌ Ответьте на сообщение пользователя!\n\nПример: т 500 (ответом на сообщение)")
        return
    
    try:
        amount = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ Укажите сумму!\n\nПример: т 500")
        return
    
    if amount <= 0:
        await message.answer("🚫 НУ БЛЯДЬ БОЛЬШЕ СТАВЬ 🚫")
        return
    
    sender_id = message.from_user.id
    receiver_id = message.reply_to_message.from_user.id
    receiver_name = message.reply_to_message.from_user.username or f"user{receiver_id}"
    
    if sender_id == receiver_id:
        await message.answer("🚫 ТЫ ДАЛБАЕБ? 🚫")
        return
    
    sender_balance = get_balance(sender_id)
    
    if sender_balance < amount:
        await message.answer(f"❌ Недостаточно средств!\n💰 Баланс: {sender_balance} TONN\n📤 Нужно: {amount} TONN")
        return
    
    update_balance(sender_id, -amount)
    update_balance(receiver_id, amount)
    
    await message.answer(
        f"✅ Перевод выполнен!\n\n"
        f"📤 Отправитель: @{message.from_user.username}\n"
        f"📥 Получатель: @{receiver_name}\n"
        f"💵 Сумма: {amount} TONN\n\n"
        f"💰 Ваш баланс: {get_balance(sender_id)} TONN"
    )

# Инлайн обработчики
@dp.callback_query(F.data.startswith("cards_"))
async def cards_callback(call: CallbackQuery):
    if call.data == "cards_collect":
        state_type, state_data = get_game_state(call.from_user.id)
        if state_type == "cards":
            win = state_data.get('win', 0)
            if win > 0:
                update_balance(call.from_user.id, win)
            clear_game_state(call.from_user.id)
            await call.message.edit_text(f"💰 Вы забрали выигрыш: {win} TONN")
            await call.answer()
        return
    
    idx = int(call.data.split("_")[1])
    state_type, state_data = get_game_state(call.from_user.id)
    
    if state_type != "cards":
        await call.answer("Игра не найдена!", show_alert=True)
        return
    
    buttons = state_data['buttons']
    bet = state_data['bet']
    level = state_data['level']
    
    if buttons[idx] == '💣':
        clear_game_state(call.from_user.id)
        await call.message.edit_text(
            f"💣 ВЫ ПРОИГРАЛИ! 💣\n\n"
            f"Ставка: {bet} TONN\n"
            f"Выигрыш: 0 TONN\n\n"
            f"@{call.from_user.username}, вы проиграли..."
        )
    else:
        multiplier = get_multiplier(level)
        win = int(bet * multiplier)
        
        if level == 5:
            update_balance(call.from_user.id, win)
            clear_game_state(call.from_user.id)
            await call.message.edit_text(
                f"🎉 ПОБЕДА! 🎉\n\n"
                f"Ставка: {bet} TONN\n"
                f"Выигрыш: {win} TONN\n"
                f"Множитель: x{multiplier}\n\n"
                f"@{call.from_user.username}, вы прошли все уровни!"
            )
        else:
            new_buttons = generate_cards()
            state_data['level'] = level + 1
            state_data['buttons'] = new_buttons
            state_data['win'] = win
            save_game_state(call.from_user.id, "cards", state_data)
            
            next_multiplier = get_multiplier(level + 1)
            text = f"✅ Уровень {level} пройден!\n\n"
            text += f"Текущий выигрыш: {win} TONN\n"
            text += f"Уровень {level + 1} | Множитель x{next_multiplier}"
            
            await call.message.edit_text(text, reply_markup=cards_keyboard(new_buttons))
    
    await call.answer()

@dp.callback_query(F.data.startswith("field_"))
async def field_callback(call: CallbackQuery):
    if call.data == "field_collect":
        state_type, state_data = get_game_state(call.from_user.id)
        if state_type == "field":
            win = state_data.get('win', 0)
            if win > 0:
                update_balance(call.from_user.id, win)
            clear_game_state(call.from_user.id)
            await call.message.edit_text(f"💰 Вы забрали выигрыш: {win} TONN")
            await call.answer()
        return
    
    if call.data == "field_no":
        await call.answer()
        return
    
    parts = call.data.split("_")
    row = int(parts[1])
    col = int(parts[2])
    
    state_type, state_data = get_game_state(call.from_user.id)
    if state_type != "field":
        await call.answer("Игра не найдена!", show_alert=True)
        return
    
    bet = state_data['bet']
    mines = state_data['mines']
    win = state_data['win']
    opened = state_data.get('opened', [])
    
    if (row, col) in opened:
        await call.answer("Эта клетка уже открыта!")
        return
    
    if (row, col) in mines:
        clear_game_state(call.from_user.id)
        await call.message.edit_text(
            f"💣 ВЫ ПРОИГРАЛИ! 💣\n\n"
            f"Ставка: {bet} TONN\n"
            f"Выигрыш: 0 TONN\n\n"
            f"@{call.from_user.username}, вы наступили на мину!"
        )
    else:
        opened.append((row, col))
        win += 20
        state_data['win'] = win
        state_data['opened'] = opened
        save_game_state(call.from_user.id, "field", state_data)
        
        text = f"✅ +20 TONN!\n\n"
        text += f"Текущий выигрыш: {win} TONN\n"
        text += f"Ставка: {bet} TONN\n"
        text += f"Открыто клеток: {len(opened)}/20"
        
        await call.message.edit_text(text, reply_markup=field_keyboard(opened, mines))
    
    await call.answer()

@dp.message(Command("start"))
async def start_command(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"🎲 Добро пожаловать в TONN Casino! 🎲\n\n"
        f"💰 Баланс: {user[2]} TONN\n\n"
        f"📌 Команды:\n"
        f"карты [ставка] - игра Карты\n"
        f"поле [ставка] - игра Поле\n"
        f"казино [ставка] - слот\n"
        f"ограбить - ограбление (5 мин)\n"
        f"б / баланс - баланс\n"
        f"бонус - бонус 2500 TONN\n"
        f"топ - топ игроков\n"
        f"т [сумма] - перевод (ответом)"
    )

# Запуск
async def main():
    logger.info("Бот TONN запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
