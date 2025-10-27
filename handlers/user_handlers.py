import datetime
import logging
import math

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart
from aiogram.exceptions import AiogramError
from config import settings
from utils import issue_key_to_user, issue_trial_key

from keyboards import get_main_menu_kb, get_payment_kb, get_instruction_platforms_kb, get_back_to_instructions_kb, \
    get_country_selection_kb, get_my_keys_kb, get_key_details_kb, get_support_kb, get_payment_method_kb
from database import db_commands as db
from payments import create_yookassa_payment, check_yookassa_payment
from utils import generate_vless_key, handle_payment_logic

log = logging.getLogger(__name__)
router = Router()

TEXT_INSTRUCTION_MENU = "ℹ️ **Инструкция**\n\nВыберите вашу операционную систему:"
TEXT_ANDROID = """
📱 **Инструкция для Android (V2Box):**

1. Скачайте приложение V2Box из [Google Play](https://play.google.com/store/apps/details?id=com.v2box.v2box).
2. Скопируйте ключ VLESS, который выдал бот.
3. Откройте V2Box и нажмите кнопку "+" внизу справа.
4. Выберите "Import config from Clipboard".
5. Нажмите на импортированный профиль для выбора.
6. Нажмите большую круглую кнопку для подключения.
"""
TEXT_IOS = """
🍎 **Инструкция для iPhone/iPad (V2Box):**

1. Скачайте приложение V2Box из [App Store](https://apps.apple.com/us/app/v2box-v2ray-client/id6446814670).
2. Скопируйте ключ VLESS.
3. Откройте V2Box -> вкладка "Configs".
4. Нажмите "+" вверху справа.
5. Выберите "Import from clipboard".
6. Перейдите на вкладку "Home" -> "Connect".
"""
TEXT_WINDOWS = """
💻 **Инструкция для Windows (v2rayN):**

1. Скачайте v2rayN-Core с [GitHub](https://github.com/2dust/v2rayN/releases). (Ищите `v2rayN-With-Core.zip`).
2. Распакуйте архив, запустите `v2rayN.exe`.
3. Скопируйте ключ VLESS.
4. В v2rayN нажмите `Ctrl+V`.
5. Ключ появится в списке. ПКМ -> "Установить как активный сервер".
6. В трее (возле часов) иконка v2rayN -> ПКМ -> "Системный прокси" -> "Установить как системный прокси".
7. Там же: "Режим маршрутизации" -> "Обход LAN и континентального Китая".
"""
TEXT_MACOS = """
🍏 **Инструкция для macOS (V2RayU):**

1. Скачайте V2RayU с [GitHub](https://github.com/yanue/V2rayU/releases). (Ищите `.dmg`).
2. Установите приложение.
3. Скопируйте ключ VLESS.
4. Иконка V2RayU в строке меню -> "Import" -> "Import from pasteboard".
5. Выберите сервер в меню.
6. Нажмите "Turn V2ray-core On".
"""
TEXT_SUPPORT = "По всем вопросам пишите @NjordVPN_Support"


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик /start"""
    await db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.full_name
    )
    await message.answer(
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        f"Наш основной канал 👉 https://t.me/NjordVPN"
        "Я бот для продажи VPN-ключей. "
        "Выбери действие в меню:",
        reply_markup=get_main_menu_kb(user_id=message.from_user.id)
    )


# === Инлайн-навигация ===

@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery):
    """Главное меню (инлайн)."""
    await callback.message.edit_text(
        "👋 Привет!\n\n"
        "Наш основной канал 👉 https://t.me/NjordVPN"
        "Я бот для продажи VPN-ключей. "
        "Выбери действие в меню:",
        reply_markup=get_main_menu_kb(user_id=callback.from_user.id)
    )


@router.callback_query(F.data == "menu:buy")
async def menu_buy_select_country(callback: CallbackQuery):
    """Показывает выбор страны."""
    await callback.message.edit_text(
        "🌍 Выберите страну подключения:\n"
        "⚡ Премиум локации с повышенной скоростью\n"
        "🔹 Стандартные локации",
        reply_markup=get_country_selection_kb()  # Новая клавиатура
    )
    await callback.answer()


@router.callback_query(F.data == "trial:get")
async def process_trial_get(callback: CallbackQuery, bot: Bot):
    """Обрабатывает нажатие на кнопку 'Пробный период'."""
    user_id = callback.from_user.id
    log.info(f"Пользователь {user_id} запросил пробный период.")
    await callback.answer("⏳ Проверяю возможность выдачи...")  # Ответ-заглушка

    success, result_data = await issue_trial_key(bot, user_id)

    # --- Если УСПЕШНО выдан ключ ---
    if success:
        vless_string = result_data
        expires_at = datetime.datetime.now() + datetime.timedelta(days=1)
        success_text = (
            f"✅ **Пробный ключ на 24 часа активирован!**\n\n"
            f"Сервер: **Финляндия** 🇫🇮\n\n"
            "Ваш ключ доступа:\n"
            f"```\n{vless_string}\n```\n\n"
            f"Действителен до: **{expires_at.strftime('%Y-%m-%d %H:%M')}**\n\n"
            "Скопируйте ключ и добавьте его в приложение. Инструкцию можно найти в главном меню."
        )
        # Отправляем ключ НОВЫМ сообщением (не редактируем меню)
        await callback.message.answer(
            success_text,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        # Можно опционально отредактировать исходное меню, убрав кнопку триала, но проще оставить как есть
        # await callback.message.edit_reply_markup(reply_markup=get_main_menu_kb()) # Пример

    # --- Если НЕ УДАЛОСЬ (уже получал или ошибка) ---
    else:
        error_message = result_data  # Функция вернула текст ошибки
        if error_message == "Вы уже активировали пробный период.":
            # Отправляем сообщение в чат вместо alert'а
            await callback.message.answer(
                "⏳ **Вы уже использовали пробный период.**\n\n"
                "Чтобы продолжить пользоваться VPN, пожалуйста, выберите и оплатите один из наших тарифов в главном меню (кнопка \"🛒 Купить VPN\").",
                parse_mode="Markdown"
            )
            await callback.answer()  # Просто закрываем часики
        else:
            # Для других ошибок показываем alert
            await callback.answer(error_message, show_alert=True)


@router.callback_query(F.data.startswith("select_country:"))
async def select_country_show_tariffs(callback: CallbackQuery):
    """Показывает тарифы после выбора страны."""
    country = callback.data.split(":")[1]
    log.info(f"User {callback.from_user.id} selected country: {country}")
    products = await db.get_products(country=country)  # Передаем страну

    if not products:
        await callback.message.edit_text(
            f"К сожалению, сейчас нет доступных тарифов для **{country}**.",
            reply_markup=get_country_selection_kb()
        )
        await callback.answer()
        return

    text = f"Тарифы для **{country}**:\n\n"
    buttons = []
    for product in products:
        text += f"🔹 **{product.name}** - {product.price} руб.\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"{product.name} ({product.price} руб.)",
                callback_data=f"buy_product:{product.id}:{country}"  # ID теперь уникален
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к странам", callback_data="menu:buy")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "menu:keys")
async def menu_keys_show_first_page(callback: CallbackQuery):
    """Показывает ПЕРВУЮ страницу ключей пользователя."""
    await callback.answer()  # Снимаем часики

    user_id = callback.from_user.id
    page = 0  # Всегда начинаем с первой страницы
    page_size = 5

    total_keys = await db.count_user_keys(user_id)
    if total_keys == 0:
        await callback.message.edit_text(
            "У вас пока нет купленных ключей.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📋 Главное меню", callback_data="menu:main")]]
            ),
        )
        return

    keys_on_page = await db.get_user_keys(user_id, page=page, page_size=page_size)
    kb = get_my_keys_kb(keys_on_page, total_keys, page=page, page_size=page_size)

    total_pages = math.ceil(total_keys / page_size)
    text = "🔑 **Ваши ключи:**"
    if total_pages > 1:
        text += f"\n\n📄 Страница {page + 1} из {total_pages}"

    # Редактируем сообщение, показывая ключи и пагинацию
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("mykeys_page:"))
async def menu_keys_paginate(callback: CallbackQuery):
    """Обрабатывает нажатия на кнопки пагинации 'Назад'/'Вперед'."""
    try:
        page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        log.warning(f"Некорректный callback_data для пагинации ключей: {callback.data}")
        await callback.answer("Ошибка навигации.", show_alert=True)
        return

    await callback.answer()  # Снимаем часики

    user_id = callback.from_user.id
    page_size = 5

    total_keys = await db.count_user_keys(user_id)
    keys_on_page = await db.get_user_keys(user_id, page=page, page_size=page_size)
    kb = get_my_keys_kb(keys_on_page, total_keys, page=page, page_size=page_size)

    total_pages = math.ceil(total_keys / page_size)
    text = "🔑 **Ваши ключи:**"
    if total_pages > 1:
        text += f"\n\n📄 Страница {page + 1} из {total_pages}"

    # Редактируем сообщение с новой страницей
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except AiogramError as e:
        if "message is not modified" in str(e).lower():
            # Если это ошибка "сообщение не изменено", просто игнорируем
            pass
        else:
            # Если это другая ошибка, логируем ее
            log.error(f"Ошибка при редактировании сообщения пагинации: {e}")
            await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data.startswith("key_details:"))
async def menu_key_details(callback: CallbackQuery):
    """Показывает детали выбранного ключа."""
    try:
        # Парсим ID ключа и номер страницы
        _, key_id_str, page_str = callback.data.split(":")
        key_id = int(key_id_str)
        current_page = int(page_str)
    except (IndexError, ValueError):
        log.warning(f"Некорректный callback_data для деталей ключа: {callback.data}")
        await callback.answer("Ошибка получения ключа.", show_alert=True)
        return

    await callback.answer()  # Снимаем часики

    # Получаем ключ из БД по ID
    key = await db.get_key_by_id(key_id)

    if not key or key.user_id != callback.from_user.id:  # Проверяем, что ключ принадлежит пользователю
        await callback.answer("Ключ не найден.", show_alert=True)
        # Вернем пользователя к списку ключей (на первую страницу)
        # TODO: Лучше возвращать на current_page, но для этого menu_keys_show_first_page нужно переделать
        await menu_keys_show_first_page(callback)
        return

    # Формируем текст с деталями (без изменений)
    now = datetime.datetime.now()
    if key.expires_at > now:
        status = "✅ *Активен*";
        remaining = key.expires_at - now;
        time_left = f"{remaining.days} дн. {remaining.seconds // 3600} ч."
    else:
        status = "❌ *Истек*";
        time_left = "0"

    text = (
        f"🔑 **Детали ключа** ({status})\n\n"
        f"Сервер: `{key.vless_key.split('@')[1].split(':')[0]}`\n"
        f"Порт: `{key.vless_key.split(':')[2].split('?')[0]}`\n"
        f"Истекает: `{key.expires_at.strftime('%Y-%m-%d %H:%M')}`\n"
        f"Осталось: {time_left}\n\n"
        "Нажмите кнопки ниже для действий."
    )

    # Передаем номер страницы в клавиатуру
    kb = get_key_details_kb(key_id, current_page)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except AiogramError:
        pass


@router.callback_query(F.data.startswith("key_copy:"))
async def menu_key_copy(callback: CallbackQuery):
    """Отправляет ключ пользователю для копирования."""
    try:
        # Парсим ID ключа (страницу можно игнорировать)
        _, key_id_str, _ = callback.data.split(":")
        key_id = int(key_id_str)
    except (IndexError, ValueError):
        log.warning(f"Некорректный callback_data для копирования ключа: {callback.data}")
        await callback.answer("Ошибка получения ключа.", show_alert=True)
        return

    # Получаем ключ по ID
    key = await db.get_key_by_id(key_id)

    if not key or key.user_id != callback.from_user.id:
        await callback.answer("Ключ не найден.", show_alert=True)
        return

    try:
        await callback.message.answer(
            f"Ваш ключ (нажмите для копирования):\n\n<code>{key.vless_key}</code>",
            parse_mode="HTML"
        )
        await callback.answer("Ключ отправлен в чат!", show_alert=True)
    except Exception as e:
        log.error(f"Ошибка при отправке ключа {key_id} пользователю {callback.from_user.id}: {e}")
        await callback.answer("Не удалось отправить ключ.", show_alert=True)


@router.callback_query(F.data.startswith("key_renew:"))
async def menu_key_renew(callback: CallbackQuery, bot: Bot):
    """Начинает процесс продления ключа."""
    try:
        _, key_id_str, page_str = callback.data.split(":")
        key_id = int(key_id_str)
        current_page = int(page_str)  # Запоминаем страницу для возврата
    except (IndexError, ValueError):
        log.warning(f"Некорректный callback_data для продления ключа: {callback.data}")
        await callback.answer("Ошибка продления.", show_alert=True)
        return

    await callback.answer("⏳ Готовлю счет для продления...")

    # 1. Получаем ключ и связанный заказ/продукт
    key = await db.get_key_by_id(key_id)
    if not key or key.user_id != callback.from_user.id:
        await callback.answer("Ключ не найден.", show_alert=True)
        return

    original_order = await db.get_order_by_id(key.order_id)
    if not original_order:
        log.error(f"Не найден оригинальный заказ {key.order_id} для ключа {key_id}")
        await callback.answer("Ошибка: Не найден оригинальный заказ.", show_alert=True)
        return

    product = await db.get_product_by_id(original_order.product_id)
    if not product:
        log.error(f"Не найден продукт {original_order.product_id} для заказа {key.order_id}")
        await callback.answer("Ошибка: Не найден тариф для продления.", show_alert=True)
        return

    # 2. Создаем НОВЫЙ заказ (для отслеживания платежа за продление)
    # Используем цену и длительность оригинального продукта
    try:
        renewal_order_id = await db.create_order(
            user_id=callback.from_user.id,
            product_id=product.id,
            amount=product.price
        )
    except Exception as e:
        log.error(f"Ошибка создания заказа на продление для ключа {key_id}: {e}")
        await callback.answer("Не удалось создать заказ на продление.", show_alert=True)
        return

    # 3. Создаем счет в ЮKassa, передаем ID ключа и ID нового заказа в metadata
    payment_metadata = {
        "renewal_key_id": str(key_id),  # ID ключа, который продлеваем
        "renewal_order_id": str(renewal_order_id)  # ID нового заказа
    }
    payment_url, payment_id = await create_yookassa_payment(
        amount=product.price,
        description=f"Продление ключа '{product.name}' (Заказ #{renewal_order_id})",
        order_id=renewal_order_id,  # Передаем ID НОВОГО заказа
        metadata=payment_metadata
    )

    # 4. Обновляем НОВЫЙ заказ, добавляя payment_id
    await db.update_order_status(renewal_order_id, payment_id, status='pending')

    # 5. Отправляем ссылку на оплату
    kb = get_payment_kb(payment_url, renewal_order_id)  # Используем ID НОВОГО заказа для кнопки "Проверить"
    # Добавляем кнопку "Назад к деталям ключа"
    kb.inline_keyboard.append(
        [InlineKeyboardButton(text="⬅️ Назад к деталям", callback_data=f"key_details:{key_id}:{current_page}")]
    )

    await callback.message.edit_text(
        f"Вы продлеваете: **{product.name}**\n"
        f"Срок: +{product.duration_days} дней\n"
        f"Сумма к оплате: **{product.price} руб.**\n\n"
        "Нажмите кнопку ниже, чтобы перейти к оплате:",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu:help")
async def menu_static(callback: CallbackQuery):
    """Статичные страницы (инлайн)."""
    if callback.data == "menu:help":
        text = "Инструкция по подключению V2Box:\n1. ...\n2. ..."
    else:
        text = "По всем вопросам пишите @NjordVPN_Support"

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]]
        ),
    )


@router.callback_query(F.data == "menu:instruction")
async def menu_instruction_platforms(callback: CallbackQuery):
    """Показывает выбор ОС для инструкции."""
    await callback.message.edit_text(
        TEXT_INSTRUCTION_MENU,
        reply_markup=get_instruction_platforms_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("instruction:"))
async def menu_instruction_detail(callback: CallbackQuery):
    """Показывает инструкцию для выбранной ОС."""
    platform = callback.data.split(":")[1]
    text = "Инструкция не найдена."
    if platform == "android":
        text = TEXT_ANDROID
    elif platform == "ios":
        text = TEXT_IOS
    elif platform == "windows":
        text = TEXT_WINDOWS
    elif platform == "macos":
        text = TEXT_MACOS

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_instructions_kb(),  # Новая клавиатура
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.callback_query(F.data == "menu:support")
async def menu_support(callback: CallbackQuery):
    """Показывает контакт поддержки и ссылку на оферту."""
    log.info("Вошли в обработчик menu_support")  # <-- Лог 1
    try:
        kb = get_support_kb()
        kb_json = kb.model_dump_json(indent=2)  # Преобразуем в JSON для лога
        log.info(f"Сгенерирована клавиатура:\n{kb_json}")  # <-- Лог 2

        await callback.message.edit_text(
            TEXT_SUPPORT,
            reply_markup=kb
        )
        log.info("Вызов edit_text успешно завершен.")  # <-- Лог 3
        await callback.answer()
        log.info("Вызов callback.answer() успешно завершен.")  # <-- Лог 4
    except AiogramError as e:
        # Ловим общие ошибки aiogram
        log.error(f"AiogramError в menu_support: {e}")
        await callback.answer("Произошла ошибка при обновлении меню.", show_alert=True)
    except Exception as e:
        # Ловим любые другие ошибки
        log.exception("Непредвиденная ошибка в menu_support:")  # Используем exception для полного трейсбека
        await callback.answer("Произошла критическая ошибка.", show_alert=True)


@router.callback_query(F.data.startswith("buy_product:"))
async def process_buy_callback(callback: CallbackQuery, bot: Bot):
    """
    Обработка нажатия на кнопку тарифа.
    Шаг 1: Создает заказ (pending) и показывает выбор способа оплаты.
    """
    await callback.answer(cache_time=1)
    try:
        _, product_id_str, country = callback.data.split(":")
        product_id = int(product_id_str)
    except ValueError:
        log.error(f"Invalid callback data format: {callback.data}")
        await callback.answer("Произошла ошибка. Попробуйте снова.", show_alert=True)
        return

    log.info(f"User {callback.from_user.id} initiated purchase for product {product_id} in country {country}")

    product = await db.get_product_by_id(product_id)
    if not product:
        await callback.answer("Тариф не найден. Попробуйте снова.", show_alert=True)
        return

    order_id = await db.create_order(
        user_id=callback.from_user.id,
        product_id=product_id,
        amount=product.price
    )

    # 2. Показываем ВЫБОР СПОСОБА ОПЛАТЫ
    kb = get_payment_method_kb(order_id, country)

    try:
        # Редактируем текущее сообщение
        await callback.message.edit_text(
            f"Вы выбрали: **{product.name} ({country})**\n"
            f"Сумма к оплате: **{product.price} руб.**\n\n"
            "Теперь выберите удобный способ оплаты:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        log.error(f"Ошибка при показе выбора способа оплаты: {e}")
        await callback.answer("Не удалось обновить меню. Попробуйте снова.")


@router.callback_query(F.data.startswith("pay_method:"))
async def process_payment_method(callback: CallbackQuery, bot: Bot):
    """
    Обработка нажатия на кнопку способа оплаты (Карта или СБП).
    Шаг 2: Создает ссылку на оплату и отправляет ее НОВЫМ сообщением.
    """
    await callback.answer("⏳ Создаю ссылку на оплату...")

    try:
        _, method, order_id_str = callback.data.split(":")
        order_id = int(order_id_str)
    except ValueError:
        log.error(f"Invalid pay_method callback data: {callback.data}")
        await callback.answer("Ошибка! Не удалось обработать способ оплаты.", show_alert=True)
        return

    # 1. Получаем заказ из БД
    order = await db.get_order_by_id(order_id)
    if not order or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден!", show_alert=True)
        return

    # 2. Не даем создавать новую ссылку, если платеж уже в процессе
    # (кроме 'failed', но для простоты блокируем все, кроме 'pending')
    if order.status != 'pending':
        await callback.answer("Платеж по этому заказу уже создан или обработан.", show_alert=True)
        return

    product = await db.get_product_by_id(order.product_id)
    if not product:
        await callback.answer("Ошибка: Тариф не найден для этого заказа.", show_alert=True)
        return

    # 3. Устанавливаем способ оплаты в зависимости от кнопки
    payment_method_data = None
    description_suffix = " (Карта/ЮMoney)"
    if method == "sbp":
        # Это заставит ЮKassa показать ТОЛЬКО СБП
        payment_method_data = {"type": "sbp"}
        description_suffix = " (СБП)"

    # 4. Создаем счет в ЮKassa
    try:
        country = product.country
        if not country:  # На случай, если у тарифа NULL country (общий)
            # Пытаемся вытащить страну из metadata заказа, если она там есть
            # (В нашем коде ее там нет, берем из продукта - product.country)
            # Если и там нет, ставим "Unknown"
            country = "Unknown"

        metadata = {"country": country}

        payment_url, payment_id = await create_yookassa_payment(
            amount=product.price,
            description=f"Оплата '{product.name}' ({country}){description_suffix} (Заказ #{order_id})",
            order_id=order_id,
            metadata=metadata,
            payment_method_data=payment_method_data  # ⬅️ ГЛАВНОЕ ИЗМЕНЕНИЕ
        )
    except Exception as e:
        log.error(f"Ошибка создания счета ЮKassa (метод {method}) для заказа {order_id}: {e}")
        await callback.answer("Не удалось создать счет в ЮKassa. Попробуйте другой способ.", show_alert=True)
        return

    # 5. Обновляем заказ, добавляя payment_id
    await db.update_order_status(order_id, payment_id, status='pending')

    # 6. Отправляем ссылку на оплату НОВЫМ СООБЩЕНИЕМ
    # (Используем get_payment_kb из keyboards.py) [cite_start][cite: 105]
    kb = get_payment_kb(payment_url, order_id)

    try:
        # Отправляем НОВОЕ сообщение с оплатой
        await callback.message.answer(
            f"Ваша ссылка на оплату (Счет: {description_suffix}):\n"
            f"Тариф: **{product.name} ({country})**\n"
            f"Сумма: **{product.price} руб.**\n\n"
            "Нажмите кнопку ниже, чтобы перейти к оплате:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        # И удаляем сообщение с выбором способа
        await callback.message.delete()
    except Exception as e:
        log.error(f"Ошибка при отправке/удалении сообщения об оплате: {e}")


@router.callback_query(F.data.startswith("check_payment:"))
async def process_check_payment(callback: CallbackQuery, bot: Bot):
    """
    Обработка нажатия на кнопку "Проверить оплату".
    Теперь использует универсальную функцию handle_payment_logic.
    """
    order_id = int(callback.data.split(":")[1])

    order = await db.get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден!", show_alert=True)
        return

    # 1. Проверяем, может пользователь нажал кнопку снова ПОСЛЕ успешной оплаты
    if order.status == 'paid':
        await callback.answer("Этот заказ уже оплачен. Ключ должен быть у вас в сообщениях.", show_alert=True)
        return

    if not order.payment_id:
        await callback.answer("Ошибка: ID платежа не найден для этого заказа.", show_alert=True)
        return

    # 2. Запрашиваем статус в ЮKassa [cite: 177]
    payment_info = await check_yookassa_payment(order.payment_id)
    if not payment_info:
        await callback.answer("Не удалось проверить статус платежа в ЮKassa.", show_alert=True)
        return

    # --- Платеж УСПЕШЕН ---
    if payment_info.status == 'succeeded':
        await callback.answer("✅ Оплата найдена! Обрабатываю...")

        # 3. Обновляем статус в БД (на случай, если вебхук еще не дошел)
        await db.update_order_status(order_id, order.payment_id, status='paid')

        # 4. Вызываем ту же универсальную функцию, что и вебхук
        success, message_text = await handle_payment_logic(bot, order, payment_info)

        # 5. РЕДАКТИРУЕМ текущее сообщение, показывая результат
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Главное меню", callback_data="menu:main")]
        ])
        if success:
            # Добавляем кнопку "Мои ключи" при успехе
            kb.inline_keyboard.insert(0, [InlineKeyboardButton(text="📖 Мои ключи", callback_data="menu:keys")])

        await callback.message.edit_text(
            message_text,
            reply_markup=kb,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    # --- Платеж НЕ УСПЕШЕН ---
    elif payment_info.status == 'pending':
        await callback.answer("Платеж еще не поступил. Попробуйте через минуту.", show_alert=True)

    elif payment_info.status in ('canceled', 'waiting_for_capture'):
        await callback.answer(f"Платеж отменен или ожидает подтверждения (статус: {payment_info.status}).",
                              show_alert=True)
        await db.update_order_status(order_id, order.payment_id, status='failed')

    else:
        log.warning(f"Неожиданный статус платежа {payment_info.id}: {payment_info.status}")
        await callback.answer(f"Неизвестный статус платежа: {payment_info.status}", show_alert=True)