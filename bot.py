# bot.py fayli (Serverga joylash uchun to'liq versiya)

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Kerakli kutubxonalar
from pydub import AudioSegment
import speech_recognition as sr
from deep_translator import GoogleTranslator, MyMemoryTranslator, LingueeTranslator

# --- BOTNI SOZLASH ---
# Tokenni xavfsiz tarzda muhit o'zgaruvchisidan (environment variable) olamiz
# Bu tokenni Render'dagi "Environment" bo'limiga kiritasiz
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Agar token topilmasa, bot ishini to'xtatadi
if not BOT_TOKEN:
    logging.critical("Xatolik: TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi topilmadi!")
    exit("Iltimos, Render'ning 'Environment' bo'limida tokeningizni kiriting!")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)


# --- TARJIMA FUNKSIYALARI ---
TRANSLATOR_FALLBACK_CHAIN = [
    ("Google", GoogleTranslator),
    ("MyMemory", MyMemoryTranslator),
    ("Linguee", LingueeTranslator)
]

async def get_reliable_translation(text, source_lang, target_lang):
    """
    Ishonchli tarjimani topadi (fallback tizimi).
    Ro'yxatdagi tarjimonlarni navbatma-navbat sinab ko'radi.
    """
    for name, translator_class in TRANSLATOR_FALLBACK_CHAIN:
        try:
            translated_text = translator_class(source=source_lang, target=target_lang).translate(text)
            if translated_text:
                logging.info(f"Successfully translated using {name}.")
                return translated_text, name
        except Exception as e:
            logging.warning(f"{name} translator failed. Error: {e}. Trying next one...")
            continue
    return None, None


# --- TELEGRAM HANDLER'LARI ---
user_directions = {}
DIRECTIONS_MAP = {
    "🇺🇿 UZ-RU 🇷🇺": ("uz", "ru"), "🇷🇺 RU-UZ 🇺🇿": ("ru", "uz"),
    "🇺🇿 UZ-EN 🇬🇧": ("uz", "en"), "🇬🇧 EN-UZ 🇺🇿": ("en", "uz"),
    "🇷🇺 RU-EN 🇬🇧": ("ru", "en"), "🇬🇧 EN-RU 🇷🇺": ("en", "ru"),
}

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    """Botga start bosilganda salomlashish va tugmalarni chiqarish."""
    builder = ReplyKeyboardBuilder()
    for text in DIRECTIONS_MAP.keys():
        builder.add(types.KeyboardButton(text=text))
    builder.adjust(2)
    await message.answer(
        "Assalomu alaykum! Tarjima uchun matnli yoki ovozli xabar yuboring.",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@dp.message(F.voice)
async def handle_voice_message(message: types.Message):
    """Ovozli xabarlarni qabul qilib, tarjima qiladi."""
    user_id = message.from_user.id
    
    if user_id not in user_directions:
        await message.answer("Iltimos, avval ovozli xabar qaysi tilga tarjima qilinishi uchun yo'nalishni tanlang.")
        return

    await message.answer("Ovozli xabar qabul qilindi, qayta ishlanmoqda...")
    
    file_id = message.voice.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    # downloads papkasi mavjudligini tekshirish va yaratish
    os.makedirs("downloads", exist_ok=True)
    
    ogg_filename = f"downloads/{file_id}.ogg"
    wav_filename = f"downloads/{file_id}.wav"

    await bot.download_file(file_path, destination=ogg_filename)
    
    try:
        AudioSegment.from_ogg(ogg_filename).export(wav_filename, format="wav")
    except Exception as e:
        logging.error(f"Could not convert .ogg to .wav: {e}")
        await message.answer("Kechirasiz, audio faylni qayta ishlashda xatolik yuz berdi. FFmpeg o'rnatilganini tekshiring.")
        return

    recognizer = sr.Recognizer()
    recognized_text = ""
    with sr.AudioFile(wav_filename) as source:
        audio_data = recognizer.record(source)
    
    try:
        source_lang_code, target_lang_code = user_directions[user_id]
        lang_map = {'uz': 'uz-UZ', 'ru': 'ru-RU', 'en': 'en-US'}
        google_lang_code = lang_map.get(source_lang_code, 'en-US')
        
        recognized_text = recognizer.recognize_google(audio_data, language=google_lang_code)
        await message.answer(f"<b>Aniqlangan matn:</b>\n\n<i>{recognized_text}</i>\n\nTarjima qilinmoqda...")

    except sr.UnknownValueError:
        await message.answer("Kechirasiz, nutqni aniqlab bo'lmadi.")
    except sr.RequestError as e:
        await message.answer(f"Nutqni aniqlash xizmatida xatolik yuz berdi: {e}")
    finally:
        # Vaqtinchalik fayllarni o'chirish
        if os.path.exists(ogg_filename): os.remove(ogg_filename)
        if os.path.exists(wav_filename): os.remove(wav_filename)

    if not recognized_text:
        return

    # Aniqlangan matnni tarjima qilish
    translated_text, translator_name = await get_reliable_translation(recognized_text, source_lang_code, target_lang_code)
    
    if translated_text:
        response = f"<b>Tarjima ({translator_name}):</b>\n\n{translated_text}"
    else:
        response = "😔 Kechirasiz, tarjima qilishda xatolik yuz berdi."
    
    await message.answer(response)

@dp.message(F.text)
