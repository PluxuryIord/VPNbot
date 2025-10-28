import datetime
import math

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings


# def get_main_menu_kb() -> InlineKeyboardMarkup:
#     return InlineKeyboardMarkup(
#         inline_keyboard=[
#             [InlineKeyboardButton(text="🎁 Пробный период (24ч)", callback_data="trial:get")],
#             [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="menu:buy")],
#             [InlineKeyboardButton(text="📖 Мои ключи", callback_data="menu:keys")],
#             [
#                 InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="menu:instruction"),
#                 InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support"),
#             ],
#         ]
#     )


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
            InlineKeyboardButton(text=f"{premium} {country} {flag}", callback_data=f"select_country:{country}")
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
                InlineKeyboardButton(text="📱 Android", url="https://teletype.in/@coid_siemens/0BKy1e3yrgt"),
                InlineKeyboardButton(text="🍎 iPhone", url="https://teletype.in/@coid_siemens/3vXPZr2S0Kn"),
            ],
            [
                InlineKeyboardButton(text="💻 Windows", url="https://teletype.in/@coid_siemens/JnYNn8TyoDG"),
                InlineKeyboardButton(text="🍏 Mac", url="https://teletype.in/@coid_siemens/UVA_Tk0VyQK"),
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
        ]
    )


def get_payment_method_kb(order_id: int, country: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Картой / ЮMoney / СБП", callback_data=f"pay_method:default:{order_id}")],
            # [InlineKeyboardButton(text="⚡ Система Быстрых Платежей (СБП)", callback_data=f"pay_method:sbp:{order_id}")],
            # Кнопка отмены, чтобы вернуться к выбору тарифа
            [InlineKeyboardButton(text="⬅️ Назад к тарифам", callback_data=f"select_country:{country}")]
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


def get_support_kb() -> InlineKeyboardMarkup:
    """Клавиатура для раздела Поддержка."""
    keyboard = [
        # Кнопка-ссылка на оферту
        [InlineKeyboardButton(
            text="📜 Публичная оферта",
            url="https://telegra.ph/PUBLICHNAYA-OFERTA-o-zaklyuchenii-dogovora-ob-okazanii-uslug-10-27-2"
        )],
        # Кнопка "Назад"
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню админа."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="menu:main")]
        ]
    )


def get_back_to_admin_kb() -> InlineKeyboardMarkup:
    """Кнопка 'Назад' для админ-панели."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в админ-меню", callback_data="admin:main")]
        ]
    )


def get_main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    """
    Генерирует главное меню.
    Для админов добавляет кнопку "Админ-панель".
    """
    keyboard = [
        [InlineKeyboardButton(text="🎁 Пробный период (24ч)", callback_data="trial:get")],
        [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="menu:buy")],
        [InlineKeyboardButton(text="📖 Мои ключи", callback_data="menu:keys")],
        [
            InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="menu:instruction"),
            InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support"),
        ],
    ]

    if user_id in settings.get_admin_ids:
        keyboard.insert(1, [
            InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin:main")
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_stats_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Клавиатура пагинации для статистики админа (по 5 элементов).
    """
    nav_row = []

    # 1. Кнопка "Назад"
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:stats_page:{page - 1}")
        )

    # 2. Индикатор страницы
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="ignore")
        )

    # 3. Кнопка "Вперед"
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin:stats_page:{page + 1}")
        )

    keyboard = []
    if nav_row:
        keyboard.append(nav_row)

    # 4. Кнопка "Назад в админ-меню"
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в админ-меню", callback_data="admin:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_broadcast_confirmation_kb() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения рассылки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, отправить", callback_data="broadcast:confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel")
            ]
        ]
    )
