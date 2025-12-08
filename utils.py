import datetime
import uuid
import logging
from typing import Optional, Dict

from aiogram import Bot
from urllib.parse import quote

# from yookassa import Payment

from config import settings, XuiServer
from database import db_commands as db
import vpn_api
import crm
# from database.models import Orders

log = logging.getLogger(__name__)

global_last_server_indices: Dict[str, int] = {}


async def get_least_loaded_server(country: str) -> Optional[XuiServer]:
    """
    Выбирает сервер из УКАЗАННОЙ СТРАНЫ методом "Карусель".
    Возвращает None, если серверов в этой стране нет.
    """
    global global_last_server_indices
    all_servers = settings.XUI_SERVERS

    # 1. Фильтруем серверы по выбранной стране
    servers_in_country = [s for s in all_servers if s.country == country]

    if not servers_in_country:
        log.error(f"!!! ОШИБКА в get_least_loaded_server: Не найдено серверов для страны '{country}'!")
        return None

    # 2. Инициализируем/получаем индекс для этой страны
    if country not in global_last_server_indices:
        global_last_server_indices[country] = -1
    last_index = global_last_server_indices[country]

    # 3. Применяем "Карусель" к отфильтрованному списку
    next_index = (last_index + 1) % len(servers_in_country)
    global_last_server_indices[country] = next_index  # Обновляем индекс для ЭТОЙ СТРАНЫ

    selected_server = servers_in_country[next_index]

    if isinstance(selected_server, XuiServer):
        log.info(f"Распределитель: для страны '{country}' выбран сервер {selected_server.name}")
        return selected_server
    else:
        log.error(f"!!! НЕИЗВЕСТНЫЙ ТИП: get_least_loaded_server вернул {type(selected_server)}")
        return None


def generate_vless_key(user_uuid: str, product_name: str, user_id: int, server_config: XuiServer) -> str:
    """
    Генерирует ссылку VLess в формате VLESS + XHTTP + Reality,
    основываясь на ключе, сгенерированном панелью.
    """
    tag = f"VPNBot_{product_name.replace(' ', '_')}_{user_id}_{server_config.country}"

    vless_server = server_config.vless_server
    vless_port = server_config.vless_port
    security_type = server_config.security_type  # "reality"
    reality_pbk = server_config.reality_pbk
    reality_short_id = server_config.reality_short_id
    reality_sni = server_config.reality_server_names[0] if server_config.reality_server_names else ""
    reality_fp = server_config.reality_fingerprint
    xhttp_path_raw = "/"
    xhttp_path = quote(xhttp_path_raw)

    # Собираем VLESS + XHTTP + Reality
    vless_string = (
        f"vless://{user_uuid}"
        f"@{vless_server}:{vless_port}"
        f"?type=xhttp"
        f"&encryption=none"
        f"&path={xhttp_path}"
        # f"&host="
        # f"&mode=auto"
        f"&security={security_type}"
        f"&pbk={reality_pbk}"
        f"&fp={reality_fp}"
        f"&sni={reality_sni}"
        f"&sid={reality_short_id}"
        # f"&spx={xhttp_path}"
        # f"&pqv=..."
        f"#{tag}"
    )

    return vless_string


async def issue_key_to_user(bot: Bot, user_id: int, product_id: int, order_id: int, country: str) -> tuple[
    bool, uuid.UUID | None]:  #
    """
    Полный цикл выдачи ключа.
    Возвращает (Успех, Токен_Подписки).
    """
    try:
        server_config = await get_least_loaded_server(country=country)
        if not server_config:
            raise ValueError(f"No servers found for country: {country}")

        product = await db.get_product_by_id(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        new_uuid = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(days=product.duration_days)

        api_success = await vpn_api.add_vless_user(
            server_config=server_config,
            user_id=user_id,
            days=product.duration_days,
            new_uuid=new_uuid
        )

        if not api_success:
            raise Exception("Failed to add user via X-UI API")

        vless_string = generate_vless_key(
            user_uuid=new_uuid,
            product_name=product.name,
            user_id=user_id,
            server_config=server_config
        )

        #
        subscription_token = await db.add_vless_key(
            user_id=user_id,
            order_id=order_id,
            vless_key=vless_string,
            expires_at=expires_at
        )

        # CRM: Уведомление о покупке ключа
        await crm.notify_key_purchased(
            bot=bot,
            user_id=user_id,
            product_name=product.name,
            amount=product.price,
            expires_at=expires_at.strftime('%Y-%m-%d %H:%M')
        )

        log.info(f"Successfully issued key {new_uuid} for order {order_id} on server {server_config.name}")
        return True, subscription_token #

    except Exception as e:
        log.error(f"Failed to issue key for order {order_id} (user {user_id}): {e}")
        try:
            for admin_id in settings.get_admin_ids:
                await bot.send_message(
                    admin_id,
                    f"⚠️ **СБОЙ ВЫДАЧИ КЛЮЧА** ⚠️\n\n"
                    f"Не удалось выдать ключ для заказа #{order_id} (Пользователь: {user_id}, Страна: {country}).\n"
                    f"Ошибка: {e}\n\n"
                    "**Требуется ручное вмешательство!**",
                    parse_mode="Markdown"
                )
        except Exception as admin_notify_e:
            log.error(f"Failed to notify admin about failure: {admin_notify_e}")

        return False, None


async def issue_trial_key(bot: Bot, user_id: int, first_name: str = None, force: bool = False) -> str | None:
    """
    Выдает ОДНОРАЗОВЫЙ пробный ключ (Модель 2: ссылка-подписка).

    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        first_name: Имя пользователя (опционально)
        force: Если True, выдаёт триал даже если пользователь уже получал

    Returns:
        subscription_url при успехе, None при ошибке
    """
    try:
        if not force:
            has_trial = await db.check_trial_status(user_id)
            if has_trial:
                log.warning(f"Пользователь {user_id} уже получал пробный ключ.")
                return None

        finland_servers = [s for s in settings.XUI_SERVERS if s.country == "Финляндия"]
        if not finland_servers:
            log.error("Не найдены серверы для Финляндии в конфиге для выдачи триала.")
            raise ValueError("Конфигурация для пробного периода не найдена.")
        server_config = finland_servers[0]

        new_uuid = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(days=1)
        trial_duration_days = 1

        api_success = await vpn_api.add_vless_user(
            server_config=server_config,
            user_id=user_id,
            days=trial_duration_days,
            new_uuid=new_uuid
        )

        if not api_success:
            raise Exception("Failed to add trial user via X-UI API")

        vless_string = generate_vless_key(
            user_uuid=new_uuid,
            product_name="Пробный",
            user_id=user_id,
            server_config=server_config
        )

        #
        subscription_token = await db.add_vless_key(
            user_id=user_id,
            order_id=None, #
            vless_key=vless_string,
            expires_at=expires_at
        )

        await db.mark_trial_received(user_id)

        #
        subscription_url = f"{settings.WEBHOOK_HOST}/sub/{subscription_token}"

        # CRM: Уведомление о взятии триала
        await crm.notify_trial_taken(
            bot=bot,
            user_id=user_id,
            expires_at=expires_at.strftime('%Y-%m-%d %H:%M')
        )

        log.info(f"Пробный ключ {new_uuid} успешно выдан (как подписка) пользователю {user_id} на сервере {server_config.name}")
        return subscription_url

    except Exception as e:
        log.error(f"Ошибка выдачи пробного ключа для {user_id}: {e}")
        try:
            for admin_id in settings.get_admin_ids:
                await bot.send_message(
                    admin_id,
                    f"⚠️ **СБОЙ ВЫДАЧИ ТРИАЛА** ⚠️\n\n"
                    f"Не удалось выдать пробный ключ пользователю {user_id}.\n"
                    f"Ошибка: {e}\n\n"
                    "**Требуется проверить логи.**",
                    parse_mode="Markdown"
                )
        except Exception as admin_notify_e:
            log.error(f"Не удалось уведомить админа о сбое триала: {admin_notify_e}")

        return None


# Константа для реферального бонуса
REFERRAL_BONUS_DAYS = 7


async def issue_referral_key(bot: Bot, user_id: int, days: int) -> str | None:
    """
    Выдает ключ за бонусные дни реферальной программы.

    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        days: Количество дней

    Returns:
        subscription_url при успехе, None при ошибке
    """
    try:
        # Списываем дни с баланса
        success, remaining = await db.use_referral_balance(user_id, days)
        if not success:
            log.warning(f"Недостаточно бонусных дней у пользователя {user_id}")
            return None

        # Берём первый сервер Финляндии
        finland_servers = [s for s in settings.XUI_SERVERS if s.country == "Финляндия"]
        if not finland_servers:
            log.error("Не найдены серверы для Финляндии")
            # Возвращаем дни обратно
            await db.add_referral_balance(user_id, days)
            return None
        server_config = finland_servers[0]

        new_uuid = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(days=days)

        api_success = await vpn_api.add_vless_user(
            server_config=server_config,
            user_id=user_id,
            days=days,
            new_uuid=new_uuid
        )

        if not api_success:
            # Возвращаем дни обратно
            await db.add_referral_balance(user_id, days)
            raise Exception("Failed to add user via X-UI API")

        vless_string = generate_vless_key(
            user_uuid=new_uuid,
            product_name="Реферальный",
            user_id=user_id,
            server_config=server_config
        )

        subscription_token = await db.add_vless_key(
            user_id=user_id,
            order_id=None,
            vless_key=vless_string,
            expires_at=expires_at
        )

        subscription_url = f"{settings.WEBHOOK_HOST}/sub/{subscription_token}"

        log.info(f"Реферальный ключ {new_uuid} выдан пользователю {user_id} на {days} дней")
        return subscription_url

    except Exception as e:
        log.error(f"Ошибка выдачи реферального ключа для {user_id}: {e}")
        return None


async def extend_key_with_referral_bonus(user_id: int, key_id: int, days: int) -> datetime.datetime | None:
    """
    Продлевает ключ за бонусные дни реферальной программы.

    Args:
        user_id: ID пользователя
        key_id: ID ключа для продления
        days: Количество дней

    Returns:
        Новая дата истечения при успехе, None при ошибке
    """
    try:
        # Списываем дни с баланса
        success, remaining = await db.use_referral_balance(user_id, days)
        if not success:
            log.warning(f"Недостаточно бонусных дней у пользователя {user_id}")
            return None

        # Получаем ключ
        key = await db.get_key_by_id(key_id)
        if not key or key.user_id != user_id:
            # Возвращаем дни обратно
            await db.add_referral_balance(user_id, days)
            return None

        # Вычисляем новую дату
        now = datetime.datetime.now()
        start_date = max(now, key.expires_at)
        new_expiry = start_date + datetime.timedelta(days=days)

        # Обновляем в БД
        await db.update_key_expiry(key_id, new_expiry)

        # Синхронизируем на панели X-UI
        try:
            vless_key_str = key.vless_key or ""
            client_uuid = vless_key_str.split('vless://')[1].split('@')[0]
            server_host = vless_key_str.split('@')[1].split(':')[0]
            server_config = next((s for s in settings.XUI_SERVERS if s.vless_server == server_host), None)

            if server_config:
                new_expiry_ts = int(new_expiry.timestamp() * 1000)
                updated = await vpn_api.update_vless_user_expiry(server_config, client_uuid, new_expiry_ts)
                if not updated:
                    # Фолбэк: пересоздаём клиента
                    await vpn_api.delete_vless_user(server_config, client_uuid)
                    delta_days = max(1, int((new_expiry - datetime.datetime.now()).total_seconds() // 86400))
                    await vpn_api.add_vless_user(server_config, user_id=user_id, days=delta_days, new_uuid=client_uuid)
        except Exception as sync_e:
            log.error(f"Ошибка синхронизации продления на панели: {sync_e}")

        log.info(f"Ключ {key_id} продлён на {days} дней за бонусы. Новая дата: {new_expiry}")
        return new_expiry

    except Exception as e:
        log.error(f"Ошибка продления ключа за бонусы для {user_id}: {e}")
        return None


async def process_referral_bonus(bot: Bot, referrer_id: int, referred_id: int) -> bool:
    """
    Начисляет бонусные дни на баланс реферера за первую покупку реферала.

    Args:
        bot: Экземпляр бота для отправки уведомления
        referrer_id: ID реферера (кто пригласил)
        referred_id: ID реферала (кто купил)

    Returns:
        True если бонус начислен
    """
    try:
        # Начисляем бонусные дни на баланс
        new_balance = await db.add_referral_balance(referrer_id, REFERRAL_BONUS_DAYS)

        notification_text = (
            f"🎉 <b>Реферальный бонус!</b>\n\n"
            f"Ваш друг совершил первую покупку!\n\n"
            f"🎁 Вам начислено: <b>+{REFERRAL_BONUS_DAYS} дней</b>\n"
            f"💰 Ваш баланс: <b>{new_balance} дней</b>\n\n"
            f"Используйте бонусные дни для покупки или продления подписки в меню реферальной программы!"
        )

        try:
            await bot.send_message(
                referrer_id,
                notification_text,
                parse_mode="HTML"
            )
            log.info(f"Реферальный бонус +{REFERRAL_BONUS_DAYS} дней начислен на баланс пользователя {referrer_id} за реферала {referred_id}. Новый баланс: {new_balance}")
        except Exception as send_e:
            log.warning(f"Не удалось отправить уведомление о бонусе пользователю {referrer_id}: {send_e}")

        return True

    except Exception as e:
        log.error(f"Ошибка начисления реферального бонуса для {referrer_id}: {e}")
        return False


async def handle_payment_logic(bot: Bot, order_id: int, metadata: dict) -> tuple[bool, str, str | None]:
    """
    Универсальная логика обработки УСПЕШНОГО платежа (и ЮKassa, и Crypto).
    (Модель 2: 1 ключ = 1 подписка)
    Возвращает (Успех, Текст сообщения, Тип_Операции ["new_key" или "renewal"]).
    """
    try:
        order = await db.get_order_by_id(order_id)
        if not order:
            log.error(f"[PaymentLogic] Ошибка: Заказ {order_id} не найден.")
            return False, "Ошибка: Заказ не найден.", None

        renewal_key_id_str = metadata.get("renewal_key_id")
        user_id = order.user_id
        product_id = order.product_id

        # --- ЛОГИКА ПРОДЛЕНИЯ ---
        if renewal_key_id_str:
            renewal_key_id = int(renewal_key_id_str)
            log.info(f"[PaymentLogic] Заказ {order_id} определен как ПРОДЛЕНИЕ ключа {renewal_key_id}.")

            key_to_renew = await db.get_key_by_id(renewal_key_id)
            product = await db.get_product_by_id(product_id)

            if not key_to_renew or not product or key_to_renew.user_id != user_id:
                raise ValueError("Ключ или продукт для продления не найден или не принадлежит вам.")

            now = datetime.datetime.now()
            start_date = max(now, key_to_renew.expires_at)
            new_expiry_date = start_date + datetime.timedelta(days=product.duration_days)

            await db.update_key_expiry(renewal_key_id, new_expiry_date)
            log.info(f"Ключ {renewal_key_id} продлен до {new_expiry_date}.")

            # Синхронизируем срок действия на панели X-UI
            try:
                vless_key_str = key_to_renew.vless_key or ""
                # Извлекаем UUID и сервер из vless://<uuid>@<server>:<port>
                client_uuid = vless_key_str.split('vless://')[1].split('@')[0]
                server_host = vless_key_str.split('@')[1].split(':')[0]
                server_config = next((s for s in settings.XUI_SERVERS if s.vless_server == server_host), None)
                if server_config:
                    new_expiry_ts = int(new_expiry_date.timestamp() * 1000)
                    updated = await vpn_api.update_vless_user_expiry(server_config, client_uuid, new_expiry_ts)
                    if not updated:
                        # Фолбэк: удалить и создать клиента заново с нужным сроком
                        deleted = await vpn_api.delete_vless_user(server_config, client_uuid)
                        if not deleted:
                            log.error(f"[Renewal] Не удалось удалить клиента {client_uuid} на {server_config.name} для продления.")
                        # Ставим дни так, чтобы конечная дата была близка к new_expiry_date
                        delta_days = max(1, int((new_expiry_date - datetime.datetime.now()).total_seconds() // 86400))
                        readded = await vpn_api.add_vless_user(server_config, user_id=user_id, days=delta_days, new_uuid=client_uuid)
                        if readded:
                            log.info(f"[Renewal] Клиент {client_uuid} пересоздан c новой датой на {server_config.name}")
                        else:
                            log.error(f"[Renewal] Не удалось пересоздать клиента {client_uuid} на {server_config.name}")
                else:
                    log.error(f"[Renewal] Не найден server_config для {server_host}; панель не обновлена.")
            except Exception as sync_e:
                log.error(f"[Renewal] Ошибка синхронизации продления на панели: {sync_e}")

            # Сообщение пользователю
            message_text = (
                f"✅ <b>Ключ успешно продлен!</b>\n\n"
                f"Тариф: <b>{product.name}</b>\n"
                f"Новый срок действия: до <code>{new_expiry_date.strftime('%Y-%m-%d %H:%M')}</code>\n\n"
                "Ваш ключ остался прежним, обновите его в приложении."
            )
            return True, message_text, "renewal"  #

        # --- ⬇️ ⬇️ ⬇️ ИЗМЕНЕНИЕ (ЗАПРОС 1) ⬇️ ⬇️ ⬇️ ---
        # --- ЛОГИКА ВЫДАЧИ НОВОГО КЛЮЧА ---
        else:
            log.info(f"[PaymentLogic] Заказ {order_id} определен как НОВАЯ ПОКУПКА.")

            # Проверяем, является ли это кастомным платежом (без выдачи ключа)
            product = await db.get_product_by_id(product_id)
            if product and product.name == "Кастомный платеж":
                # Это кастомный платеж от админа - не выдаем ключ
                log.info(f"[PaymentLogic] Заказ {order_id} - кастомный платеж, ключ не выдается.")
                message_text = (
                    f"✅ <b>Оплата прошла успешно!</b>\n\n"
                    f"Сумма: <b>{order.amount} ₽</b>\n\n"
                    "Спасибо за оплату!"
                )

                # Уведомляем в CRM
                await crm.send_to_crm(
                    bot=bot,
                    user_id=user_id,
                    message=f"💰 <b>Кастомный платеж оплачен</b>\n\n"
                            f"Сумма: <b>{order.amount} ₽</b>\n"
                            f"Заказ: <code>{order_id}</code>"
                )

                return True, message_text, None

            # Обычная покупка - выдаем ключ
            country = metadata.get("country")
            if not country:
                log.error(f"!!! ОШИБКА: Не найдена страна в metadata для заказа {order_id}")
                if product and product.country:
                    country = product.country
                else:
                    country = settings.XUI_SERVERS[0].country if settings.XUI_SERVERS else "Unknown"
                if country == "Unknown":
                    return False, "Критическая ошибка: Не удалось определить страну сервера. Свяжитесь с поддержкой.", None

            success, subscription_token = await issue_key_to_user(
                bot=bot,
                user_id=user_id,
                product_id=product_id,
                order_id=order_id,
                country=country
            )

            if success:
                subscription_url = f"{settings.WEBHOOK_HOST}/sub/{subscription_token}"

                # Обрабатываем реферальный бонус
                try:
                    referrer_id = await db.mark_referral_purchased(user_id)
                    if referrer_id:
                        # Это первая покупка реферала - начисляем бонус рефереру
                        await process_referral_bonus(bot, referrer_id, user_id)
                except Exception as ref_e:
                    log.error(f"Ошибка при обработке реферального бонуса для user {user_id}: {ref_e}")

                message_text = (
                    f"✅ <b>Оплата прошла успешно!</b>\n\n"
                    f"Ваш ключ 👇👇👇\n\n"
                    f"<code>{subscription_url}</code>\n\n"
                    f"1. Нажмите на ключ 👆👆👆, чтобы скопировать его\n"
                    f"2. Выберите тип устройства"
                )
                return True, message_text, "new_key"
            else:
                message_text = (
                    "❌ **Ошибка выдачи ключа**\n\n"
                    "Оплата прошла, но при создании ключа произошла ошибка.\n"
                    "Мы уже уведомили администратора. Пожалуйста, свяжитесь с поддержкой."
                )
                return False, message_text, None
        # --- ⬆️ ⬆️ ⬆️ КОНЕЦ ИЗМЕНЕНИЯ ⬆️ ⬆️ ⬆️

    except Exception as e:
        log.error(f"Критическая ошибка в handle_payment_logic для заказа {order_id}: {e}")
        return False, "❌ **Критическая ошибка**\n\nПроизошла непредвиденная ошибка при обработке вашего платежа. Свяжитесь с поддержкой.", None