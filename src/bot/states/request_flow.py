from aiogram.fsm.state import State, StatesGroup


class CalcFlow(StatesGroup):
    waiting_direction = State()
    waiting_amount = State()


class CreateRequestFlow(StatesGroup):
    waiting_direction = State()
    waiting_amount = State()
    waiting_full_name = State()
    waiting_phone = State()
    waiting_requisites = State()


class AmlFlow(StatesGroup):
    waiting_check_type = State()
    waiting_value = State()
