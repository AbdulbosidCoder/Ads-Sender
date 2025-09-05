# handlers/topic_create_private.py
from __future__ import annotations
import re
from typing import Optional

from aiogram import types, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import dp, db


router = Router()
# ---------- FSM ----------
class TopicCreatePriv(StatesGroup):
    pick_group = State()
    enter_thread = State()
    enter_name = State()

# ---------- Helpers ----------
def _normalize_space(s: str | None) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", (s or "")).strip()

def _ensure_user_row(m: types.Message) -> Optional[dict]:
    """Userni DBdan oladi, bo'lmasa yaratadi."""
    u = db.get_user_by_telegram_id(m.from_user.id)
    if not u:
        uid = db.create_user(
            telegram_id=m.from_user.id,
            username=m.from_user.username,
            first_name=m.from_user.first_name,
            last_name=m.from_user.last_name,
        )
        u = db.get_user_by_id(uid)
    return u

# ---------- /topic_create: start in PRIVATE ----------
@router.message(Command("topic_create"))
async def topic_create_start(m: types.Message, state: FSMContext):
    if m.chat.type != ChatType.PRIVATE:
        await m.answer("Iltimos, bu komandani shaxsiy chatda (/topic_create) ishlating.")
        return

    user = _ensure_user_row(m)
    if not user:
        await m.answer("Profilingizni saqlab bo‘lmadi. Keyinroq urinib ko‘ring.")
        return

    groups = db.list_groups_by_user(user["id"], limit=100, offset=0) or []
    if not groups:
        await m.answer("Sizga biriktirilgan guruh topilmadi. Avval botni guruh(lar)ga qo‘shing.")
        return

    kb = InlineKeyboardBuilder()
    for g in groups:
        title = (g["name"] or str(g["telegram_id"]))[:60]
        kb.button(text=title, callback_data=f"tpc_pick_group:{g['id']}")
    kb.adjust(1)

    await m.answer("Qaysi guruhga topic qo‘shamiz? ⬇️", reply_markup=kb.as_markup())
    await state.clear()
    await state.set_state(TopicCreatePriv.pick_group)

# ---------- Group picked ----------
@router.callback_query(TopicCreatePriv.pick_group, F.data.startswith("tpc_pick_group:"))
async def topic_create_group_picked(c: types.CallbackQuery, state: FSMContext):
    await c.answer()
    try:
        group_id = int(c.data.split(":")[1])
    except Exception:
        await c.message.answer("Noto‘g‘ri guruh tanlovi.")
        return

    g = db.get_group_by_id(group_id)
    if not g:
        await c.message.answer("Guruh DB’da topilmadi.")
        return

    await state.update_data(group_id=group_id)
    await c.message.edit_reply_markup()
    await c.message.answer(
        "Topic’ning <b>thread_id</b> (Telegram topic id) ini yuboring.\n"
        "Masalan: <code>12345</code>\n\n"
        "Eslatma: bu qiymat guruhdagi forum topic’ning <i>message_thread_id</i> bo‘lishi kerak.",
        parse_mode="HTML",
    )
    await state.set_state(TopicCreatePriv.enter_thread)

# ---------- Thread ID entered ----------
@router.message(TopicCreatePriv.enter_thread, F.text)
async def topic_create_thread_received(m: types.Message, state: FSMContext):
    txt = _normalize_space(m.text)
    if not re.fullmatch(r"\d{1,12}", txt or ""):
        await m.answer("Iltimos, faqat raqamlardan iborat <code>thread_id</code> yuboring. Masalan: <code>12345</code>", parse_mode="HTML")
        return

    thread_id = int(txt)
    await state.update_data(thread_id=thread_id)

    await m.answer(
        "Endi topic <b>nomi</b>ni yuboring (maks. 128 belgi).\n"
        "Masalan: <code>NAMANGAN</code>",
        parse_mode="HTML",
    )
    await state.set_state(TopicCreatePriv.enter_name)

# ---------- Name entered -> save to DB ----------
@router.message(TopicCreatePriv.enter_name, F.text)
async def topic_create_name_received(m: types.Message, state: FSMContext):
    name = _normalize_space(m.text)
    if not name:
        await m.answer("Topic nomi bo‘sh bo‘lmasin. Qayta yuboring.")
        return
    if len(name) > 128:
        await m.answer("Topic nomi 128 belgidan oshmasin. Qayta yuboring.")
        return

    data = await state.get_data()
    group_id = data.get("group_id")
    thread_id = data.get("thread_id")

    if not group_id or thread_id is None:
        await m.answer("Sessiya ma’lumoti topilmadi. Qayta /topic_create yuboring.")
        await state.clear()
        return

    # Shu group + thread_id bor-yo'qligini tekshirish
    rows = db.list_topics_by_group(group_id) or []
    exists = next((t for t in rows if int(t["telegram_id"]) == int(thread_id)), None)

    try:
        if exists:
            # update (rename)
            db.update_topic(exists["id"], name=name)
            await m.answer(
                "♻️ Topic yangilandi (DB):\n"
                f"- DB ID: <b>{exists['id']}</b>\n"
                f"- Thread ID: <code>{thread_id}</code>\n"
                f"- Nom: <b>{name}</b>",
                parse_mode="HTML",
            )
        else:
            # create
            topic_db_id = db.create_topic(telegram_id=thread_id, name=name, group_id=group_id)
            await m.answer(
                "✅ Topic DBga qo‘shildi:\n"
                f"- DB ID: <b>{topic_db_id}</b>\n"
                f"- Thread ID: <code>{thread_id}</code>\n"
                f"- Nom: <b>{name}</b>",
                parse_mode="HTML",
            )
    except Exception as e:
        await m.answer(f"DB xatosi: {e}")
        return

    await state.clear()
