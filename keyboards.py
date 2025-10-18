# keyboards.py
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# --- Главное меню ---
btn_buy = KeyboardButton(text="🛒 Купить VPN")
btn_keys = KeyboardButton(text="📖 Мои ключи")
btn_help = KeyboardButton(text="ℹ️ Помощь")
btn_support = KeyboardButton(text="💬 Поддержка")

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [btn_buy],
        [btn_keys],
        [btn_help, btn_support]
    ],
    resize_keyboard=True
)

# --- Клавиатура для оплаты ---
def get_payment_kb(payment_url: str, order_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату",
                                  callback_data=f"check_payment:{order_id}")]
        ]
    )