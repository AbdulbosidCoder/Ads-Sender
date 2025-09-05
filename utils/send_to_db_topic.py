# utils/send_to_db_topic.py
from __future__ import annotations
from typing import Optional
from aiogram import Bot

def get_thread_ids_for_topic(db, *, topic_db_id: int) -> Optional[tuple[int, int]]:
    """
    Returns (group_tid, thread_tid) for a DB topic_id,
    yoki None agar topilmasa.
    """
    t = db.get_topic_by_id(topic_db_id)
    if not t:
        return None
    g = db.get_group_by_id(t["group_id"])
    if not g:
        return None
    return int(g["telegram_id"]), int(t["telegram_id"])

async def send_to_db_topic(
    db,
    bot: Bot,
    *,
    topic_db_id: int,
    text: str,
    parse_mode: Optional[str] = "HTML",
    disable_web_page_preview: bool = True,
):
    ids = get_thread_ids_for_topic(db, topic_db_id=topic_db_id)
    if not ids:
        raise ValueError("Topic yoki Group DB’da topilmadi.")
    group_tid, thread_tid = ids
    return await bot.send_message(
        chat_id=group_tid,
        message_thread_id=thread_tid,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )
