import os, re, asyncio
from typing import Optional

from aiogram import Bot, F
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)

from loader import dp, db, bot

# ================= States =================
class TokenState(StatesGroup):
    gpt_token = State()

class User(StatesGroup):
    get_contact = State()

# ================= Token update =================
@dp.message(Command("token"))
async def _update_gpt_token(message: Message, state: FSMContext):
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Iltimos, tokenni shaxsiy chatda yuboring.")
        return
    await message.answer("Yangi ChatGPT tokenini kiriting:")
    await state.set_state(TokenState.gpt_token)

@dp.message(TokenState.gpt_token)
async def _update_gpt_token2(message: Message, state: FSMContext):
    token = (message.text or "").strip()
    if not token:
        await message.answer("❌ Token bo‘sh bo‘lmasin.")
        await state.clear()
        return
    try:
        from openai import OpenAI
        client = OpenAI(api_key=token)
        # block API call off the event loop
        await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
        )
    except Exception:
        await message.answer("❌ Token noto‘g‘ri yoki ishlamadi.")
        await state.clear()
        return

    # .env update
    try:
        env_path = ".env"
        lines, found = [], False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("OPENAI_API_KEY="):
                        lines.append(f"OPENAI_API_KEY={token}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"OPENAI_API_KEY={token}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        os.environ["OPENAI_API_KEY"] = token
        await message.answer("✅ Token ishlayapti va .env faylda yangilandi!")
    except Exception:
        await message.answer("⚠️ Token ishladi, lekin .env faylni yangilashda xato bo‘ldi!")

    await state.clear()

# ================= DB helpers (yours) =================
def upsert_user_from_message(m: Message) -> int:
    tg_id = m.from_user.id
    existing = db.get_user_by_telegram_id(tg_id)
    if existing:
        fields = {}
        username = m.from_user.username or None
        first_name = m.from_user.first_name or None
        last_name = m.from_user.last_name or None
        if existing.get("username") != username:
            fields["username"] = username
        if existing.get("first_name") != first_name:
            fields["first_name"] = first_name
        if existing.get("last_name") != last_name:
            fields["last_name"] = last_name
        if fields:
            db.update_user(existing["id"], **fields)
        return int(existing["id"])
    return db.create_user(
        telegram_id=tg_id,
        username=m.from_user.username or None,
        first_name=m.from_user.first_name or None,
        last_name=m.from_user.last_name or None,
    )

def upsert_group_from_chat(chat_id: int, title: Optional[str], owner_user_id: Optional[int] = None) -> int:
    existing = db.get_group_by_telegram_id(chat_id)
    if existing:
        updates = {}
        if title is not None and existing.get("name") != title:
            updates["name"] = title
        if owner_user_id is not None and existing.get("user_id") != owner_user_id:
            updates["user_id"] = owner_user_id
        if updates:
            db.update_group(existing["id"], **updates)
        return int(existing["id"])
    return db.create_group(telegram_id=chat_id, name=title or "", user_id=owner_user_id)

async def check_is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        status = getattr(member, "status", None)
        return status in ("administrator", "creator")
    except TelegramBadRequest:
        return False
    except Exception:
        return False

async def link_owner(bot: Bot, m: Message):
    chat = m.chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    owner_user_pk = upsert_user_from_message(m)
    upsert_group_from_chat(chat.id, chat.title or "", owner_user_id=owner_user_pk)

# ================= /start (fixed) =================
def _contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Kontaktni ulashish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    if m.chat.type != ChatType.PRIVATE:
        await m.answer("Salom! Ro‘yxatdan o‘tish uchun menga shaxsiy (DM) yozing.")
        return

    # Ensure user exists/updated
    upsert_user_from_message(m)
    row = db.get_user_by_telegram_id(m.from_user.id)

    # If already has phone, greet and stop
    if row and row.get("phone_number") and row.get("role") == "admin":
        await m.answer("✅ Ro‘yxatdan o‘tgansiz. Menga grouppani ichida e’lon yuboring — men tegishli guruh(lar)ga joylayman.")
        return
    if row or row.get("role") != "admin":
        await  m.answer("Iltimos menni gurihga qo'shing va admin lik huquqini bering")
    await m.answer(
        "Salom! Iltimos, kontaktni ulashing (yoki telefon raqamingizni yozing).",
        reply_markup=_contact_kb(),
    )
    await state.set_state(User.get_contact)

# ================= Contact capture (fixed) =================
PHONE_RE = re.compile(r"^\+?\d{7,15}$")

def _norm_phone(s: str) -> str:
    # remove spaces, dashes, parentheses
    return re.sub(r"[^\d+]", "", s or "")

@dp.message(User.get_contact, F.contact)
async def get_contact_via_button(m: Message, state: FSMContext):
    if not m.contact:
        await m.answer("Kontakt topilmadi. Qayta urinib ko‘ring.")
        return

    # ensure it is the user's own contact
    if m.contact.user_id and m.contact.user_id != m.from_user.id:
        await m.answer("Iltimos, o‘zingizning kontaktingizni ulashing.")
        return


    phone = _norm_phone(m.contact.phone_number)
    user_pk = upsert_user_from_message(m)
    db.update_user(user_pk, phone_number=phone)

    await m.answer("✅ Ro‘yxatdan o‘tdingiz!", reply_markup=ReplyKeyboardRemove())
    user = db.get_user_by_telegram_id(m.chat.id)
    if user.get("role") != "admin":
        await m.answer("Iltimos botni grouppaga qo'shib admin lik huquqini bering!!!")
        return
@dp.message(User.get_contact, F.text)
async def get_contact_via_text(m: Message, state: FSMContext):
    phone = _norm_phone(m.text)
    user = db.get_user_by_telegram_id(m.chat.id)
    if not PHONE_RE.match(phone) and user.get("role") != "admin":
        await m.answer("Telefon raqam noto‘g‘ri. Namuna: +99890xxxxxxx yoki 909999999. Qayta yuboring.")
        return

    user_pk = upsert_user_from_message(m)
    db.update_user(user_pk, phone_number=phone)

    await m.answer("✅ Ro‘yxatdan o‘tdingiz!", reply_markup=ReplyKeyboardRemove())
    await state.clear()

# ================= Group linking (when bot added) =================
@dp.message(F.new_chat_members)
async def on_new_members(m: Message, bot: Bot, state: FSMContext):
    me = await bot.get_me()
    for u in m.new_chat_members:
        if u.id == me.id:
            # Link group owner: your existing logic
            await link_owner(bot, m)

            # Promote the adder to admin in DB
            owner_user_pk = upsert_user_from_message(m)  # ensures user row exists/updated
            db.set_user_role(owner_user_pk, "admin")

            await m.reply(
                (
                    f"Rahmat! Botni qo‘shgan: <b>{m.from_user.full_name}</b> (id={m.from_user.id}).\n"
                    f"Sizga admin rol berildi. Endi DM orqali e’lon yuborsangiz — shu guruhga joylanadi."
                ),
                parse_mode=ParseMode.HTML,
            )
    await state.clear()
# ================= Utilities =================
@dp.message(Command("my_groups"))
async def my_groups(m: Message, bot: Bot):
    if m.chat.type != ChatType.PRIVATE:
        return

    user_pk = upsert_user_from_message(m)
    groups = db.list_groups_by_user(user_pk, limit=500, offset=0)
    if not groups:
        await m.answer("Sizga biriktirilgan guruh yo‘q. Botni biror guruhga qo‘shing.")
        return

    lines = []
    for g in groups:
        chat_id = int(g["telegram_id"])
        title = g.get("name") or str(chat_id)
        is_admin_now = await check_is_admin(bot, chat_id, m.from_user.id)
        lines.append(f"• {title} — admin={bool(is_admin_now)}")

    await m.answer("Sizga biriktirilgan guruhlar:\n" + "\n".join(lines))
