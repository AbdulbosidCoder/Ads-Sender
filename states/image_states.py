from aiogram.fsm.state import StatesGroup, State


class ImageGroup(StatesGroup):
    getUserNameState = State()
    getGroupNameState = State()
    getDeleteUserState = State()