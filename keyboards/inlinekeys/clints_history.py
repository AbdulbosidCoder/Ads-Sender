from loader import db

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_clints_history(telegram_id):
    clints = db.get_clients_history(telegram_id)
    user_button = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="all")]], resize_keyboard=True)
    clints = [row[0] for row in db.get_clients_history(telegram_id)]
    for clint in clints:
        user_button.keyboard.append([KeyboardButton(text=clint[0])])
    return user_button