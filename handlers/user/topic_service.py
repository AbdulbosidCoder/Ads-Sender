# handlers/topic_create_db_only.py
from __future__ import annotations
import re
from typing import Optional

from aiogram import types, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberOwner, ChatMemberAdministrator

from loader import dp, db, bot

def _ensure_group_row(m: types.Message) -> Optional[dict]:
    """Guruh rowini topadi, bo'lmasa yaratadi."""
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return None
    g = db.get_group_by_telegram_id(m.chat.id)
    if not g:
        gid = db.create_group(telegram_id=m.chat.id, name=m.chat.title or "", user_id=None)
        g = db.get_group_by_id(gid)
    return g



async def _bot_can_manage_topics(chat_id: int) -> bool:
    me = await bot.me()
    cm = await bot.get_chat_member(chat_id, me.id)
    # ChatMemberAdministrator da can_manage_topics bo'ladi, Ownerda default True deya olamiz
    if isinstance(cm, ChatMemberOwner):
        return True
    if isinstance(cm, ChatMemberAdministrator):
        return bool(getattr(cm, "can_manage_topics", False))
    return False



# ========== /topic_list ==========
@dp.message(Command("topic_list"))
async def topic_list(m: types.Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        await m.answer("Bu komandani guruh ichida ishlating.")
        return

    g = _ensure_group_row(m)
    if not g:
        await m.reply("Guruh ma’lumotini topib bo‘lmadi.")
        return

    rows = db.list_topics_by_group(g["id"], limit=200, offset=0) or []
    if not rows:
        await m.reply("Bu guruhda DB’da topic yo‘q.")
        return

    text_lines = ["<b>Topiclar (DB)</b>:"]
    for r in rows:
        text_lines.append(f"• <b>ID:</b> {r['id']} | <b>Thread:</b> <code>{r['telegram_id']}</code> | <b>Nom:</b> {r.get('name','')}")
    await m.reply("\n".join(text_lines), parse_mode="HTML")


@dp.message(Command("topic_set_general"))
async def topic_set_general(m: types.Message):
    # Foydalanish: /topic_set_general 12   (12 — DB topic_id)
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.reply("Foydalanish: <code>/topic_set_general &lt;topic_id&gt;</code>", parse_mode="HTML")
        return
    topic_id = int(parts[1])
    t = db.get_topic_by_id(topic_id)
    if not t:
        await m.reply("Topic DB’da topilmadi.")
        return
    # Shu guruh ichidamizmi?
    g = db.get_group_by_telegram_id(m.chat.id)
    if not g or t["group_id"] != g["id"]:
        await m.reply("Bu topic ushbu guruhga tegishli emas.")
        return
    # Avval shu guruhning hamma topiclarida is_general=0, so‘ng bu topicga =1
    for row in db.list_topics_by_group(g["id"]):
        db.update_topic(row["id"], is_general=1 if row["id"] == topic_id else 0)
    await m.reply(f"⭐️ General topic o‘rnatildi. (DB ID: {topic_id})")
