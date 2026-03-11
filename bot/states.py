from aiogram.fsm.state import State, StatesGroup


class AdminBroadcastState(StatesGroup):
    waiting_target = State()
    waiting_content_type = State()
    waiting_content = State()
