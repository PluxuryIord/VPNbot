import datetime
import math

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings


def _get_flag_for_country(country_name: str) -> str:
    """
    Вспомогательная функция для получения флага страны.
    """
    if country_name == "Финляндия":
        return "🇫🇮"
    if country_name == "Германия":
        return "🇩🇪"
    if country_name == "Нидерланды":
        return "🇳🇱"
    return "🏳️"  # Флаг по умолчанию


def get_main_menu_kb(user_id: int, has_keys: bool = False) -> InlineKeyboardMarkup:
    """Главное меню. Кнопка 'Мои ключи' показывается только если has_keys=True."""
    keyboard = [
        [InlineKeyboardButton(text="🎁 Пробный период (24ч)", callback_data="trial:get")],
        [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="menu:buy")],
    ]

    if has_keys:
         keyboard.append([InlineKeyboardButton(text="📖 Мои ключи", callback_data="menu:keys")])

    keyboard.append([
        InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="menu:instruction"),
        InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support"),
    ])

    if user_id in settings.get_admin_ids:
        keyboard.insert(1, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_trial_discount_kb(key_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для спецпредложения за 2 часа до конца триала."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Продлить за 119₽", callback_data=f"special_offer:119:{key_id}")]
    ])


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
                url="https://teletype.in/@coid_siemens/3PPKfFAHxhw"  #
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


def get_payment_kb(payment_url: str, order_id: int, back_callback_data: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для ссылки на оплату (с кастомной кнопкой "Назад")
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_payment:{order_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback_data)]
        ]
    )


def get_payment_method_kb(order_id: int, country: str) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора способа оплаты (ЮKassa / Crypto).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Картой / ЮMoney / СБП", callback_data=f"pay_method:yookassa:{order_id}")],
            [InlineKeyboardButton(text="💎 Криптовалютой (USDT)", callback_data=f"pay_method:crypto:{order_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к тарифам", callback_data=f"select_country:{country}")]
        ]
    )


def get_my_keys_kb(keys_on_page: list, total_keys: int, page: int = 0, page_size: int = 5) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру для 'Мои ключи' с пагинацией.
    """
    keyboard = []
    server_ip_to_country = {s.vless_server: s.country for s in settings.XUI_SERVERS}
    if keys_on_page:
        now = datetime.datetime.now()
        for key in keys_on_page:

            country = "Unknown"
            flag = "🏳️"
            try:
                server_ip = key.vless_key.split('@')[1].split(':')[0]
                country = server_ip_to_country.get(server_ip, "")  #
            except Exception:
                pass

            flag = _get_flag_for_country(country)
            if key.expires_at > now:
                status_icon = "✅"
                remaining = key.expires_at - now
                days_left = remaining.days

                if days_left > 0:
                    time_left = f"(Осталось {days_left} д.)"
                else:
                    hours_left = remaining.seconds // 3600
                    if hours_left > 0:
                        time_left = f"(Осталось {hours_left} ч.)"
                    else:
                        time_left = "(Меньше часа)"
            else:
                status_icon = "❌"
                time_left = f"(Истек {key.expires_at.strftime('%d.%m')})"

            btn_text = f"{status_icon} Ключ {country} {flag} {time_left}"

            keyboard.append([
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"key_details:{key.id}:{page}"
                )
            ])

    total_pages = math.ceil(total_keys / page_size)
    nav_row = []

    placeholder_btn = InlineKeyboardButton(text=" ", callback_data="ignore")

    # 1. Кнопка "Назад"
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mykeys_page:{page - 1}")
        )
    else:
        nav_row.append(placeholder_btn)  #

    # 2. Индикатор страницы
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="ignore")
        )
    else:
        nav_row.append(InlineKeyboardButton(text="1/1", callback_data="ignore"))

    # 3. Кнопка "Вперед"
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"mykeys_page:{page + 1}")
        )
    else:
        nav_row.append(placeholder_btn)

    if total_pages > 1:
        keyboard.append(nav_row)

    #
    keyboard.append([InlineKeyboardButton(text="📋 Главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_key_details_kb(key_id: int, current_page: int) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра ключа."""
    keyboard = [
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mykeys_page:{current_page}"),
            InlineKeyboardButton(text="🔄 Продлить", callback_data=f"key_renew:{key_id}:{current_page}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_support_kb() -> InlineKeyboardMarkup:
    """Клавиатура для раздела Поддержка."""
    keyboard = [
        [InlineKeyboardButton(
            text="📜 Публичная оферта",
            url="https://telegra.ph/PUBLICHNAYA-OFERTA-o-zaklyuchenii-dogovora-ob-okazanii-uslug-10-27-2"
        )],
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


def get_admin_stats_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Клавиатура пагинации для статистики админа (по 5 элементов).
    """
    nav_row = []

    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:stats_page:{page - 1}")
        )

    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="ignore")
        )

    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin:stats_page:{page + 1}")
        )

    keyboard = []
    if nav_row:
        keyboard.append(nav_row)

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


def get_renewal_kb(key_id: int) -> InlineKeyboardMarkup:
    """
    Создает кнопку "Продлить" для уведомлений об истечении.
    Key_id: ID ключа (Keys.id), НЕ заказа.
    Page: 0 (
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продлить сейчас", callback_data=f"key_renew:{key_id}:0")]
    ])


def get_renewal_payment_method_kb(order_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора способа оплаты (ЮKassa / Crypto)
    БЕЗ кнопки "Назад к тарифам" (для меню продления).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Картой / ЮMoney / СБП", callback_data=f"pay_method:yookassa:{order_id}")],
            [InlineKeyboardButton(text="💎 Криптовалютой (USDT)", callback_data=f"pay_method:crypto:{order_id}")]
        ]
    )


def get_payment_success_kb(renewal_key_id: int | None = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для сообщения об успешной оплате (которое приходит от вебхука).
    Включает кнопку "Главное меню" и, если это продление, "К деталям ключа".
    """
    keyboard = []

    if renewal_key_id:
        keyboard.append([
            InlineKeyboardButton(text="⬅️ К деталям ключа", callback_data=f"key_details:{renewal_key_id}:0")
        ])

    keyboard.append([InlineKeyboardButton(text="📋 Главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_trial_already_used_kb() -> InlineKeyboardMarkup:
    """
    Клавиатура для сообщения "Вы уже получали пробный ключ".
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="menu:buy")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]
        ]
    )
