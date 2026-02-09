import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, BotCommand, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, 
    BufferedInputFile, FSInputFile
)

# --- НАШИ МОДУЛИ ---
import database as db          # База качалки
import database_vpn as vpn_db  # База прокси
import plots                   # Графики
import analysis                # Анализ веса
import keep_alive              # Веб-сервер + Подписка
import proxy_vacuum            # Пылесос

# -----------------------------------------------------------
# НАСТРОЙКИ
# -----------------------------------------------------------
TOKEN = "8349554668:AAHX4Fk76PFTVHrlxPTl7TTvcWds-kb6tEs"
USER_TIMEZONE = 3  # Москва

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# -----------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------------------------------------
def get_today_str():
    offset = timezone(timedelta(hours=USER_TIMEZONE))
    return datetime.now(offset).strftime("%Y-%m-%d")

def format_date_user(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%d.%m.%Y")

async def get_working_date(state: FSMContext):
    data = await state.get_data()
    return data.get("selected_date", get_today_str())

# -----------------------------------------------------------
# МАШИНА СОСТОЯНИЙ
# -----------------------------------------------------------
class Form(StatesGroup):
    waiting_for_food = State()
    waiting_for_weight = State()
    waiting_for_steps = State()
    waiting_for_gym = State()
    waiting_for_date = State()
    waiting_for_deficit_global = State()
    waiting_for_deficit_day = State()
    waiting_for_fix_burn = State()

# -----------------------------------------------------------
# КЛАВИАТУРЫ
# -----------------------------------------------------------
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="🍔 Внести еду"), KeyboardButton(text="⚖️ Внести вес")],
        [KeyboardButton(text="👣 Внести шаги"), KeyboardButton(text="🏋️‍♂️ Внести треню")],
        [KeyboardButton(text="✏️ Редактировать"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📈 Графики"), KeyboardButton(text="🧠 Анализ")],
        [KeyboardButton(text="⚙️ Дефицит"), KeyboardButton(text="📅 Другая дата")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_deficit_menu():
    kb = [
        [KeyboardButton(text="🌍 Изменить ОБЩИЙ дефицит")],
        [KeyboardButton(text="📅 Изменить для ЭТОГО ДНЯ")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_edit_menu():
    kb = [
        [KeyboardButton(text="❌ Удалить запись еды")],
        [KeyboardButton(text="🔥 Исправить Активность (Итог)")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_analysis_keyboard():
    kb = [
        [InlineKeyboardButton(text="📅 7 Дней", callback_data="anal_7")],
        [InlineKeyboardButton(text="🗓 30 Дней", callback_data="anal_30")],
        [InlineKeyboardButton(text="♾ За всё время", callback_data="anal_all")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# -----------------------------------------------------------
# ЛОГИКА БОТА
# -----------------------------------------------------------

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    db.init_db()
    vpn_db.init_proxy_db()
    await state.update_data(selected_date=get_today_str())
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Меню"),
        BotCommand(command="stats", description="📊 Отчет"),
        BotCommand(command="export", description="💾 Бэкап")
    ])
    await message.answer(
        "💪 <b>Монах V7.0 (Koyeb Edition)</b>.\n"
        "Я слежу за твоим жиром и качаю прокси в фоне.\n"
        "Твоя подписка: <code>/sub</code> после URL сервера.", 
        parse_mode="HTML", 
        reply_markup=get_main_keyboard()
    )

# --- 💾 ЭКСПОРТ/ИМПОРТ ---
@dp.message(Command("export"))
async def export_db(message: types.Message):
    await message.answer("📦 Пакую базы...")
    try:
        await message.reply_document(FSInputFile("iron_monk.db"), caption="💾 Качалка")
        await message.reply_document(FSInputFile("vpn_storage.db"), caption="🌐 ВПН")
    except: await message.answer("Ошибка экспорта.")

@dp.message(F.document)
async def import_db(message: types.Message):
    fname = message.document.file_name
    if fname in ["iron_monk.db", "vpn_storage.db"]:
        try:
            file = await bot.get_file(message.document.file_id)
            await bot.download_file(file.file_path, fname)
            await message.answer(f"✅ База {fname} восстановлена!")
        except Exception as e: await message.answer(f"Ошибка: {e}")

# --- 🧠 АНАЛИЗ ---
@dp.message(F.text == "🧠 Анализ")
async def analysis_menu(message: types.Message):
    await message.answer("Выбери период для анализа:", reply_markup=get_analysis_keyboard())

@dp.callback_query(F.data.startswith("anal_"))
async def process_analysis(callback: CallbackQuery):
    code = callback.data.split("_")[1]
    days = 7 if code == "7" else (30 if code == "30" else None)
    try:
        await callback.message.edit_text("⏳ Считаю математику...")
        report = analysis.analyze_period(callback.from_user.id, days)
        await callback.message.edit_text(report, parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")
    await callback.answer()

# --- 📈 ГРАФИКИ ---
@dp.message(F.text == "📈 Графики")
async def show_charts(message: types.Message):
    wait_msg = await message.answer("🎨 Рисую...")
    data = db.get_history(message.from_user.id, 30)
    if not data:
        await wait_msg.edit_text("Нет данных для графиков.")
        return
    photo_file = plots.create_progress_chart(data)
    if photo_file:
        await message.reply_photo(photo=BufferedInputFile(photo_file.read(), filename="chart.png"))
        await wait_msg.delete()
    else: await wait_msg.edit_text("Ошибка генерации.")

# --- 🍔 ЕДА ---
@dp.message(F.text == "🍔 Внести еду")
async def food_start(message: types.Message, state: FSMContext):
    date = await get_working_date(state)
    await message.answer(f"📅 [{format_date_user(date)}] Сколько ккал нажрал?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_food)

@dp.message(Form.waiting_for_food)
async def food_process(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        val = int(message.text)
        date = await get_working_date(state)
        db.add_food(message.from_user.id, val, date)
        await message.answer(f"➕ Добавил {val} ккал.", reply_markup=get_main_keyboard())
        await state.set_state(None)
    else: await message.answer("Пиши цифрами!")

# --- ⚖️ ВЕС ---
@dp.message(F.text == "⚖️ Внести вес")
async def weight_start(message: types.Message, state: FSMContext):
    date = await get_working_date(state)
    await message.answer(f"📅 [{format_date_user(date)}] Твой вес?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_weight)

@dp.message(Form.waiting_for_weight)
async def weight_process(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(',', '.'))
        date = await get_working_date(state)
        db.update_weight(message.from_user.id, val, date)
        await message.answer(f"✅ Вес {val} кг записан.", reply_markup=get_main_keyboard())
        await state.set_state(None)
    except: await message.answer("Нужно число (напр. 95.5)")

# --- 👣 ШАГИ ---
@dp.message(F.text == "👣 Внести шаги")
async def steps_start(message: types.Message, state: FSMContext):
    date = await get_working_date(state)
    stats = db.get_stats(message.from_user.id, date)
    cur = stats['steps'] if stats['steps'] else 0
    await message.answer(f"📅 [{format_date_user(date)}]\nСейчас в базе: {cur}\nВведи ИТОГ на часах:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_steps)

@dp.message(Form.waiting_for_steps)
async def steps_process(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        val = int(message.text)
        date = await get_working_date(state)
        added = db.update_steps(message.from_user.id, val, date)
        await message.answer(f"👣 Шаги обновлены до {val} ({added:+} ккал).", reply_markup=get_main_keyboard())
        await state.set_state(None)
    else: await message.answer("Пиши цифрами!")

# --- 🏋️‍♂️ ТРЕНЯ ---
@dp.message(F.text == "🏋️‍♂️ Внести треню")
async def gym_start(message: types.Message, state: FSMContext):
    await message.answer("Сколько сжег на тренировке?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_gym)

@dp.message(Form.waiting_for_gym)
async def gym_process(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        db.add_burn(message.from_user.id, int(message.text), await get_working_date(state))
        await message.answer("🔥 Треня записана!", reply_markup=get_main_keyboard())
        await state.set_state(None)

# --- ✏️ РЕДАКТИРОВАНИЕ ---
@dp.message(F.text == "✏️ Редактировать")
async def edit_start(message: types.Message):
    await message.answer("Что исправляем?", reply_markup=get_edit_menu())

@dp.message(F.text == "❌ Удалить запись еды")
async def delete_food_start(message: types.Message, state: FSMContext):
    date = await get_working_date(state)
    logs = db.get_food_logs(message.from_user.id, date)
    if not logs:
        await message.answer("Записей за этот день нет.", reply_markup=get_main_keyboard())
        return
    btns = [[InlineKeyboardButton(text=f"❌ {l[1]} ккал", callback_data=f"del_food_{l[0]}")] for l in logs]
    await message.answer(f"История за {format_date_user(date)}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("del_food_"))
async def process_food_delete(callback: CallbackQuery):
    log_id = int(callback.data.split("_")[2])
    success, val = db.delete_food_entry(log_id, callback.from_user.id)
    if success: await callback.message.edit_text(f"✅ Удалил запись на {val} ккал.")
    await callback.answer()

@dp.message(F.text == "🔥 Исправить Активность (Итог)")
async def fix_burn_start(message: types.Message, state: FSMContext):
    await message.answer("Введи правильную сумму активности за день (Шаги + Треня):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_fix_burn)

@dp.message(Form.waiting_for_fix_burn)
async def fix_burn_process(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        db.set_burn_absolute(message.from_user.id, int(message.text), await get_working_date(state))
        await message.answer("✅ Исправлено.", reply_markup=get_main_keyboard())
        await state.set_state(None)

# --- ⚙️ ДЕФИЦИТ ---
@dp.message(F.text == "⚙️ Дефицит")
async def deficit_menu_start(message: types.Message):
    await message.answer("Настройка обязательного дефицита:", reply_markup=get_deficit_menu())

@dp.message(F.text == "🌍 Изменить ОБЩИЙ дефицит")
async def deficit_global_start(message: types.Message, state: FSMContext):
    await message.answer("Введи новый дефицит по умолчанию (напр. 600):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_deficit_global)

@dp.message(Form.waiting_for_deficit_global)
async def deficit_global_process(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        db.set_global_deficit(message.from_user.id, int(message.text))
        await message.answer(f"✅ Стандартный дефицит: -{message.text} ккал.", reply_markup=get_main_keyboard())
        await state.set_state(None)

@dp.message(F.text == "📅 Изменить для ЭТОГО ДНЯ")
async def deficit_day_start(message: types.Message, state: FSMContext):
    date = await get_working_date(state)
    await message.answer(f"Дефицит конкретно на {format_date_user(date)}?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_deficit_day)

@dp.message(Form.waiting_for_deficit_day)
async def deficit_day_process(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        db.set_daily_deficit(message.from_user.id, int(message.text), await get_working_date(state))
        await message.answer(f"✅ Дефицит на день установлен.", reply_markup=get_main_keyboard())
        await state.set_state(None)

# --- 📊 СТАТИСТИКА ---
@dp.message(F.text == "📊 Статистика")
async def stats_view(message: types.Message, state: FSMContext):
    date = await get_working_date(state)
    stats = db.get_stats(message.from_user.id, date)
    eff_def = db.get_effective_deficit(message.from_user.id, date)
    bmr = 1950
    total_burn = bmr + stats['out']
    allowed = total_burn - eff_def
    rem = allowed - stats['in']
    label = f"{format_date_user(date)}"
    if date == get_today_str(): label += " (Сегодня)"
    text = (f"📅 <b>ОТЧЕТ {label}:</b>\n\n"
            f"🔥 Расход: {stats['out']} (+{bmr})\n"
            f"🛡 Дефицит: -{eff_def}\n"
            f"🍽 Лимит: <b>{allowed}</b>\n"
            f"🍔 Съел: {stats['in']}\n"
            f"👉 <b>Остаток: {rem} ккал</b>\n\n"
            f"⚖️ Вес: {stats['weight']} кг")
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- 📅 ДРУГАЯ ДАТА ---
@dp.message(F.text == "📅 Другая дата")
async def change_date_start(message: types.Message, state: FSMContext):
    await message.answer("Введи дату (ДД.ММ):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_date)

@dp.message(Form.waiting_for_date)
async def change_date_process(message: types.Message, state: FSMContext):
    try:
        t = message.text.strip()
        y = datetime.now().year
        d_sql = datetime.strptime(f"{t}.{y}" if len(t)==5 else t, "%d.%m.%Y").strftime("%Y-%m-%d")
        await state.update_data(selected_date=d_sql)
        await message.answer(f"✅ Режим работы с датой: {t}", reply_markup=get_main_keyboard())
        await state.set_state(None)
    except: await message.answer("Формат: 15.01")

@dp.message(F.text == "🔙 Назад")
async def back_handler(message: types.Message, state: FSMContext):
    await state.set_state(None)
    await message.answer("Главное меню", reply_markup=get_main_keyboard())

# -----------------------------------------------------------
# ЗАПУСК ВСЕГО
# -----------------------------------------------------------
async def main():
    print("🚀 Инициализация систем...")
    db.init_db()
    vpn_db.init_proxy_db()
    
    # 1. Запускаем Веб-сервер (ВАЖНО ДЛЯ HEALTH CHECK)
    await keep_alive.start_server()
    
    # 2. Запускаем фоновые задачи
    asyncio.create_task(proxy_vacuum.vacuum_job())
    
    # 3. Запускаем Бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): print("Офф.")
