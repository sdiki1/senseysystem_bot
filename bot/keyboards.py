from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="▶️ Начать диагностику", callback_data="diag:start")]]
    )


def diagnostic_question_keyboard(question_index: int, options: tuple[str, str, str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=option, callback_data=f"diag:answer:{question_index}:{option_index}")]
        for option_index, option in enumerate(options)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def diagnostic_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Войти в систему — SENSEY club", callback_data="offer:club")],
            [InlineKeyboardButton(text="⚔️ Личный разбор — увидеть слепые зоны", callback_data="offer:consult")],
        ]
    )


def reminder_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔒 SENSEY club", callback_data="offer:club")],
            [InlineKeyboardButton(text="⚔️ Личный разбор", callback_data="offer:consult")],
        ]
    )


def continue_diagnostic_keyboard(label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data="diag:continue")]]
    )


def club_offer_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Войти в SENSEY club — 3000 ₽", url=url)]]
    )


def consult_offer_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Записаться на разбор — 10 000 ₽", url=url)]]
    )


def payment_url_keyboard(label: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])


def channel_access_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔓 Вступить в SENSEY club", url=url)]]
    )


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users")],
            [InlineKeyboardButton(text="💰 Платежи", callback_data="admin:payments")],
        ]
    )


def admin_broadcast_target_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Все", callback_data="admin:broadcast_target:all")],
            [InlineKeyboardButton(text="Только CLUB", callback_data="admin:broadcast_target:club")],
            [InlineKeyboardButton(text="Только Разбор", callback_data="admin:broadcast_target:consult")],
        ]
    )


def admin_broadcast_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Текст", callback_data="admin:broadcast_type:text")],
            [InlineKeyboardButton(text="Фото", callback_data="admin:broadcast_type:photo")],
            [InlineKeyboardButton(text="Видео", callback_data="admin:broadcast_type:video")],
        ]
    )
