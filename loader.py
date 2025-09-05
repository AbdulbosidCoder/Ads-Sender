from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from data.config import TOKEN
from aiogram.fsm.storage.memory import MemoryStorage
from utils.sqlite import Database

bot = Bot(token=TOKEN,default= DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher(storage=MemoryStorage())
db = Database("data/main.db")
