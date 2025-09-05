from pprint import pprint

from aiogram.filters import CommandStart, Command
from aiogram import types
from aiogram.fsm.context import FSMContext

from loader import dp


@dp.message(Command("help"))
async def start_bot(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        (
            "👋 Assalomu alaykum!\n\n"
            "Sizni <b>SendAds Bot</b> ga xush kelibsiz!\n\n"
            "📢 Ushbu bot yordamida siz e’lonlaringizni to‘g‘ri mavzularga "
            "avtomatik joylashtira olasiz.\n\n"
            "⚙️ Qanday ishlaydi?\n"
            "1️⃣ Botni kerakli guruhga qo‘shing va unga <b>admin huquqlari</b>ni bering.\n"
            "2️⃣ Bot guruhdagi <i>topic</i>larni avtomatik aniqlab, e’lonlarni kerakli joyga yo‘naltiradi.\n"
            "3️⃣ Siz shunchaki e’lon yuborasiz, qolganini bot o‘zi qiladi ✅\n\n"
            "➡️ Iltimos, hozir botni kerakli guruh(lar)ingizga qo‘shib, admin qilib qo‘ying.\n"
            "Shundan so‘ng siz reklama yuborishingiz mumkin bo‘ladi.\n\n"
            "Boshlash uchun: /start"
        ),
        parse_mode="HTML"
    )


