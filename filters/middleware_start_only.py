# middlewares/command_gate.py
from typing import Callable, Awaitable, Dict, Set
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from aiogram.enums import ChatType

from loader import db  # your shared DB instance

def _is_command(msg: Message) -> bool:
    if not msg.text:
        return False
    if msg.entities:
        for e in msg.entities:
            if e.type == "bot_command" and e.offset == 0:
                return True
    return msg.text.startswith("/")


class CommandGateMiddleware(BaseMiddleware):
    """
    Group chats:
      - Non-commands -> always pass to handlers (do not block messages).
      - Commands     -> only allowed roles may pass to handlers; others are swallowed (no reply).
    Private chats:
      - Everything passes (you can handle /start etc. as usual).

    Configure allowed roles via `allowed_roles`.
    """
    def __init__(self, allowed_roles: Set[str] | None = None):
        self.allowed_roles = allowed_roles or {"admin"}  # adjust if you have "moderator", etc.

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict], Awaitable],
        event: TelegramObject,
        data: Dict,
    ):
        if not isinstance(event, Message):
            return await handler(event, data)

        msg: Message = event

        # PRIVATE: allow everything (your /start or other commands will work)
        if msg.chat.type == ChatType.PRIVATE:
            # Optional: attach role for convenience
            if msg.from_user:
                role = db.get_role_by_telegram_id(msg.from_user.id)
                data["user_role"] = role
            return await handler(event, data)

        # GROUP/SUPERGROUP:
        if msg.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            # 1) Non-commands -> always pass through (do NOT block messages)
            if not _is_command(msg):
                return await handler(event, data)

            # 2) Commands -> check role
            user_role = None
            if msg.from_user:
                user_role = db.get_role_by_telegram_id(msg.from_user.id)

            # If role is allowed -> let handlers run (and pass role to them)
            if user_role in self.allowed_roles:
                data["user_role"] = user_role
                return await handler(event, data)

            # Not allowed -> swallow (no handler, no reply)
            return

        # Other chat types -> default behavior
        return await handler(event, data)
