# general_reader.py — rewritten for multi-item router
from __future__ import annotations
import re
from typing import Optional, List

from aiogram import types, F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


from loader import db, bot
from utils.request_chatgpt import gpt_format_and_route, text_hash, _ns

group_msg_router = Router()

# Telefon aniqlash (kontakt bor-yo‘qni oldindan tekshirish uchun)
PHONE_RE = re.compile(r"\+?\d[\d\-\s]{6,}\d")

def _has_phone(s: str) -> bool:
    return bool(PHONE_RE.search(s or ""))

def _username_at(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip()
    if not u:
        return None
    return u if u.startswith("@") else f"@{u}"

@group_msg_router.message(F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}) & F.text)
async def on_general_message(m: types.Message, state: FSMContext):
    group_tid = m.chat.id
    g = db.get_group_by_telegram_id(group_tid)
    if not g:
        gid = db.create_group(telegram_id=group_tid, name=m.chat.title or "", user_id=None)
        g = db.get_group_by_id(gid)

    raw_text = _ns(m.text or "")
    if not raw_text:
        return

    # usernames
    from_user_username = m.from_user.username if (m.from_user and m.from_user.username) else None
    fallback_username = _username_at(from_user_username) or "https://adminyukgo.oqdev.uz/"
    group_username = "https://adminyukgo.oqdev.uz/"

    # Routerga to‘liq xabarni beramiz — u ichida bo‘lib, N item qaytaradi
    res = await gpt_format_and_route(
        src_group_db_id=g["id"],
        message_text=raw_text,
        fallback_username=fallback_username,
        group_username=group_username,
    )
    if not res:
        return

    # Router ikki xil shaklda qaytishi mumkin: single yoki multi
    if isinstance(res, dict) and "items" in res:
        items = res.get("items") or []
    else:
        items = [res]

    # Agar hech bo‘lmasa bitta OK item bo‘lsa — yuboramiz; aks holda, “Noto‘g‘ri format” shartlarini tekshiramiz
    any_ok = any(it.get("ok") for it in items if isinstance(it, dict))

    # Kontakt mavjudligini xom xabar bo‘yicha oldindan tekshiramiz
    has_contact_by_message = _has_phone(raw_text) or bool(from_user_username)

    if not any_ok:
        # Barcha itemlar NOK: “Noto‘g‘ri format” faqat (kontakt yo‘q) VA (destination/yo‘nalish yo‘q) bo‘lsa
        reasons = { (it or {}).get("reason") for it in items if isinstance(it, dict) }
        missing_dest = any(r in ("missing_destination", "missing_location") for r in reasons)
        if (not has_contact_by_message) and missing_dest:
            try:
                await m.reply("Noto‘g‘ri format. Kontakt (username yoki telefon) va shahar yo‘nalishlari ko‘rsatilmagan.")
            except Exception:
                pass
        return

    # Bir xabardan kelgan ko‘p itemlar orasida dublikat yuborishni oldini olamiz (full_text hash bo‘yicha)
    sent_hashes = set()

    for it in items:
        if not it or not it.get("ok"):
            continue

        short_text = (it.get("short_text") or "").strip()
        full_text  = (it.get("full_text") or "").strip()
        if not short_text or not full_text:
            continue

        # Dublikatni tekshirish (shu xabar doirasida)
        item_full_hash = text_hash(full_text)
        if item_full_hash in sent_hashes:
            continue
        sent_hashes.add(item_full_hash)

        # Kesh bo‘yicha tekshirish (ilgari yuborilgan bo‘lsa — skip)
        cached = db.get_route_by_hash(message_hash=item_full_hash, src_group_tid=group_tid)
        if cached:
            # Baribir “to‘liq ko‘rish” matnini yangilab qo‘yamiz (agar kerak bo‘lsa)
            db.save_full_by_hash(item_full_hash[:32], full_text)
            continue

        # Manzil
        try:
            dst_group = db.get_group_by_id(int(it["group_id"]))
            dst_topic = db.get_topic_by_id(int(it["topic_id"]))
        except Exception:
            continue
        if not (dst_group and dst_topic):
            continue

        # “To‘liq ko‘rish” uchun full_text saqlaymiz (short text kartochkada ko‘rinadi)
        h = item_full_hash[:32]
        db.save_full_by_hash(h, full_text)

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="👁 To‘liq ko‘rish", callback_data=f"full:{h}")
        ]])

        await bot.send_message(
            chat_id=dst_group["telegram_id"],
            message_thread_id=dst_topic["telegram_id"],
            text=short_text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )

        # Route keshini yaratamiz (keyingi shunga o‘xshash itemlar yuborilmasligi uchun)
        db.create_message_route_cache(
            message_hash=item_full_hash,
            src_group_tid=group_tid,
            dst_group_id=dst_group["id"],
            dst_topic_id=dst_topic["id"],
        )

import re

@group_msg_router.callback_query(F.data.startswith("full:"))
async def on_full_view(c: types.CallbackQuery, state: FSMContext):
    h = c.data.split(":", 1)[1] if (c.data and ":" in c.data) else ""
    full = db.get_full_by_hash(h) or "To‘liq matn topilmadi."

    plain = re.sub(r"<[^>]*>", "", full or "")
    plain = re.sub(r"\s+", " ", plain).strip()

    MAX_ALERT = 190
    if len(plain) > MAX_ALERT:
        plain = plain[:MAX_ALERT].rstrip() + "…"

    await c.answer(plain or "To‘liq matn topilmadi.", show_alert=True)
