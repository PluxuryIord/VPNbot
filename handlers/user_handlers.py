import datetime
import logging
import math

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart
from aiogram.exceptions import AiogramError
from config import settings
from utils import issue_key_to_user

from keyboards import get_main_menu_kb, get_payment_kb, get_instruction_platforms_kb, get_back_to_instructions_kb, \
    get_country_selection_kb, get_my_keys_kb
from database import db_commands as db
from payments import create_yookassa_payment, check_yookassa_payment
from utils import generate_vless_key

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
TEXT_SUPPORT = "По всем вопросам пишите @"


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
        "Я бот для продажи VPN-ключей. "
        "Выбери действие в меню:",
        reply_markup=get_main_menu_kb()
    )


# === Инлайн-навигация ===

@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery):
    """Главное меню (инлайн)."""
    await callback.message.edit_text(
        "👋 Привет!\n\n"
        "Я бот для продажи VPN-ключей. "
        "Выбери действие в меню:",
        reply_markup=get_main_menu_kb()
    )


@router.callback_query(F.data == "menu:buy")
async def menu_buy_select_country(callback: CallbackQuery):
    """Показывает выбор страны."""
    await callback.message.edit_text(
        "🌍 Выберите страну подключения:",
        reply_markup=get_country_selection_kb()  # Новая клавиатура
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_country:"))
async def select_country_show_tariffs(callback: CallbackQuery):
    """Показывает тарифы после выбора страны."""
    country = callback.data.split(":")[1]
    log.info(f"User {callback.from_user.id} selected country: {country}")
    products = await db.get_products(country=country) # Передаем страну

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
                callback_data=f"buy_product:{product.id}:{country}" # ID теперь уникален
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
    await callback.answer() # Снимаем часики

    user_id = callback.from_user.id
    page = 0 # Всегда начинаем с первой страницы
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

    await callback.answer() # Снимаем часики

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


@router.callback_query(F.data.in_({"menu:help", "menu:support"}))
async def menu_static(callback: CallbackQuery):
    """Статичные страницы (инлайн)."""
    if callback.data == "menu:help":
        text = "Инструкция по подключению V2Box:\n1. ...\n2. ..."
    else:
        text = "По всем вопросам пишите @CoId_Siemens"

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
    """Показывает контакт поддержки."""
    await callback.message.edit_text(
        TEXT_SUPPORT,
        reply_markup=InlineKeyboardMarkup(  # Клавиатура только с кнопкой "Назад"
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]]
        ),
    )


@router.callback_query(F.data.startswith("buy_product:"))
async def process_buy_callback(callback: CallbackQuery, bot: Bot):
    """Обработка нажатия на кнопку тарифа (теперь со страной)"""
    await callback.answer(cache_time=1)
    try:
        _, product_id_str, country = callback.data.split(":")
        product_id = int(product_id_str)
    except ValueError:
        log.error(f"Invalid callback data format: {callback.data}")
        await callback.message.edit_text("Произошла ошибка. Попробуйте снова.")
        return

    log.info(f"User {callback.from_user.id} initiated purchase for product {product_id} in country {country}")

    product = await db.get_product_by_id(product_id)
    if not product:
        await callback.message.edit_text(
            "Тариф не найден. Попробуйте снова.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад к странам", callback_data="menu:buy")]])
        )
        return

    # 1. Создаем заказ в БД
    order_id = await db.create_order(
        user_id=callback.from_user.id,
        product_id=product_id,
        amount=product.price
    )

    # 2. Создаем счет в ЮKassa, добавляем страну в metadata
    payment_url, payment_id = await create_yookassa_payment(
        amount=product.price,
        description=f"Оплата '{product.name}' ({country}) (Заказ #{order_id})",
        order_id=order_id,
        metadata={"country": country}  # ⬅️ Добавляем страну сюда
    )

    # 3. Обновляем заказ, добавляя payment_id
    await db.update_order_status(order_id, payment_id, status='pending')

    # 4. Отправляем ссылку на оплату
    kb = get_payment_kb(payment_url, order_id)  # Клавиатура уже включает кнопку "Назад к странам"

    await callback.message.edit_text(
        f"Вы выбрали: **{product.name} ({country})**\n"
        f"Сумма к оплате: **{product.price} руб.**\n\n"
        "Нажмите кнопку ниже, чтобы перейти к оплате:",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("check_payment:"))
async def process_check_payment(callback: CallbackQuery, bot: Bot):
    """
    Обработка нажатия на кнопку "Проверить оплату"
    """
    order_id = int(callback.data.split(":")[1])

    order = await db.get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден!", show_alert=True)
        return

    if order.status == 'paid':

        user_key = await db.get_user_key_by_order_id(order_id)
        if user_key:
            await callback.answer("Этот заказ уже оплачен.", show_alert=True)
        else:
            await callback.answer("Заказ оплачен, но произошла ошибка выдачи. Свяжитесь с поддержкой.", show_alert=True)
        return

    if not order.payment_id:
        await callback.answer("Ошибка: ID платежа не найден.", show_alert=True)
        return

    payment_info = await check_yookassa_payment(order.payment_id)

    if not payment_info:
        await callback.answer("Не удалось проверить статус платежа.", show_alert=True)
        return

    if payment_info.status == 'succeeded':
        # --- БЛОК ВЫДАЧИ КЛЮЧА ---
        await db.update_order_status(order_id, order.payment_id, status='paid')
        await callback.answer("✅ Оплата найдена! Генерирую ключ...")

        country = payment_info.metadata.get("country")
        if not country:
            log.error(f"!!! ОШИБКА: Не найдена страна в metadata платежа {payment_info.id} для заказа {order_id}")
            country = settings.XUI_SERVERS[0].country if settings.XUI_SERVERS else "Unknown"
            # TODO: Или можно попробовать найти страну по product_id заказа, если тарифы уникальны для стран
            await callback.message.edit_text("Ошибка: Не удалось определить страну. Свяжитесь с поддержкой.")
            return

        success, vless_string = await issue_key_to_user(
            bot=bot,
            user_id=order.user_id,
            product_id=order.product_id,
            order_id=order.id,
            country=country
        )

        if success:
            # 3. Показываем РЕАЛЬНЫЙ ключ прямо в текущем меню
            product = await db.get_product_by_id(order.product_id)
            expires_at = datetime.datetime.now() + datetime.timedelta(days=product.duration_days)

            if success:
                product = await db.get_product_by_id(order.product_id)
                expires_at = datetime.datetime.now() + datetime.timedelta(days=product.duration_days)
                success_text = (
                    f"✅ **Оплата прошла успешно! ({country})**\n\n"  # Добавили страну
                    "Ваш ключ доступа:\n"
                    f"```\n{vless_string}\n```\n\n"
                    f"Срок действия: **{product.duration_days} дней** (до {expires_at.strftime('%Y-%m-%d %H:%M')})\n\n"
                    "Скопируйте ключ и добавьте его в V2Box."
                )
                await callback.message.edit_text(
                    success_text,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="📋 Главное меню", callback_data="menu:main")]]),
                    # Изменили кнопку
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
        else:
            # 4. Если issue_key_to_user провалился
            await callback.message.edit_text(
                "❌ **Ошибка выдачи ключа**\n\n"
                "Оплата прошла, но при создании ключа произошла ошибка.\n"
                "Мы уже уведомили администратора. Пожалуйста, свяжитесь с поддержкой.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]]
                ),
                parse_mode="Markdown"
            )
        # --- КОНЕЦ БЛОКА ВЫДАЧИ ---

    elif payment_info.status == 'pending':
        await callback.answer("Платеж еще не поступил. Подождите...", show_alert=True)

    elif payment_info.status in ('canceled', 'failed'):
        await callback.answer(f"Платеж отменен (статус: {payment_info.status}).", show_alert=True)

    else:
        await callback.answer(f"Статус платежа: {payment_info.status}", show_alert=True)
