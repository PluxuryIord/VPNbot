from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings


def get_main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="menu:buy")],
            [InlineKeyboardButton(text="📖 Мои ключи", callback_data="menu:keys")],
            [
                InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="menu:instruction"),
                InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support"),
            ],
        ]
    )


def get_country_selection_kb() -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для выбора страны."""
    buttons = []
    countries = sorted(list(set(server.country for server in settings.XUI_SERVERS)))
    for country in countries:
        flag = ""
        premium = ""
        if country == "Финляндия":
            flag = "🇫🇮"
            premium = "⚡"
        elif country == "Германия":
            flag = "🇩🇪"
        elif country == "Нидерланды":
            flag = "🇳🇱"
        buttons.append(
            InlineKeyboardButton(text=f"{flag} {country} {premium}", callback_data=f"select_country:{country}")
        )

    keyboard = []
    for i in range(0, len(buttons), 2):
        keyboard.append(buttons[i:i + 2])

    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_instruction_platforms_kb() -> InlineKeyboardMarkup:
    """Клавиатура для выбора ОС в разделе Инструкции"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 Android", callback_data="instruction:android"),
                InlineKeyboardButton(text="🍎 iPhone", callback_data="instruction:ios"),
            ],
            [
                InlineKeyboardButton(text="💻 Windows", callback_data="instruction:windows"),
                InlineKeyboardButton(text="🍏 Mac", callback_data="instruction:macos"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]
    )


def get_back_to_instructions_kb() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой Назад к выбору ОС"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к выбору ОС", callback_data="menu:instruction")]
        ]
    )


def get_payment_kb(payment_url: str, order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_payment:{order_id}")],
            [InlineKeyboardButton(text="⬅️ Отмена (к странам)", callback_data="menu:buy")]
        ]
    )
