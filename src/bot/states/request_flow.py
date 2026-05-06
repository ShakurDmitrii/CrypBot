from aiogram.fsm.state import State, StatesGroup


class CalcFlow(StatesGroup):
    waiting_direction = State()
    waiting_amount = State()


class CreateRequestFlow(StatesGroup):
    waiting_direction = State()
    waiting_amount = State()
    waiting_full_name = State()
    waiting_requisites = State()
    waiting_confirm = State()
    waiting_edit_field = State()


class AmlFlow(StatesGroup):
    waiting_check_type = State()
    waiting_value = State()


class OperatorFlow(StatesGroup):
    waiting_margin_value = State()
    waiting_request_id = State()
    waiting_request_status = State()
    waiting_request_comment = State()
    waiting_aml_id = State()
    waiting_aml_status = State()
    waiting_aml_comment = State()
