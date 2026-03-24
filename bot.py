import asyncio
import json
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    Contact,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# =========================
# НАСТРОЙКИ
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DATA_FILE = "applications.json"
LOG_FILE = "bot.log"

# =========================
# ЛОГИРОВАНИЕ
# =========================
logging.basicConfig(
    level=logging.INFO,
    filename=LOG_FILE,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)

if not BOT_TOKEN:
    raise ValueError("Не задан BOT_TOKEN. Укажи его в переменных окружения.")

if ADMIN_ID <= 0:
    raise ValueError("Не задан ADMIN_ID. Укажи корректный Telegram ID в переменных окружения.")

# =========================
# ИНИЦИАЛИЗАЦИЯ
# =========================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================
# СОСТОЯНИЯ FSM
# =========================
class BookingStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_dates = State()
    waiting_for_contact = State()


# =========================
# КЛАВИАТУРЫ
# =========================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Записаться на сеанс")],
        [KeyboardButton(text="FAQ"), KeyboardButton(text="Связаться с мастером")],
    ],
    resize_keyboard=True
)

faq_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Сколько стоит татуировка?")],
        [KeyboardButton(text="Как подготовиться к сеансу?")],
        [KeyboardButton(text="Можно ли со своим эскизом?")],
        [KeyboardButton(text="Сколько длится сеанс?")],
        [KeyboardButton(text="Назад в меню")],
    ],
    resize_keyboard=True
)

contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Поделиться контактом", request_contact=True)],
        [KeyboardButton(text="Ввести данные вручную")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================
def load_applications():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_application(application: dict):
    applications = load_applications()
    applications.append(application)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(applications, f, ensure_ascii=False, indent=4)


def is_valid_contact(contact: str) -> bool:
    # Очень простая валидация:
    # либо телефон с + и цифрами, либо @username, либо email
    contact = contact.strip()

    if contact.startswith("@") and len(contact) >= 5:
        return True

    if "@" in contact and "." in contact and " " not in contact:
        return True

    digits = contact.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if digits.isdigit() and 10 <= len(digits) <= 15:
        return True

    return False


async def finalize_application(message: Message, state: FSMContext, contact_value: str):
    await state.update_data(contact=contact_value)
    data = await state.get_data()

    application = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "name": data.get("name"),
        "description": data.get("description"),
        "reference_file_id": data.get("reference_file_id"),
        "reference_file_ids": data.get("reference_file_ids", []),
        "preferred_dates": data.get("preferred_dates"),
        "contact": contact_value,
    }

    save_application(application)
    logging.info(f"Заявка сохранена от пользователя {message.from_user.id}")

    admin_text = (
        "Новая заявка на тату-сеанс:\n\n"
        f"Имя: {application['name']}\n"
        f"Telegram: @{application['username'] if application['username'] else 'нет username'}\n"
        f"User ID: {application['user_id']}\n"
        f"Описание: {application['description']}\n"
        f"Удобные даты: {application['preferred_dates']}\n"
        f"Контакт: {application['contact']}\n"
        f"Дата заявки: {application['created_at']}"
    )

    try:
        await bot.send_message(ADMIN_ID, admin_text)
        reference_ids = application.get("reference_file_ids") or []

        if reference_ids:
            for index, file_id in enumerate(reference_ids, start=1):
                caption = f"Референс {index} от {application['name']}" if index == 1 else None
                await bot.send_photo(
                    ADMIN_ID,
                    file_id,
                    caption=caption
                )
        elif application["reference_file_id"]:
            await bot.send_photo(
                ADMIN_ID,
                application["reference_file_id"],
                caption=f"Референс от {application['name']}"
            )
    except Exception as e:
        logging.error(f"Ошибка отправки админу: {e}")

    await message.answer(
        "Спасибо ! Заявка отправлена. Я передал информацию, с тобой свяжутся для уточнения деталей !",
        reply_markup=main_keyboard
    )

    await state.clear()


# =========================
# ОБРАБОТЧИКИ
# =========================
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    logging.info(f"Пользователь {message.from_user.id} запустил бота")
    await message.answer(
        "Привет ! Я бот для записи на тату-сеанс.\n"
        "Здесь можно узнать ответы на частые вопросы и оставить заявку.",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "FAQ")
async def faq_menu(message: Message):
    await message.answer(
        "Выберите интересующий вопрос:",
        reply_markup=faq_keyboard
    )


@dp.message(F.text == "Сколько стоит татуировка?")
async def faq_price(message: Message):
    await message.answer(
        "Стоимость зависит от размера, сложности эскиза и места нанесения. "
        "Для точной оценки лучше отправить описание идеи или референс. " \
        "Маленькую татуировку, размером около 10-ти сантиметров я набью за 4 тысячи рублей. ^^"
    )


@dp.message(F.text == "Как подготовиться к сеансу?")
async def faq_prepare(message: Message):
    await message.answer(
        "Перед сеансом желательно выспаться, поесть, не употреблять алкоголь за сутки (энергетики тоже тучше не пить)"
        "и не приходить с повреждённой кожей в зоне татуировки."
    )


@dp.message(F.text == "Можно ли со своим эскизом?")
async def faq_sketch(message: Message):
    await message.answer(
        "Да, конечно. Можно прийти со своим эскизом или референсом, "
        "а также доработать идею вместе со мной."
    )


@dp.message(F.text == "Сколько длится сеанс?")
async def faq_duration(message: Message):
    await message.answer(
        "Длительность зависит от размера и сложности работы: "
        "небольшие татуировки могут занять 1–2 часа, крупные — несколько сеансов."
    )


@dp.message(F.text == "Назад в меню")
async def back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_keyboard)


@dp.message(F.text == "Связаться с мастером")
async def contact_master(message: Message):
    await message.answer(
        "Вы можете написать напрямую: @XIIXIIXIIXIIXIIXIIXIIX\n"
        "Или оставить заявку через кнопку «Записаться на сеанс».",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "Записаться на сеанс")
async def booking_start(message: Message, state: FSMContext):
    await state.set_state(BookingStates.waiting_for_name)
    logging.info(f"Пользователь {message.from_user.id} начал оформление заявки")
    await message.answer(
        "Отлично. Давай начнём запись.\n\nКак тебя зовут?",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(BookingStates.waiting_for_name)
async def booking_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(BookingStates.waiting_for_description)
    await message.answer(
        "Опиши идею татуировки.\n"
        "Можно отправить либо обычный текст, либо до 10 фото с подписью в одном сообщении.\n\n"
        "Укажи, что хочешь набить, стиль, размер и место нанесения."
    )


@dp.message(BookingStates.waiting_for_description, F.photo)
async def booking_description_with_photo(message: Message, state: FSMContext):
    description = message.caption.strip() if message.caption else None

    if not description:
        await message.answer(
            "Пожалуйста, добавь к фото подпись с описанием идеи: что хочешь набить, стиль, размер, место нанесения."
        )
        return

    largest_photo = message.photo[-1]
    await state.update_data(
        description=description,
        reference_file_id=largest_photo.file_id,
        reference_file_ids=[largest_photo.file_id],
    )
    await state.set_state(BookingStates.waiting_for_dates)
    await message.answer(
        "Отлично, описание и референс получил !\n"
        "Теперь напиши удобные даты или дни для записи.\n"
        "Например: после 20 апреля, по выходным, вечером в будни.",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(BookingStates.waiting_for_description, F.text)
async def booking_description_text(message: Message, state: FSMContext):
    await state.update_data(
        description=message.text.strip(),
        reference_file_id=None,
        reference_file_ids=[],
    )
    await state.set_state(BookingStates.waiting_for_dates)
    await message.answer(
        "Принял описание !\n"
        "Теперь напиши удобные даты или дни для записи.\n"
        "Например: после 20 апреля, по выходным, вечером в будни.",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(BookingStates.waiting_for_description)
async def booking_description_invalid(message: Message):
    await message.answer(
        "Отправь либо текстовое описание идеи, либо до 10 фото с подписью в одном сообщении."
    )


@dp.message(BookingStates.waiting_for_dates)
async def booking_dates(message: Message, state: FSMContext):
    await state.update_data(preferred_dates=message.text.strip())
    await state.set_state(BookingStates.waiting_for_contact)
    await message.answer(
        "Теперь оставь контакт для связи.\n"
        "Можно нажать кнопку ниже и отправить номер телефона,\n"
        "или ввести вручную телефон, @username или email.",
        reply_markup=contact_keyboard
    )


@dp.message(BookingStates.waiting_for_contact, F.contact)
async def booking_contact_shared(message: Message, state: FSMContext):
    if not message.contact:
        await message.answer("Не удалось получить контакт. Попробуй ещё раз или введи его вручную.")
        return

    await finalize_application(message, state, message.contact.phone_number)


@dp.message(BookingStates.waiting_for_contact, F.text == "Ввести контакт вручную")
async def booking_contact_manual_prompt(message: Message):
    await message.answer(
        "Введи контакт вручную: номер телефона, @username или email.",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(BookingStates.waiting_for_contact, F.text)
async def booking_contact_manual(message: Message, state: FSMContext):
    contact = message.text.strip()

    if not is_valid_contact(contact):
        await message.answer(
            "Контакт выглядит некорректно.\n"
            "Отправь номер телефона, @username или email."
        )
        return

    await finalize_application(message, state, contact)


# =========================
# ЗАПУСК
# =========================
async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())