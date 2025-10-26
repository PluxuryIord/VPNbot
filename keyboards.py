import datetime
import math

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
            premium = "🔹"
        elif country == "Нидерланды":
            flag = "🇳🇱"
            premium = "🔹"
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
            [InlineKeyboardButton(
                text="⚙️ Настройка исключений",
                url="https://teletype.in/@coid_siemens/3PPKfFAHxhw"
            )],
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


def get_my_keys_kb(keys_on_page: list, total_keys: int, page: int = 0, page_size: int = 5) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру для 'Мои ключи' с пагинацией.
    """
    keyboard = []

    # Добавляем кнопки для каждого ключа на странице
    if keys_on_page:
        for key in keys_on_page:
            status_icon = "✅" if key.expires_at > datetime.datetime.now() else "❌"  # Нужен импорт datetime вверху файла
            # ❗️ Добавим callback_data для детального просмотра (пока заглушка)
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_icon} Ключ (до {key.expires_at.strftime('%d.%m.%Y')})",
                    callback_data=f"key_details:{key.id}:{page}"
                    # callback_data="key_details"  # Временно
                )
            ])

    # --- Кнопки пагинации ---
    total_pages = math.ceil(total_keys / page_size)
    nav_row = []
    # Кнопка "Назад"
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mykeys_page:{page - 1}")
        )
    # Индикатор страницы
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="ignore")  # Кнопка без действия
        )
    # Кнопка "Вперед"
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"mykeys_page:{page + 1}")
        )

    if nav_row:
        keyboard.append(nav_row)  # Добавляем ряд с кнопками навигации

    # Кнопка "Главное меню"
    keyboard.append([InlineKeyboardButton(text="📋 Главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_key_details_kb(key_id: int, current_page: int) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра ключа."""
    keyboard = [
        [
            InlineKeyboardButton(text="🔑 Скопировать ключ", callback_data=f"key_copy:{key_id}:{current_page}"),
            InlineKeyboardButton(text="🔄 Продлить", callback_data=f"key_renew:{key_id}:{current_page}")
        ],
        # Обновляем callback_data кнопки Назад
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"mykeys_page:{current_page}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
