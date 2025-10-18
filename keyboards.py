# keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Главное меню (ИНЛАЙН) ---

def get_main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="menu:buy")],
            [InlineKeyboardButton(text="📖 Мои ключи", callback_data="menu:keys")],
            [
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
                InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support"),
            ],
        ]
    )

# --- Клавиатура для оплаты ---

def get_payment_kb(payment_url: str, order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_payment:{order_id}")],
        ]
    )