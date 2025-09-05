# topic_watcher.py
from aiogram import types, F, Router
from aiogram.enums import ChatType
from loader import db

topic_db_router = Router()

def _ensure_group(chat: types.Chat):
    g = db.get_group_by_telegram_id(chat.id)
    if not g:
        gid = db.create_group(telegram_id=chat.id, name=chat.title or "")
        g = db.get_group_by_id(gid)
    return g

def _find_topic_row(group_id: int, thread_id: int):
    rows = [x for x in db.list_topics_by_group(group_id) if x["telegram_id"] == thread_id]
    return rows[0] if rows else None


# Yangi topic yaratilsa
@topic_db_router.message(F.forum_topic_created)
async def on_topic_created(m: types.Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return

    t = m.forum_topic_created
    thread_id = m.message_thread_id  # new topic thread id
    name = t.name or f"thread:{thread_id}"

    g = _ensure_group(m.chat)

    existing = _find_topic_row(g["id"], thread_id)
    if existing:
        # If it somehow already exists, just update the name (reactivate too)
        try:
            db.update_topic(existing["id"], name=name, is_active=True)
        except TypeError:
            # If your update_topic doesn't accept is_active, just update name
            db.update_topic(existing["id"], name=name)
    else:
        db.create_topic(telegram_id=thread_id, name=name, group_id=g["id"])
    # (Optional) feedback to chat:
    # await m.answer(f"New topic created: {name}")


# Topic nomi o'zgarsa
@topic_db_router.message(F.forum_topic_edited)
async def on_topic_edited(m: types.Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return

    t = m.forum_topic_edited
    thread_id = m.message_thread_id

    g = db.get_group_by_telegram_id(m.chat.id)
    if not g:
        return

    row = _find_topic_row(g["id"], thread_id)
    if not row:
        # If we missed 'created' earlier, create now with best-effort name
        name = t.name or f"thread:{thread_id}"
        db.create_topic(telegram_id=thread_id, name=name, group_id=g["id"])
        return

    # Keep old name if only icon/color changed (t.name can be None)
    new_name = t.name or row["name"]
    if new_name != row["name"]:
        db.update_topic(row["id"], name=new_name)


# Topic yopilsa (close)
@topic_db_router.message(F.forum_topic_closed)
async def on_topic_closed(m: types.Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return

    thread_id = m.message_thread_id
    g = db.get_group_by_telegram_id(m.chat.id)
    if not g:
        return

    row = _find_topic_row(g["id"], thread_id)
    if not row:
        return

    # Prefer hard delete if your DB supports it, otherwise soft-delete
    deleted = False
    try:
        # If your db has a hard delete:
        db.delete_topic(row["id"])
        deleted = True
    except AttributeError:
        # Fallback to soft delete flag
        try:
            db.update_topic(row["id"], is_active=False)
        except TypeError:
            # If your schema has no 'is_active', you can no-op or repurpose another field
            pass

    # (Optional) you could log or notify admins here about the deletion/soft-deletion


# Topic qayta ochilsa (reopen)
@topic_db_router.message(F.forum_topic_reopened)
async def on_topic_reopened(m: types.Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return

    thread_id = m.message_thread_id
    g = _ensure_group(m.chat)

    row = _find_topic_row(g["id"], thread_id)
    if row:
        # Reactivate if previously soft-deleted; ensure it’s active in UI
        try:
            db.update_topic(row["id"], is_active=True)
        except TypeError:
            # Schema without is_active: nothing to do
            pass
    else:
        # If it was hard-deleted or never captured, recreate with a generic name
        name = f"thread:{thread_id}"
        db.create_topic(telegram_id=thread_id, name=name, group_id=g["id"])


# (Optional) General topic hide/unhide → treat like active flag flips
@topic_db_router.message(F.general_forum_topic_hidden)
async def on_general_topic_hidden(m: types.Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return
    g = db.get_group_by_telegram_id(m.chat.id)
    if not g:
        return
    # General topic has its own thread id (usually 1). Use message_thread_id provided.
    row = _find_topic_row(g["id"], m.message_thread_id)
    if row:
        try:
            db.update_topic(row["id"], is_active=False)
        except TypeError:
            pass


@topic_db_router.message(F.general_forum_topic_unhidden)
async def on_general_topic_unhidden(m: types.Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return
    g = _ensure_group(m.chat)
    row = _find_topic_row(g["id"], m.message_thread_id)
    if row:
        try:
            db.update_topic(row["id"], is_active=True)
        except TypeError:
            pass
    else:
        db.create_topic(telegram_id=m.message_thread_id, name="General", group_id=g["id"])
