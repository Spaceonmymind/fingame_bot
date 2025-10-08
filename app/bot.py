import os
import asyncio
import csv
import random, string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.orm import Session

from db import SessionLocal, engine, Base
from models import Registration
from utils import slots

# --- Генерация уникального ID ---
def generate_unique_id(session: Session) -> str:
    while True:
        candidate = "FG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        exists = session.query(Registration).filter_by(unique_id=candidate).first()
        if not exists:
            return candidate

# --- Инициализация ---
Base.metadata.create_all(bind=engine)
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

# --- Список администраторов ---
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_ID", "").replace(" ", "").split(",") if x]


# --- FSM ---
class RegisterGame(StatesGroup):
    choosing_game = State()
    choosing_slot = State()


# --- Старт ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    game_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Купимания", callback_data="game_kupimania")],
        [InlineKeyboardButton(text="🌍 Мир проектов", callback_data="game_mir")]
    ])

    await state.set_state(RegisterGame.choosing_game)
    await message.answer("Привет 👋 Добро пожаловать на ФинИгры!\nВыберите игру:", reply_markup=game_keyboard)


# --- Выбор игры ---
@dp.callback_query(F.data.startswith("game_"))
async def choose_game(callback: types.CallbackQuery, state: FSMContext):
    game = "Купимания" if callback.data == "game_kupimania" else "Мир проектов"

    session: Session = SessionLocal()
    existing = session.query(Registration).filter_by(
        telegram_id=callback.from_user.id, game=game
    ).first()

    if existing:
        await callback.message.answer(
            f"⚠️ Вы уже зарегистрированы!\n"
            f"Игра: {game}\n"
            f"Дата: {existing.slot_date}\n"
            f"Время: {existing.slot_time}\n"
            f"Ваш ID: {existing.unique_id}"
        )
        session.close()
        await callback.answer()
        return

    await state.update_data(game=game)

    available_slots = []
    for date, times in slots.items():
        for time in times:
            count = session.query(Registration).filter_by(game=game, slot_date=date, slot_time=time).count()
            if count < 4:
                available_slots.append((date, time))
    session.close()

    if not available_slots:
        await callback.message.answer("❌ Для этой игры нет свободных слотов.")
        await state.clear()
        await callback.answer()
        return

    slot_buttons = [[InlineKeyboardButton(text=f"{d} {t}", callback_data=f"slot_{d}_{t}")]
                    for d, t in available_slots]
    slot_keyboard = InlineKeyboardMarkup(inline_keyboard=slot_buttons)

    await state.set_state(RegisterGame.choosing_slot)
    await callback.message.answer(f"Вы выбрали игру: {game}\nТеперь выберите слот:", reply_markup=slot_keyboard)
    await callback.answer()


# --- Выбор слота ---
@dp.callback_query(F.data.startswith("slot_"))
async def register_slot(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    slot_date, slot_time = parts[1], parts[2]
    data = await state.get_data()
    game = data.get("game")

    session: Session = SessionLocal()
    try:
        count = session.query(Registration).filter_by(game=game, slot_date=slot_date, slot_time=slot_time).count()
        if count >= 4:
            await callback.message.answer("❌ Этот слот уже заполнен. Попробуйте другой.")
            await callback.answer()
            return

        unique_id = generate_unique_id(session)
        reg = Registration(
            telegram_id=callback.from_user.id,
            game=game,
            slot_date=slot_date,
            slot_time=slot_time,
            unique_id=unique_id
        )
        session.add(reg)
        session.commit()

        await callback.message.answer(
            f"✅ Регистрация завершена!\n"
            f"Игра: {game}\n"
            f"Дата: {slot_date}\n"
            f"Время: {slot_time}\n"
            f"Ваш ID: {unique_id}\n\n"
            f"Покажите этот код организатору."
        )

        # Рассылка всем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"✅ Новый ID\nИгра: {game}\nДата: {slot_date}\nВремя: {slot_time}\nID: {unique_id}"
                )
            except Exception as e:
                print(f"Ошибка отправки админу {admin_id}: {e}")

    finally:
        session.close()
        await state.clear()
        await callback.answer()


# --- Админ-команды ---
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@dp.message(Command("list"))
async def admin_list(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    session: Session = SessionLocal()
    try:
        regs = session.query(Registration).order_by(Registration.slot_date, Registration.slot_time).all()
        if not regs:
            await message.answer("📭 Пока нет регистраций.")
            return

        text = "📋 Список регистраций:\n\n"
        for r in regs:
            status = "✅ Активен" if not r.used else "❌ Использован"
            text += f"{r.unique_id} → {r.game} → {r.slot_date} {r.slot_time} → {status}\n"

        await message.answer(text if len(text) < 4000 else text[:4000])
    finally:
        session.close()


@dp.message(Command("export"))
async def admin_export(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    session: Session = SessionLocal()
    try:
        regs = session.query(Registration).order_by(Registration.slot_date, Registration.slot_time).all()
        if not regs:
            await message.answer("📭 Пока нет регистраций.")
            return

        filename = "registrations.csv"
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["unique_id", "game", "slot_date", "slot_time", "telegram_id", "created_at", "status"])
            for r in regs:
                status = "active" if not r.used else "used"
                writer.writerow([r.unique_id, r.game, r.slot_date, r.slot_time, r.telegram_id, r.created_at, status])

        # отправляем CSV всем админам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_document(admin_id, FSInputFile(filename, filename))
            except Exception as e:
                print(f"Ошибка при отправке файла админу {admin_id}: {e}")

        os.remove(filename)
    finally:
        session.close()


@dp.message(Command("use"))
async def admin_use(message: types.Message):
    if not is_admin(message.from_user.id):
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
        await message.answer(f"✅ ID {id_to_use} отмечен как использованный ({reg.game}, {reg.slot_date} {reg.slot_time}).")
    finally:
        session.close()


@dp.message(Command("active"))
async def admin_active(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    session: Session = SessionLocal()
    try:
        regs = session.query(Registration).filter_by(used=False).order_by(Registration.slot_date, Registration.slot_time).all()
        if not regs:
            await message.answer("📭 Нет активных ID.")
            return

        text = "📋 Активные ID:\n\n"
        for r in regs:
            text += f"{r.unique_id} → {r.game} → {r.slot_date} {r.slot_time}\n"

        await message.answer(text if len(text) < 4000 else text[:4000])
    finally:
        session.close()


# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
