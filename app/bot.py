import os
import asyncio
import csv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from sqlalchemy.orm import Session

from db import SessionLocal, engine, Base
from models import Registration

import random, string

# --- Генерация уникального ID с защитой от дубликатов ---
def generate_unique_id(session: Session) -> str:
    while True:
        candidate = "FG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        exists = session.query(Registration).filter_by(unique_id=candidate).first()
        if not exists:
            return candidate

# --- Инициализация ---
Base.metadata.create_all(bind=engine)
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- Клавиатура выбора игр ---
game_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎲 Купимания")],
        [KeyboardButton(text="🌍 Мир проектов")]
    ],
    resize_keyboard=True
)

# --- Старт ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет 👋 Добро пожаловать на ФинИгры!\nВыберите игру:",
        reply_markup=game_keyboard
    )

# --- Регистрация ---
@dp.message(F.text.in_(["🎲 Купимания", "🌍 Мир проектов"]))
async def register_game(message: types.Message):
    session: Session = SessionLocal()
    try:
        game = message.text.strip()

        # Проверяем, есть ли уже регистрация этого игрока в этой игре
        existing = (
            session.query(Registration)
            .filter_by(telegram_id=message.from_user.id, game=game)
            .first()
        )

        if existing:
            await message.answer(
                f"⚠️ Вы уже зарегистрированы в этой игре!\n"
                f"Игра: {game}\n"
                f"Ваш ID: {existing.unique_id}\n"
                f"Статус: {'✅ Активен' if not existing.used else '❌ Использован'}"
            )
            return

        # Генерация нового уникального ID
        unique_id = generate_unique_id(session)

        reg = Registration(
            telegram_id=message.from_user.id,
            game=game,
            unique_id=unique_id
        )
        session.add(reg)
        session.commit()

        await message.answer(
            f"✅ Регистрация завершена!\n"
            f"Игра: {game}\n"
            f"Ваш уникальный ID: {unique_id}\n\n"
            f"Покажите этот код организатору."
        )

        await bot.send_message(
            ADMIN_ID,
            f"✅ Новый ID\nИгра: {game}\nID: {unique_id}"
        )

    finally:
        session.close()

# --- Отметить ID как использованный ---
@dp.message(Command("use"))
async def admin_use(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("⚠️ Использование: /use FG-XXXXXX")
        return

    id_to_use = args[1].strip()
    session: Session = SessionLocal()
    try:
        reg = session.query(Registration).filter_by(unique_id=id_to_use).first()
        if not reg:
            await message.answer(f"❌ ID {id_to_use} не найден.")
            return

        if reg.used:
            await message.answer(f"⚠️ ID {id_to_use} уже был использован ранее!")
            return

        reg.used = True
        session.commit()

        await message.answer(f"✅ ID {id_to_use} отмечен как использованный (игра: {reg.game}).")

    finally:
        session.close()

# --- Список всех регистраций ---
@dp.message(Command("list"))
async def admin_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    session: Session = SessionLocal()
    try:
        regs = session.query(Registration).order_by(Registration.created_at).all()
        if not regs:
            await message.answer("📭 Пока нет регистраций.")
            return

        text = "📋 Список регистраций:\n\n"
        for r in regs:
            status = "✅ Активен" if not r.used else "❌ Использован"
            text += f"{r.unique_id} → {r.game} → {status}\n"

        await message.answer(text)
    finally:
        session.close()

# --- Экспорт в CSV ---
@dp.message(Command("export"))
async def admin_export(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    session: Session = SessionLocal()
    try:
        regs = session.query(Registration).all()
        if not regs:
            await message.answer("📭 Пока нет регистраций.")
            return

        filename = "registrations.csv"
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["unique_id", "game", "telegram_id", "created_at", "status"])
            for r in regs:
                status = "active" if not r.used else "used"
                writer.writerow([r.unique_id, r.game, r.telegram_id, r.created_at, status])

        await bot.send_document(
            ADMIN_ID,
            FSInputFile(filename, filename)
        )
        os.remove(filename)
    finally:
        session.close()

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
