import datetime
import html
import logging
import math
import crypto_pay
import json

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from aiogram.filters import CommandStart
from aiogram.exceptions import AiogramError
from config import settings
from utils import issue_key_to_user, issue_trial_key

from keyboards import get_main_menu_kb, get_payment_kb, get_instruction_platforms_kb, get_back_to_instructions_kb, \
    get_country_selection_kb, get_my_keys_kb, get_key_details_kb, get_support_kb, get_payment_method_kb, \
    get_renewal_payment_method_kb, get_payment_success_kb, get_trial_already_used_kb
from database import db_commands as db
from payments import create_yookassa_payment, check_yookassa_payment
from utils import generate_vless_key, handle_payment_logic
from middlewares.throttling import ThrottlingMiddleware

log = logging.getLogger(__name__)
router = Router()

# router.message.filter(CommandStart()).middleware(ThrottlingMiddleware(rate_limit=1.0))
router.message.middleware(ThrottlingMiddleware(rate_limit=1.0))

router = Router()

TEXT_INSTRUCTION_MENU = "ℹ️ **Инструкция**\n\nВыберите вашу операционную систему:"
TEXT_ANDROID = """
Скачайте бесплатный клиент [v2RayTun](https://play.google.com/store/apps/details?id=com.v2raytun.android&pcampaignid=web_share) и вставьте ключ по инструкции с фото.
"""
TEXT_IOS = """
Скачайте бесплатный клиент [v2RayTun](https://apps.apple.com/ru/app/v2raytun/id6476628951) и вставьте ключ по инструкции с фото.
"""
TEXT_WINDOWS = """
Скачайте бесплатный клиент [v2RayN](https://github.com/2dust/v2rayN/releases) и вставьте ключ по инструкции с фото.
"""
TEXT_MACOS = """
Скачайте бесплатный клиент [v2RayTun](https://apps.apple.com/ru/app/v2raytun/id6476628951) и вставьте ключ по инструкции с фото.
"""
TEXT_SUPPORT = "По всем вопросам пишите @NjordVPN_Support"


async def _notify_admins(bot: Bot, text: str):
    """Отправляет сообщение всем админам из .env."""
    for admin_id in settings.get_admin_ids:
        try:
            await bot.send_message(
                admin_id,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except AiogramError as e:
            log.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")


def _get_user_info_for_admin(message: Message | CallbackQuery) -> str:
    """Форматирует кликабельную ссылку на пользователя или @username."""
    user = message.from_user
    if user.username:
        #
        return f"@{user.username}"
    else:
        #
        safe_name = html.escape(user.first_name or f"User {user.id}")
        return f'<a href="tg://user?id={user.id}">{safe_name}</a> (ID: {user.id})'


def _get_flag_for_country(country_name: str) -> str:
    """
    Вспомогательная функция для получения флага страны.
    (Логика взята из keyboards.py)
    """
    if country_name == "Финляндия": return "🇫🇮"
    if country_name == "Германия": return "🇩🇪"
    if country_name == "Нидерланды": return "🇳🇱"
    return "🏳️"


async def _handle_old_menu(bot: Bot, user_id: int, last_menu_id: int | None):
    """Пытается удалить старое меню. Если не вышло - редактирует."""
    if not last_menu_id:
        return  #

    try:
        await bot.delete_message(chat_id=user_id, message_id=last_menu_id)
    except AiogramError as e:
        if "message to delete not found" in str(e) or "message can't be deleted" in str(e):
            try:
                await bot.edit_message_text("🗑️", chat_id=user_id, message_id=last_menu_id)
            except Exception as e_edit:
                log.info(
                    f"Не удалось ни удалить, ни отредактировать старое меню {last_menu_id} для {user_id}: {e_edit}")
        else:
            log.info(f"Не удалось удалить старое меню {last_menu_id} для {user_id}: {e}")


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    try:
        await message.delete()
    except AiogramError:
        pass

    last_menu_id = await db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.full_name
    )

    if last_menu_id is None:
        user_info = _get_user_info_for_admin(message)
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        await _notify_admins(bot, f"👤 Новый пользователь: {user_info}\n({now_str})")

    await _handle_old_menu(bot, message.from_user.id, last_menu_id)

    # TASK 1: Проверяем наличие ключей
    keys_count = await db.count_user_keys(message.from_user.id)
    show_keys = keys_count > 0

    new_menu_message = await message.answer(
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        "Я бот NjordVPN. Ищешь быстрый и стабильный VPN?\n\n"
        "Не нужно покупать вслепую. **Попробуй наш VPN бесплатно!**\n\n"
        "Нажми 🎁 **Пробный период (24ч)** в меню ниже, чтобы мгновенно получить свой первый ключ.\n\n"
        "\nP.S. Наш основной канал с новостями и акциями: https://t.me/NjordVPN",
        reply_markup=get_main_menu_kb(user_id=message.from_user.id, has_keys=show_keys),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await db.update_user_menu_id(message.from_user.id, new_menu_message.message_id)


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery):
    # TASK 1: Проверяем наличие ключей при возврате в меню
    keys_count = await db.count_user_keys(callback.from_user.id)
    show_keys = keys_count > 0

    await callback.message.edit_text(
        f"👋 Привет, {callback.from_user.full_name}!\n\n"
        "Я бот NjordVPN. Ищешь быстрый и стабильный VPN?\n\n"
        "Не нужно покупать вслепую. **Попробуй наш VPN бесплатно!**\n\n"
        "Нажми 🎁 **Пробный период (24ч)** в меню ниже, чтобы мгновенно получить свой первый ключ.\n\n"
        "\nP.S. Наш основной канал с новостями и акциями: https://t.me/NjordVPN",
        reply_markup=get_main_menu_kb(user_id=callback.from_user.id, has_keys=show_keys),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu:buy")
async def menu_buy_select_country(callback: CallbackQuery):
    # TASK 2: Новый текст меню покупки
    text = (
        "Мы используем только высокопроизводительные серверы:\n\n"
        "⚡ **Премиум (Финляндия)**\n"
        "Канал 10 Гбит/с. Оптимизирован для стриминга (Netflix, 4K) и игр с низким пингом.\n\n"
        "🔹 **Стандарт (Германия, Нидерланды)**\n"
        "Канал 1 Гбит/с. Идеально подходит для мессенджеров и соцсетей.\n\n"
        "Все тарифы включают безлимитный трафик.\n\n"
        "🌍 Выберите страну подключения:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_country_selection_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "trial:get")
async def process_trial_get(callback: CallbackQuery, bot: Bot):
    """
    Обрабатывает нажатие на кнопку 'Пробный период'.
    (Модель 2: Выдает 1 ссылку-подписку на 1 ключ)
    """
    user_id = callback.from_user.id
    log.info(f"Пользователь {user_id} запросил пробный период.")
    has_already_taken_trial = await db.check_trial_status(user_id)
    if has_already_taken_trial:
        log.info(f"Пользователь {user_id} уже получал триал. Показываю меню 'Купить'.")
        await callback.answer()
        await callback.message.edit_text(
            "Вы уже получали пробный ключ!\n\n"
            "Ознакомьтесь с тарифами, если вам понравился пробный период:",
            reply_markup=get_trial_already_used_kb()
        )
        return

    await callback.answer("⏳ Проверяю возможность выдачи...")

    success, result_data = await issue_trial_key(bot, user_id)

    if success:
        subscription_url = result_data  #
        user_info = _get_user_info_for_admin(callback)
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        await _notify_admins(bot, f"🎁 {user_info} получил пробный ключ.\n({now_str})")

        success_text = (
            f"✅ <b>Пробный период на 24 часа активирован!</b>\n"
            f"Ваш <b>ключ</b> 👇👇👇\n\n"
            f"<code>{subscription_url}</code>\n\n"
            f"1. Нажмите на <b>ключ</b> 👆👆👆, чтобы скопировать его\n"
            f"2. Выберите тип устройства\n"
        )

        await callback.message.answer(
            success_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_instruction_platforms_kb()
        )
    else:
        #
        error_message = result_data
        if error_message == "Вы уже активировали пробный период.":
            await callback.answer(
                "Вы уже использовали пробный период.",
                show_alert=True
            )
            await callback.answer()
        else:
            await callback.answer(error_message, show_alert=True)



@router.callback_query(F.data.startswith("special_offer:"))
async def process_special_offer(callback: CallbackQuery):
    try:
        _, price_str, key_id_str = callback.data.split(":")
        price, key_id = float(price_str), int(key_id_str)
    except ValueError:
        await callback.answer("Ошибка предложения.", show_alert=True)
        return
    await callback.answer("⏳ Создаю заказ по акции...")

    finland_products = await db.get_products(country="Финляндия")
    product = next((p for p in finland_products if p.duration_days == 30), finland_products[0] if finland_products else None)
    if not product:
        await callback.answer("Ошибка: Тариф не найден.", show_alert=True)
        return

    order_id = await db.create_order(user_id=callback.from_user.id, product_id=product.id, amount=price)
    # ВАЖНО: Сохраняем тип "special_offer" и цену для кнопки "Назад"
    await db.update_order_status(order_id, json.dumps({"renewal_key_id": key_id, "type": "special_offer", "offer_price": price}), status='pending')

    kb = get_renewal_payment_method_kb(order_id)
    # kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"key_details:{key_id}:0")])
    await callback.message.edit_text(f"🔥 **Специальное предложение!**\n\nТариф: **{product.name} (Финляндия 🇫🇮)**\nСрок: **30 дней**\nСумма к оплате: **{price:.0f} руб.**\n\nВыберите способ оплаты:", reply_markup=kb, parse_mode="Markdown")


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
    """Показывает ПЕРВУЮ страницу ключей пользователя. (Модель 2)"""
    await callback.answer()

    user_id = callback.from_user.id
    page = 0
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
    text = "🔑 **Ваши ключи:**\n\nНажмите на ключ чтобы скопировать его и узнать более подробную информацию"
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
    """
    Показывает детали выбранного ключа.
    (Версия 3.1: Сразу показывает ссылку-подписку и кнопки Назад/Продлить)
    """
    try:
        _, key_id_str, page_str = callback.data.split(":")
        key_id = int(key_id_str)
        current_page = int(page_str)
    except (IndexError, ValueError):
        log.warning(f"Некорректный callback_data для деталей ключа: {callback.data}")
        await callback.answer("Ошибка получения ключа.", show_alert=True)
        return

    await callback.answer()

    key = await db.get_key_by_id(key_id)

    if not key or key.user_id != callback.from_user.id:
        await callback.answer("Ключ не найден.", show_alert=True)
        await menu_keys_show_first_page(callback)
        return

    if not key.subscription_token:
        log.error(f"Критическая ошибка: Ключ {key.id} не имеет subscription_token!")
        await callback.answer("Ошибка: Токен подписки для этого ключа не найден.", show_alert=True)
        return

    server_ip_to_country = {s.vless_server: s.country for s in settings.XUI_SERVERS}
    country = "Unknown"
    flag = "🏳️"
    try:
        server_ip = key.vless_key.split('@')[1].split(':')[0]
        country = server_ip_to_country.get(server_ip, "Unknown")
        flag = _get_flag_for_country(country)
    except Exception:
        pass

    server_info = f"{country} {flag}"

    now = datetime.datetime.now()
    if key.expires_at > now:
        status = "✅ <b>Активен</b>"
        remaining = key.expires_at - now
        days = remaining.days
        hours = remaining.seconds // 3600
        time_left = f"{days} дн. {hours} ч."
    else:
        status = "❌ <b>Истек</b>"
        time_left = "0"

    subscription_url = f"{settings.WEBHOOK_HOST}/sub/{key.subscription_token}"

    text = (
        f"🔑 <b>Детали ключа</b> ({status})\n\n"
        f"Сервер: <b>{server_info}</b>\n"
        f"Истекает: <code>{key.expires_at.strftime('%Y-%m-%d %H:%M')}</code>\n"
        f"Осталось: {time_left}\n\n"
        "Ваш ключ 👇👇👇\n\n"
        f"<code>{subscription_url}</code>\n\n"
        "Нажмите на ключ 👆👆👆, чтобы скопировать"
    )

    #
    kb = get_key_details_kb(key_id, current_page)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except AiogramError as e:
        if "message is not modified" not in str(e).lower():
            log.warning(f"Ошибка в menu_key_details: {e}")
            pass


@router.callback_query(F.data.startswith("key_renew:"))
async def menu_key_renew(callback: CallbackQuery):
    try:
        _, key_id_str, page_str = callback.data.split(":")
        key_id, current_page = int(key_id_str), int(page_str)
    except (IndexError, ValueError):
        await callback.answer("Ошибка продления.", show_alert=True)
        return
    await callback.answer("⏳ Готовлю счет для продления...")
    key = await db.get_key_by_id(key_id)
    if not key or key.user_id != callback.from_user.id:
        await callback.answer("Ключ не найден.", show_alert=True)
        return

    if key.order_id is None:
        finland_products = await db.get_products(country="Финляндия")
        renewal_product = next((p for p in finland_products if p.duration_days == 30), finland_products[0] if finland_products else None)
        if not renewal_product:
             await callback.answer("Ошибка: Тарифы для Финляндии не найдены.", show_alert=True)
             return
        renewal_price = renewal_product.price
        renewal_text = f"Вы продлеваете пробный ключ (Финляндия 🇫🇮):\nТариф: **{renewal_product.name}**\n"
    else:
        original_order = await db.get_order_by_id(key.order_id)
        renewal_product = await db.get_product_by_id(original_order.product_id) if original_order else None
        if not renewal_product:
            await callback.answer("Ошибка: Не найден тариф для продления.", show_alert=True)
            return
        renewal_price = renewal_product.price
        renewal_text = f"Вы продлеваете: **{renewal_product.name}**\n"

    renewal_order_id = await db.create_order(user_id=callback.from_user.id, product_id=renewal_product.id, amount=renewal_price)
    # ВАЖНО: Сохраняем тип "renewal" для кнопки "Назад"
    await db.update_order_status(renewal_order_id, json.dumps({"renewal_key_id": key_id, "type": "renewal"}), status='pending')

    kb = get_renewal_payment_method_kb(renewal_order_id)
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"key_details:{key_id}:{current_page}")])
    await callback.message.edit_text(f"{renewal_text}Срок: +{renewal_product.duration_days} дней\nСумма к оплате: **{renewal_price} руб.**\n\nВыберите способ оплаты:", reply_markup=kb, parse_mode="Markdown")


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
async def menu_instruction_detail(callback: CallbackQuery, bot: Bot):
    """
    Показывает инструкцию для выбранной ОС.
    (Версия 3.1: Отправляет Фото И УДАЛЯЕТ старое меню)
    """

    photo_file_ids = {
        "android": [
            "AgACAgIAAxkBAAICPGkLY_drTd0nVnsL_5PKdBXaS9fQAAKKEGsb9sVZSBAqiewL-13xAQADAgADeQADNgQ",
            "AgACAgIAAxkBAAICPmkLY_w-7WhQYf0AARMa3VunSj1lqAACixBrG_bFWUgDvT8Xod4Z3AEAAwIAA3kAAzYE"
        ],
        "ios": "AgACAgIAAxkBAAICKGkLYm5_XyCAmvTiYB8jg6AGqUN9AAKAEGsb9sVZSEh7QgXeTYatAQADAgADeQADNgQ",
        "windows": [
            "AgACAgIAAxkBAAICIWkLWnL0GRAzIcCd4V-ECnF3-3O0AAJdD2sbVAJYSCHqt6zI0c4cAQADAgADeAADNgQ",
            "AgACAgIAAxkBAAICH2kLWmRvaP2PDReDiJAJA73uclRaAAJcD2sbVAJYSBnNd5oZOSROAQADAgADeAADNgQ"
        ],
        "macos": "AgACAgIAAxkBAAICHWkLWlrP9u6ZIKZwz5mjAAGcTPg5hQACVw9rG1QCWEiJXH2RydyIewEAAwIAA3gAAzYE"
    }

    platform = callback.data.split(":")[1]
    text = "Инструкция не найдена."
    photo_data = photo_file_ids.get(platform)

    if platform == "android":
        text = TEXT_ANDROID
    elif platform == "ios":
        text = TEXT_IOS
    elif platform == "windows":
        text = TEXT_WINDOWS
    elif platform == "macos":
        text = TEXT_MACOS

    await callback.answer()

    if not photo_data:
        log.warning(f"Не найден file_id для инструкции '{platform}'.")
        return  #

    try:
        # ⬇️ ⬇️ ⬇️ НОВАЯ ЛОГИКА ⬇️ ⬇️ ⬇️

        #
        if isinstance(photo_data, list):
            #
            media = []
            for i, p_id in enumerate(photo_data):
                if i == 0:
                    #
                    media.append(InputMediaPhoto(media=p_id, caption=text, parse_mode="Markdown"))
                else:
                    #
                    media.append(InputMediaPhoto(media=p_id))

            #
            await bot.send_media_group(
                chat_id=callback.from_user.id,
                media=media
            )

        #
        elif isinstance(photo_data, str):
            #
            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=photo_data,  #
                caption=text,
                parse_mode="Markdown"
            )

        #
        # await callback.message.delete()

    except AiogramError as e:
        log.error(f"Не удалось отправить фото-инструкцию для {platform} по file_id: {e}")
        await callback.message.answer(
            f"Не удалось загрузить картинку, вот текстовая инструкция:\n\n{text}",
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

    kb = get_payment_method_kb(order_id, country)

    try:
        await callback.message.edit_text(
            f"Вы выбрали: **{product.name} ({country})**\n"
            f"Сумма к оплате: **{product.price} руб.**\n\n"
            "Теперь выберите удобный способ оплаты:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        log.error(f"Ошибка при показе выбора спососа оплаты: {e}")
        await callback.answer("Не удалось обновить меню. Попробуйте снова.")


@router.callback_query(F.data.startswith("pay_method:"))
async def process_payment_method(callback: CallbackQuery, bot: Bot):
    await callback.answer("⏳ Создаю ссылку на оплату...")
    try:
        _, method, order_id_str = callback.data.split(":")
        order_id = int(order_id_str)
    except ValueError:
        await callback.answer("Ошибка!", show_alert=True)
        return

    order = await db.get_order_by_id(order_id)
    if not order or order.user_id != callback.from_user.id or order.status != 'pending':
        await callback.answer("Заказ не найден или уже обработан.", show_alert=True)
        return
    product = await db.get_product_by_id(order.product_id)
    if not product:
        await callback.answer("Тариф не найден.", show_alert=True)
        return

    renewal_key_id = None
    back_callback_data = f"select_country:{product.country or 'Unknown'}"

    # === ВАЖНО: Определяем, куда возвращаться по кнопке "Назад" ===
    if order.payment_id and order.payment_id.startswith("{"):
        try:
            order_metadata = json.loads(order.payment_id)
            renewal_key_id = order_metadata.get("renewal_key_id")
            order_type = order_metadata.get("type")
            if order_type == "special_offer":
                 # Возвращаемся на экран спецпредложения
                 offer_price = order_metadata.get("offer_price", 119)
                 back_callback_data = f"special_offer:{offer_price}:{renewal_key_id}"
            elif order_type == "renewal":
                 # Возвращаемся на экран обычного продления
                 back_callback_data = f"key_renew:{renewal_key_id}:0"
        except (json.JSONDecodeError, AttributeError): pass

    metadata = {"order_id": str(order_id), "country": product.country or "Unknown", "renewal_key_id": renewal_key_id}
    amount_to_pay = order.amount
    payment_url, payment_id_to_db, payment_system_name = None, None, ""

    try:
        if method == "yookassa":
            payment_system_name = "ЮKassa"
            payment_url, payment_id_to_db = await create_yookassa_payment(amount=amount_to_pay, description=f"Оплата '{product.name}' ({metadata['country']}) (Заказ #{order_id})", order_id=order_id, metadata=metadata)
        elif method == "crypto":
            payment_system_name = "Crypto Bot"
            payment_url = await crypto_pay.create_crypto_invoice(amount_rub=amount_to_pay, currency="RUB", order_id=order_id, metadata=metadata)
            payment_id_to_db = f"crypto_{order_id}"
        if not payment_url: raise Exception("Empty payment URL")
    except Exception as e:
        log.error(f"Ошибка создания счета {method}: {e}")
        await callback.answer("Не удалось создать счет. Попробуйте другой способ.", show_alert=True)
        return

    await db.update_order_status(order_id, payment_id_to_db, status='pending')
    try:
        await callback.message.answer(f"Ваша ссылка на оплату ({payment_system_name}):\nТариф: **{product.name} ({metadata['country']})**\nСумма: **{amount_to_pay:.0f} руб.**\n\nНажмите кнопку ниже, чтобы перейти к оплате:", reply_markup=get_payment_kb(payment_url, order_id, back_callback_data), parse_mode="Markdown")
        await callback.message.delete()
    except Exception: pass


@router.callback_query(F.data.startswith("check_payment:"))
async def process_check_payment(callback: CallbackQuery, bot: Bot):
    """
    Обработка нажатия на кнопку "Проверить оплату".
    (Версия с авто-вебхуками)
    """
    order_id = int(callback.data.split(":")[1])

    order = await db.get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден!", show_alert=True)
        return

    if order.status == 'paid':
        await callback.answer("Этот заказ уже оплачен. Ключ должен был прийти в чат.", show_alert=True)
        return

    if order.status == 'pending':
        if order.payment_id and not order.payment_id.startswith("crypto_"):
            await callback.answer("Проверяю ЮKassa... Пожалуйста, подождите.", show_alert=True)
            payment_info = await check_yookassa_payment(order.payment_id)
            if payment_info and payment_info.status == 'succeeded':
                metadata = payment_info.metadata
                success, message_text, operation_type = await handle_payment_logic(bot, order_id, metadata)

                kb = None
                if operation_type == "new_key":
                    kb = get_instruction_platforms_kb()  #
                elif operation_type == "renewal":
                    renewal_key_id = metadata.get("renewal_key_id")
                    kb = get_payment_success_kb(renewal_key_id)  #

                await callback.message.edit_text(
                    message_text,
                    reply_markup=kb,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            else:
                await callback.answer("Платеж в ЮKassa еще не прошел.", show_alert=True)
        else:
            await callback.answer(
                "Платеж еще не поступил. Пожалуйста, ожидайте, бот пришлет ключ автоматически после оплаты.",
                show_alert=True)

    else:
        await callback.answer(f"Статус заказа: {order.status}. Обратитесь в поддержку.", show_alert=True)
