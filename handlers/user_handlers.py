# handlers/user_handlers.py
import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart

from keyboards import get_main_menu_kb, get_payment_kb
from database import db_commands as db
from payments import create_yookassa_payment, check_yookassa_payment  # Создадим в шаге 3
from utils import generate_vless_key  # Создадим в шаге 4

router = Router()


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
async def menu_buy(callback: CallbackQuery):
    """Показать список тарифов (инлайн)."""
    products = await db.get_products()
    if not products:
        await callback.message.edit_text(
            "К сожалению, сейчас нет доступных тарифов.",
            reply_markup=get_main_menu_kb()
        )
        return

    text = "Выберите тариф:\n\n"
    buttons = []
    for product in products:
        text += f"🔹 **{product.name}** - {product.price} руб.\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"{product.name} ({product.price} руб.)",
                callback_data=f"buy_product:{product.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu:keys")
async def menu_keys(callback: CallbackQuery):
    """Показать ключи пользователя (инлайн)."""
    user_keys = await db.get_user_keys(callback.from_user.id)
    if not user_keys:
        await callback.message.edit_text(
            "У вас пока нет купленных ключей.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]]
            ),
        )
        return

    text = "🔑 **Ваши ключи:**\n\n"
    now = datetime.datetime.now()
    for i, key in enumerate(user_keys, 1):
        if key.expires_at > now:
            status = "✅ *Активен*"
            remaining = key.expires_at - now
            time_left = f"{remaining.days} дн. {remaining.seconds // 3600} ч."
        else:
            status = "❌ *Истек*"
            time_left = "0"
        text += (
            f"**Ключ #{i}** ({status})\n"
            f"Истекает: `{key.expires_at.strftime('%Y-%m-%d %H:%M')}`\n"
            f"Осталось: {time_left}\n"
            f"```\n{key.vless_key}\n```\n\n"
        )

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]]
        ),
    )


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


@router.message(F.text == "🛒 Купить VPN")
async def buy_vpn(message: Message):
    """Показывает список тарифов"""
    products = await db.get_products()
    if not products:
        await message.answer("К сожалению, сейчас нет доступных тарифов.")
        return

    text = "Выберите тариф:\n\n"
    buttons = []
    for product in products:
        text += f"🔹 **{product.name}** - {product.price} руб.\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"{product.name} ({product.price} руб.)",
                callback_data=f"buy_product:{product.id}"
            )
        ])

    await message.answer(text,
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                         parse_mode="Markdown")


@router.callback_query(F.data.startswith("buy_product:"))
async def process_buy_callback(callback: CallbackQuery, bot: Bot):
    """Обработка нажатия на кнопку тарифа"""
    await callback.answer(cache_time=1)  # Снимаем "часики"
    product_id = int(callback.data.split(":")[1])

    product = await db.get_product_by_id(product_id)
    if not product:
        await callback.message.edit_text(
            "Тариф не найден. Попробуйте снова.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy")]]
            ),
        )
        await callback.answer()
        return

    # 1. Создаем заказ в БД
    order_id = await db.create_order(
        user_id=callback.from_user.id,
        product_id=product_id,
        amount=product.price
    )

    # 2. Создаем счет в ЮKassa
    payment_url, payment_id = await create_yookassa_payment(
        amount=product.price,
        description=f"Оплата тарифа '{product.name}' (Заказ #{order_id})",
        order_id=order_id
    )

    # 3. Обновляем заказ, добавляя payment_id
    await db.update_order_status(order_id, payment_id, status='pending')

    # 4. Отправляем ссылку на оплату
    kb = get_payment_kb(payment_url, order_id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=kb.inline_keyboard + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy")]]
    )

    await callback.message.edit_text(
        f"Вы выбрали: **{product.name}**\n"
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
        await callback.answer("Этот заказ уже оплачен.", show_alert=True)
        return

    if not order.payment_id:
        await callback.answer("Ошибка: ID платежа не найден.", show_alert=True)
        return

    # Запрашиваем статус в ЮKassa
    payment_info = await check_yookassa_payment(order.payment_id)

    if not payment_info:
        await callback.answer("Не удалось проверить статус платежа.", show_alert=True)
        return

    if payment_info.status == 'succeeded':
        # Ура, оплата прошла!
        # 1. Обновляем статус в нашей БД
        await db.update_order_status(order_id, order.payment_id, status='paid')

        # 2. Выдаем ключ (в том же сообщении, без отдельного сообщения)
        product = await db.get_product_by_id(order.product_id)
        vless_string = generate_vless_key(order.user_id, product.name)
        expires_at = datetime.datetime.now() + datetime.timedelta(days=product.duration_days)
        await db.add_vless_key(
            user_id=order.user_id,
            order_id=order.id,
            vless_key=vless_string,
            expires_at=expires_at
        )

        # 3. Показываем ключ прямо в текущем меню + кнопка "Назад" в главное меню
        success_text = (
            "✅ Оплата прошла успешно!\n\n"
            "Ваш тестовый ключ доступа:\n"
            f"```\n{vless_string}\n```\n\n"
            f"Срок действия: **{product.duration_days} дней** (до {expires_at.strftime('%Y-%m-%d %H:%M')})\n\n"
            "Скопируйте ключ и добавьте его в V2Box."
        )
        await callback.message.edit_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]]
            ),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        await callback.answer()

    elif payment_info.status == 'pending':
        await callback.answer("Платеж еще не поступил. Подождите...", show_alert=True)

    elif payment_info.status in ('canceled', 'failed'):
        await callback.answer(f"Платеж отменен (статус: {payment_info.status}).", show_alert=True)

    else:
        await callback.answer(f"Статус платежа: {payment_info.status}", show_alert=True)


@router.message(F.text == "📖 Мои ключи")
async def my_keys(message: Message):
    """Показывает активные и истекшие ключи"""
    user_keys = await db.get_user_keys(message.from_user.id)
    if not user_keys:
        await message.answer("У вас пока нет купленных ключей.")
        return

    text = "🔑 **Ваши ключи:**\n\n"
    now = datetime.datetime.now()

    for i, key in enumerate(user_keys, 1):
        if key.expires_at > now:
            status = "✅ *Активен*"
            remaining = key.expires_at - now
            time_left = f"{remaining.days} дн. {remaining.seconds // 3600} ч."
        else:
            status = "❌ *Истек*"
            time_left = "0"

        text += (
            f"**Ключ #{i}** ({status})\n"
            f"Истекает: `{key.expires_at.strftime('%Y-%m-%d %H:%M')}`\n"
            f"Осталось: {time_left}\n"
            f"```\n{key.vless_key}\n```\n\n"
        )

    await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)


@router.message(F.text.in_({"ℹ️ Помощь", "💬 Поддержка"}))
async def static_pages(message: Message):
    """Обработка статичных кнопок"""
    if message.text == "ℹ️ Помощь":
        text = "Инструкция по подключению V2Box:\n1. ...\n2. ..."
    else:  # 💬 Поддержка
        text = "По всем вопросам пишите @CoId_Siemens"

    await message.answer(text)