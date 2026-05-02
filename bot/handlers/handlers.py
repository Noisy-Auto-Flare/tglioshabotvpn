import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Union

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
from backend.services.payment_service import PaymentService
from backend.services.payments.cryptobot import cryptobot_service
from backend.services.payments.cryptomus import cryptomus_service
from backend.services.payments.platega import platega_service
from backend.services.payments.abstract import ton_service
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import (
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    User,
    VPNKey,
)
from backend.services.tasks import (
    generate_mock_config,
    parse_payment_payload,
    process_successful_payment,
)
from backend.services.vpn import vpn_service
from backend.core.config import settings
from bot.keyboards.keyboards import (
    get_main_menu,
    get_buy_menu,
    get_tariff_list,
    get_payment_methods,
    get_profile_main_keyboard,
    get_info_menu_keyboard,
    get_back_to_main,
    get_deposit_methods,
    get_deposit_payment_methods,
    get_reset_key_confirm_keyboard,
    get_sub_management_keyboard,
    get_my_subscriptions_keyboard,
)
from bot.services.renderer import render_screen, safe_edit

class DepositStates(StatesGroup):
    waiting_for_amount = State()

logger = logging.getLogger(__name__)
router = Router()

async def _check_channel_sub(bot, user_id: int) -> bool:
    """Checks if user is subscribed to the required channel."""
    if not settings.REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(settings.REQUIRED_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Error checking channel sub for {user_id}: {e}")
        return False

async def _get_user_by_tg(db: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def _show_profile(event: Union[Message, CallbackQuery], db: AsyncSession, user: User) -> None:
    now = datetime.now()
    sub_stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now,
        )
        .order_by(Subscription.end_date.desc())
        .limit(1)
    )
    sub_result = await db.execute(sub_stmt)
    sub = sub_result.scalar_one_or_none()

    vpn_key = None
    if sub:
        vpn_stmt = (
            select(VPNKey)
            .where(
                VPNKey.user_id == user.id, 
                VPNKey.subscription_id == sub.id,
                VPNKey.is_active == True
            )
            .order_by(VPNKey.id.desc())
            .limit(1)
        )
        vpn_result = await db.execute(vpn_stmt)
        vpn_key = vpn_result.scalar_one_or_none()

    status_text = '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Отсутствует'
    vpn_info = "Отсутствует"
    if sub:
        remaining = sub.end_date - now
        days = remaining.days
        hours = remaining.seconds // 3600
        status_text = f'<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji> Активна (осталось {days} дн. {hours} ч.)'
        
        
        if vpn_key and vpn_key.is_active:
            vpn_info = f"{vpn_key.config}"
        elif vpn_key:
            vpn_info = "Ключ в процессе создания..."
        else:
            vpn_info = "Ключ еще не получен."

    await render_screen(
        event,
        db,
        "profile_main",
        keyboard=get_profile_main_keyboard(),
        telegram_id=user.telegram_id,
        balance=user.balance,
        status_text=status_text,
        vpn_info=vpn_info,
    )

@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession):
    if not message.from_user:
        return
    
    user = await _get_user_by_tg(db, message.from_user.id)
    
    # Check if user is new and has a referral code
    if not user and message.text and len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        referral_code = str(uuid.uuid4())[:8]
        referred_by = None
        
        ref_stmt = select(User).where(User.referral_code == ref_code)
        inviter = (await db.execute(ref_stmt)).scalar_one_or_none()
        
        if inviter:
            referred_by = inviter.id
            # Fix referral: +2 days for inviter
            sub_stmt = select(Subscription).where(
                Subscription.user_id == inviter.id,
                Subscription.status == SubscriptionStatus.ACTIVE
            ).order_by(Subscription.end_date.desc()).limit(1)
            inviter_sub = (await db.execute(sub_stmt)).scalar_one_or_none()
            
            if inviter_sub:
                inviter_sub.end_date += timedelta(days=2)
                # Also update VPNKey expiration
                vpn_stmt = select(VPNKey).where(VPNKey.subscription_id == inviter_sub.id)
                vpn_keys = (await db.execute(vpn_stmt)).scalars().all()
                for vpn_key in vpn_keys:
                    vpn_key.expire_at = inviter_sub.end_date
                    # Sync with RemnaWave panel
                    if vpn_key.uuid:
                        try:
                            # Use asyncio.to_thread for synchronous curl-based calls
                            await asyncio.to_thread(
                                vpn_service.update_user_expiration,
                                vpn_key.uuid,
                                inviter_sub.end_date
                            )
                        except Exception as vpn_err:
                            logger.error(f"Failed to sync expiration with RemnaWave for user {inviter.id}: {vpn_err}")
                
                notification_msg = (
                    f"<tg-emoji emoji-id=\"5222444124698853913\">🎁</tg-emoji> <b>По вашей ссылке перешел новый пользователь!</b>\n\n"
                    f"<tg-emoji emoji-id=\"5203996991054432397\">🎁</tg-emoji> Вам начислено <b>+2 дня</b> подписки"
                )
            else:
                notification_msg = (
                    f"<tg-emoji emoji-id=\"5222444124698853913\">🎁</tg-emoji> <b>По вашей ссылке перешел новый пользователь!</b>\n\n"
                    f"К сожалению, у вас нет активной подписки для начисления бонусных дней."
                )

            # Notify inviter
            if message.bot:
                try:
                    await message.bot.send_message(
                        inviter.telegram_id,
                        notification_msg,
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
        
        # Create user immediately to save referral info even if not subbed yet
        user = User(
            telegram_id=message.from_user.id,
            referral_code=referral_code,
            referred_by=referred_by,
        )
        db.add(user)
        await db.commit()
        # Refresh user from DB
        user = await _get_user_by_tg(db, message.from_user.id)

    # 1. Check channel sub
    is_subbed = await _check_channel_sub(message.bot, message.from_user.id)
    if not is_subbed:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{settings.REQUIRED_CHANNEL.lstrip('@')}")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub_status")]
        ])
        await render_screen(message, db, "required_sub", keyboard=keyboard, channel=settings.REQUIRED_CHANNEL)
        return

    if not user:
        referral_code = str(uuid.uuid4())[:8]
        user = User(
            telegram_id=message.from_user.id,
            referral_code=referral_code,
            referred_by=None,
        )
        db.add(user)
        await db.commit()

    await render_screen(message, db, "main_menu", keyboard=get_main_menu(), name=message.from_user.first_name)

@router.callback_query(F.data == "check_sub_status")
async def check_sub_status(callback: CallbackQuery, db: AsyncSession):
    is_subbed = await _check_channel_sub(callback.bot, callback.from_user.id)
    if is_subbed:
        await callback.answer("✅ Спасибо за подписку!", show_alert=True)
        await open_main_menu(callback, db)
    else:
        await callback.answer("❌ Вы все еще не подписаны на канал!", show_alert=True)

# --- Admin Broadcast ---
@router.message(F.text.startswith("/broadcast"), F.from_user.id.in_(settings.ADMIN_IDS))
async def cmd_broadcast(message: Message, db: AsyncSession):
    if not message.text or not message.bot: return
    
    # Используем html_text для сохранения форматирования и премиум-эмодзи
    html_text = message.html_text
    parts = html_text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.answer("❌ Использование: /broadcast [текст]")
        return
    
    broadcast_html = parts[1]
    
    # Get all users
    stmt = select(User.telegram_id)
    res = await db.execute(stmt)
    user_ids = res.scalars().all()
    
    count = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, broadcast_html, parse_mode="HTML")
            count += 1
            await asyncio.sleep(0.05)  # Anti-flood
        except Exception:
            continue
    
    await message.answer(f"✅ Рассылка завершена! Отправлено {count} пользователям.")

@router.message(F.from_user.id.in_(settings.ADMIN_IDS))
async def admin_broadcast_copy(message: Message, db: AsyncSession):
    # If admin sends any message (photo, video, etc) - offer to broadcast it
    # But only if it's not a command
    if message.text and message.text.startswith("/"):
        return
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data=f"start_broadcast_{message.message_id}")]
    ])
    await message.reply("Вы хотите разослать это сообщение всем пользователям?", reply_markup=keyboard)

@router.callback_query(F.data.startswith("start_broadcast_"), F.from_user.id.in_(settings.ADMIN_IDS))
async def process_broadcast(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.bot or not callback.message: return
    msg_id = int(callback.data.split("_")[-1])
    
    # Get all users
    stmt = select(User.telegram_id)
    res = await db.execute(stmt)
    user_ids = res.scalars().all()
    
    count = 0
    for uid in user_ids:
        try:
            await callback.bot.copy_message(uid, callback.from_user.id, msg_id)
            count += 1
            await asyncio.sleep(0.05)  # Anti-flood
        except Exception:
            continue
    
    await callback.answer(f"✅ Рассылка завершена! Отправлено {count} пользователям.", show_alert=True)
    if isinstance(callback.message, Message):
        await callback.message.delete()

@router.callback_query(F.data == "main_menu")
async def open_main_menu(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "main_menu", keyboard=get_main_menu(), name=callback.from_user.first_name)
    await callback.answer()

@router.callback_query(F.data == "buy_menu")
async def open_buy_menu(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "buy_menu", keyboard=get_buy_menu())
    await callback.answer()

@router.callback_query(F.data == "tariff_list")
async def open_tariff_list(callback: CallbackQuery, db: AsyncSession):
    await render_screen(callback, db, "tariff_list", keyboard=get_tariff_list())
    await callback.answer()

@router.callback_query(F.data == "trial_activate")
async def process_trial(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    
    stmt = select(Subscription).where(Subscription.user_id == user.id, Subscription.plan == "trial")
    if (await db.execute(stmt)).scalar_one_or_none():
        await callback.answer("❌ Пробный период уже активирован!", show_alert=True)
        return

    now = datetime.now()
    end_date = now + timedelta(days=3)
    sub = Subscription(user_id=user.id, plan="trial", traffic_limit_gb=30, start_date=now, end_date=end_date)
    db.add(sub)
    await db.flush()

    vpn_data = await asyncio.to_thread(vpn_service.create_user_and_get_link, user.telegram_id, 30, 3)
    if vpn_data:
        db.add(VPNKey(
            user_id=user.id, 
            subscription_id=sub.id, 
            uuid=vpn_data["uuid"],
            config=vpn_data["link"], 
            expire_at=end_date, 
            is_active=True
        ))
    else:
        db.add(VPNKey(
            user_id=user.id, 
            subscription_id=sub.id, 
            config="Error", 
            expire_at=end_date, 
            is_active=False,
            error_message="RemnaWave API error"
        ))
    await db.commit()
    
    await callback.answer("✅ Пробный период активирован на 3 дня!", show_alert=True)
    await _show_profile(callback, db, user)

@router.callback_query(F.data == "profile_main")
async def open_profile_main(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    await _show_profile(callback, db, user)
    await callback.answer()

@router.callback_query(F.data == "my_subscriptions")
async def open_my_subscriptions(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # Get all active subscriptions
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.end_date > datetime.now()
    ).order_by(Subscription.end_date.asc())
    
    sub_result = await db.execute(sub_stmt)
    subscriptions = sub_result.scalars().all()

    await render_screen(
        callback, db, "my_subscriptions",
        keyboard=get_my_subscriptions_keyboard(list(subscriptions))
    )
    await callback.answer()

@router.callback_query(F.data.startswith("manage_sub_"))
async def manage_subscription(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    sub_id = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    sub_stmt = select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()

    if not sub:
        await callback.answer("❌ Подписка не найдена.", show_alert=True)
        return

    plan_label = settings.PLANS.get(sub.plan, {}).get("label", f"Подписка #{sub.id}")
    end_date_str = sub.end_date.strftime("%d.%m.%Y")

    # Get config link for this sub
    vpn_stmt = select(VPNKey).where(
        VPNKey.subscription_id == sub.id,
        VPNKey.is_active == True
    ).order_by(VPNKey.id.desc()).limit(1)
    vpn_key = (await db.execute(vpn_stmt)).scalar_one_or_none()
    config_url = vpn_key.config if vpn_key else None

    await render_screen(
        callback, db, "sub_management",
        keyboard=get_sub_management_keyboard(sub.id, config_url),
        plan_label=plan_label,
        end_date=end_date_str
    )
    await callback.answer()

@router.callback_query(F.data.startswith("get_key_"))
async def process_get_key(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    sub_id = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # Get VPN key for this sub
    vpn_stmt = select(VPNKey).where(
        VPNKey.subscription_id == sub_id,
        VPNKey.is_active == True
    ).order_by(VPNKey.id.desc()).limit(1)
    vpn_key = (await db.execute(vpn_stmt)).scalar_one_or_none()

    if vpn_key and vpn_key.config and callback.message:
        await callback.message.answer(f"<tg-emoji emoji-id=\"5307843983102204243\">🔑</tg-emoji> <b>Ваш ключ для выбранной подписки:</b>\n\n<code>{vpn_key.config}</code>", parse_mode="HTML")
        await callback.answer()
    else:
        await callback.answer("❌ Ключ еще не создан или неактивен.", show_alert=True)

@router.callback_query(F.data.startswith("reset_key_confirm_"))
async def confirm_reset_key(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    sub_id = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    sub_stmt = select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()

    if not sub:
        await callback.answer("❌ Подписка не найдена.", show_alert=True)
        return

    remaining = 3 - sub.reset_count
    if remaining <= 0:
        await callback.answer("❌ Лимит сбросов исчерпан.", show_alert=True)
        return

    await render_screen(
        callback, db, "reset_key_confirm",
        keyboard=get_reset_key_confirm_keyboard(sub.id),
        remaining_resets=remaining
    )
    await callback.answer()

@router.callback_query(F.data.startswith("reset_key_execute_"))
async def execute_reset_key(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    sub_id = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # 1. Get sub and key
    sub_stmt = select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user.id)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()

    if not sub or sub.reset_count >= 3:
        await callback.answer("❌ Сброс невозможен.", show_alert=True)
        return

    vpn_stmt = select(VPNKey).where(
        VPNKey.subscription_id == sub.id,
        VPNKey.is_active == True
    ).order_by(VPNKey.id.desc()).limit(1)
    old_key = (await db.execute(vpn_stmt)).scalar_one_or_none()

    # 2. Delete old user
    if old_key and old_key.uuid:
        await asyncio.to_thread(vpn_service.delete_user, old_key.uuid)
        old_key.is_active = False
        await db.commit()

    # 3. Create new
    days_left = max(1, (sub.end_date - datetime.now()).days)
    vpn_data = await asyncio.to_thread(
        vpn_service.create_user_and_get_link,
        user.telegram_id,
        sub.traffic_limit_gb or 30,
        days_left,
        sub_id=sub.id
    )

    if vpn_data:
        new_key = VPNKey(
            user_id=user.id,
            subscription_id=sub.id,
            uuid=vpn_data["uuid"],
            config=vpn_data["link"],
            expire_at=sub.end_date,
            is_active=True
        )
        db.add(new_key)
        sub.reset_count += 1
        await db.commit()
        await callback.answer("✅ Ключ успешно сброшен!", show_alert=True)
        # Return to management
        await manage_subscription(callback, db)
    else:
        await callback.answer("❌ Ошибка при создании ключа.", show_alert=True)

@router.callback_query(F.data.startswith("extend_sub_"))
async def extend_subscription(callback: CallbackQuery, db: AsyncSession):
    # For now just redirect to tariff list as requested "Добавить подписку -> Переброс в меню выбора тарифов"
    # But specifically for extension we might want to handle it differently later
    await open_tariff_list(callback, db)

@router.callback_query(F.data == "statistics")
async def open_statistics(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    # Подсчет покупок
    orders_stmt = select(func.count(Payment.id)).where(Payment.user_id == user.id, Payment.status == PaymentStatus.SUCCESS)
    total_orders = (await db.execute(orders_stmt)).scalar() or 0

    # Активная подписка
    sub_stmt = select(Subscription).where(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.ACTIVE).order_by(Subscription.end_date.desc()).limit(1)
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()
    
    days_left = 0
    total_gb = 0
    if sub:
        days_left = max(0, (sub.end_date - datetime.now()).days)
        total_gb = sub.traffic_limit_gb or 0

    await render_screen(
        callback, db, "statistics",
        keyboard=get_back_to_main(),
        user_id=user.telegram_id,
        status=f'<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji> Активна' if sub else f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Отсутствует',
        days_left=days_left,
        total_orders=total_orders,
        protocol_type="VLESS/Reality",
        used_gb=0,
        total_gb=total_gb if total_gb > 0 else "∞"
    )
    await callback.answer()

@router.callback_query(F.data == "deposit_menu")
async def open_deposit_menu(callback: CallbackQuery, db: AsyncSession, state: FSMContext):
    await state.clear()
    await render_screen(callback, db, "deposit_menu", keyboard=get_deposit_methods())
    await callback.answer()

@router.callback_query(F.data == "dep_custom_amt")
async def process_custom_amount_start(callback: CallbackQuery, db: AsyncSession, state: FSMContext):
    await state.set_state(DepositStates.waiting_for_amount)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Отмена", callback_data="deposit_menu")]
    ])
    if isinstance(callback.message, Message):
        await safe_edit(
            callback.message,
            "<tg-emoji emoji-id=\"5445221832074483553\">💰</tg-emoji> <b>Пополнение баланса на произвольную сумму</b>\n\n"
            "Введите сумму пополнения (целое число от 10 до 50000):",
            reply_markup=keyboard
        )
    await callback.answer()

@router.message(DepositStates.waiting_for_amount)
async def process_custom_amount_input(message: Message, db: AsyncSession, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите корректное число.")
        return
    
    amount = int(message.text)
    if amount < 10 or amount > 50000:
        await message.answer("❌ Сумма должна быть от 10 до 50 000 руб.")
        return
    
    await state.clear()
    await render_screen(
        message, db, "payment", 
        keyboard=get_deposit_payment_methods(amount),
        plan_label="Пополнение баланса",
        price=amount
    )

@router.callback_query(F.data.startswith("dep_amt_"))
async def process_dep_amount(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    amount = int(callback.data.split("_")[-1])
    await render_screen(
        callback, db, "payment", 
        keyboard=get_deposit_payment_methods(amount),
        plan_label="Пополнение баланса",
        price=f"<b>{amount} RUB</b>"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("dep_sbp_"))
async def process_dep_sbp(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    amount = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    payment_service = PaymentService(db)
    payment = await payment_service.create_payment(
        user_id=user.id,
        tariff_id=f"dep_{amount}",
        provider="sbp",
        amount=amount
    )
    
    pay_url = await platega_service.create_payment(
        amount=amount,
        order_id=str(payment.id)
    )
    
    if not pay_url:
        await callback.answer("❌ Ошибка Platega. Попробуйте позже.", show_alert=True)
        return

    payment.external_id = str(payment.id)
    await db.commit()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5265074015868822600", text="Оплатить через СБП", url=pay_url)],
        [InlineKeyboardButton(icon_custom_emoji_id="5346300789558101141", text="Проверить оплату", callback_data=f"check_pay_{payment.id}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data=f"dep_amt_{amount}")]
    ])
    
    text = (
        f"<tg-emoji emoji-id=\"5188481279963715781\">📲</tg-emoji> <b>Оплата через СБП (Platega)</b>\n\n"
        f"Тариф: <b>Пополнение баланса</b>\n"
        f"К оплате: <b>{amount} RUB</b>\n\n"
        f"<tg-emoji emoji-id=\"5346300789558101141\">📲</tg-emoji> После оплаты нажмите кнопку \"Проверить оплату\"\n"
        f"Нажмите кнопку ниже, чтобы перейти к оплате:"
    )
    if isinstance(callback.message, Message):
        await safe_edit(callback.message, text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("dep_cryptobot_"))
async def process_dep_cryptobot(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    amount = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    amount_usd = float(amount) / settings.USD_RUB_RATE
    invoice = await cryptobot_service.create_invoice(
        amount=amount_usd,
        payload=f"{user.id}:dep_{amount}",
        currency="USD"
    )
    
    if not invoice:
        await callback.answer("❌ Ошибка CryptoBot.", show_alert=True)
        return

    payment_service = PaymentService(db)
    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=f"dep_{amount}",
        provider="cryptobot",
        amount=amount,
        external_id=str(invoice["invoice_id"])
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5361836987642815474", text="Оплатить", url=invoice["pay_url"])],
        [InlineKeyboardButton(icon_custom_emoji_id="5346300789558101141", text="Проверить оплату", callback_data=f"check_pay_{invoice['invoice_id']}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data=f"dep_amt_{amount}")]
    ])
    
    if isinstance(callback.message, Message):
        await safe_edit(
            callback.message,
            f"<tg-emoji emoji-id=\"5361836987642815474\">💎</tg-emoji> <b>Счет CryptoBot создан!</b>\n\n"
            f"Тариф: <b>Пополнение баланса</b>\n"
            f"Сумма: <b>{amount_usd:.2f} USDT</b>\n\n"
            f"<tg-emoji emoji-id=\"5346300789558101141\">📲</tg-emoji> <b>После оплаты нажмите кнопку \"Проверить оплату\"\n\n</b>"
            f"Нажмите кнопку ниже для оплаты:",
            reply_markup=keyboard
        )
    await callback.answer()

@router.callback_query(F.data.startswith("dep_cryptomus_"))
async def process_dep_cryptomus(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    amount = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    payment_service = PaymentService(db)
    order_id = f"dep_{user.id}_{int(datetime.now().timestamp())}"
    
    invoice = await cryptomus_service.create_invoice(
        amount=float(amount),
        order_id=order_id
    )
    
    if not invoice:
        await callback.answer("❌ Ошибка CryptoMus.", show_alert=True)
        return

    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=f"dep_{amount}",
        provider="cryptomus",
        amount=amount,
        external_id=invoice["uuid"]
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=invoice["url"])],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"dep_amt_{amount}")]
    ])
    
    if isinstance(callback.message, Message):
        await safe_edit(
            callback.message,
            f"<b>💳 Оплата покупки</b>\n\n"
            f"Тариф: <b>Пополнение баланса</b>\n"
            f"Сумма: <b>{amount} RUB</b>\n\n"
            f"💳 Выберите удобный способ оплаты:",
            reply_markup=keyboard
        )
    await callback.answer()

@router.callback_query(F.data.startswith("dep_stars_"))
async def process_dep_stars(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    amount = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    if isinstance(callback.message, Message):
        await callback.message.answer_invoice(
            title="Пополнение баланса",
            description=f"Пополнение на {amount} RUB",
            payload=f"stars_{user.id}_dep_{amount}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"Пополнение на {amount} RUB", amount=amount)]
        )
    await callback.answer()

@router.callback_query(F.data.startswith("dep_ton_"))
async def process_dep_ton(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    amount = int(callback.data.split("_")[-1])
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return

    payment_service = PaymentService(db)
    payment = await payment_service.create_payment(
        user_id=user.id,
        tariff_id=f"dep_{amount}",
        provider="ton",
        amount=amount
    )
    
    ton_info = await ton_service.create_invoice(amount, str(payment.id))
    pay_url = ton_info["pay_url"]
    ton_amount = ton_info.get("ton_amount", "...")
    
    payment.external_id = str(payment.id)
    await db.commit()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5377620962390857342", text="Открыть TON Кошелек", url=pay_url)],
        [InlineKeyboardButton(icon_custom_emoji_id="5346300789558101141", text="Проверить оплату", callback_data=f"check_pay_{payment.id}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data=f"dep_amt_{amount}")]
    ])
    
    text = (
        f"<tg-emoji emoji-id=\"5265151230790884988\">💎</tg-emoji> <b>Оплата через TON Connect</b>\n\n"
        f"Тариф: <b>Пополнение баланса</b>\n"
        f"Сумма: <b>{ton_amount} TON</b> ({amount} RUB)\n\n"
        f"<tg-emoji emoji-id=\"5429405838345265327\">📥</tg-emoji> <b>Адрес для перевода:</b>\n"
        f"<code>UQBO9ldjh-Z8h4PimediLifI5n-QSSf7lg6ND9itKamL1e97</code>\n\n"
        f"<tg-emoji emoji-id=\"5420323339723881652\">💬</tg-emoji> Комментарий (ОБЯЗАТЕЛЬНО): <code>{payment.id}</code>\n\n"
        f"<b>Перед переводом обязательно проверьте сумму, она должна совпадать с указанной выше</b> <tg-emoji emoji-id=\"5274099962655816924\">⚠️</tg-emoji>\n\n"
        f"Нажмите на кнопку ниже или переведите вручную с указанием комментария"
    )
    if isinstance(callback.message, Message):
        await safe_edit(callback.message, text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "info_menu")
async def open_info_menu(callback: CallbackQuery, db: AsyncSession):
    user = await _get_user_by_tg(db, callback.from_user.id)
    config_url = None
    if user:
        # Find latest active sub and its key
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > datetime.now()
        ).order_by(Subscription.end_date.desc()).limit(1)
        sub = (await db.execute(sub_stmt)).scalar_one_or_none()
        
        if sub:
            vpn_stmt = select(VPNKey).where(
                VPNKey.subscription_id == sub.id,
                VPNKey.is_active == True
            ).order_by(VPNKey.id.desc()).limit(1)
            vpn_key = (await db.execute(vpn_stmt)).scalar_one_or_none()
            if vpn_key:
                config_url = vpn_key.config

    await render_screen(callback, db, "info_menu", keyboard=get_info_menu_keyboard(config_url))
    await callback.answer()

@router.callback_query(F.data == "no_active_sub_alert")
async def no_active_sub_alert(callback: CallbackQuery):
    await callback.answer("❌ У вас нет активной подписки!", show_alert=True)

@router.callback_query(F.data == "setup_guides")
async def open_setup_guides(callback: CallbackQuery, db: AsyncSession):
    # This handler might still be needed if some old messages have it, 
    # but new ones should use the URL/alert logic.
    # For now, let's just show an alert or redirect to info_menu.
    await callback.answer("❌ Этот раздел больше не доступен. Используйте кнопку Инструкции в меню управления подпиской.", show_alert=True)

@router.callback_query(F.data == "referral_system")
async def open_referral_system(callback: CallbackQuery, db: AsyncSession):
    if not callback.bot: return
    user = await _get_user_by_tg(db, callback.from_user.id)
    if not user: return
    
    # Get invited count
    stmt = select(func.count(User.id)).where(User.referred_by == user.id)
    count = (await db.execute(stmt)).scalar() or 0
    
    bot_info = await callback.bot.get_me()
    await render_screen(
        callback, db, "referral_system", 
        keyboard=get_back_to_main(), 
        count=count, 
        bot_username=bot_info.username,
        user_id=user.referral_code
    )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_order_"))
async def process_pay_order(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    plan_id = callback.data.split("_")[2]
    plan = settings.PLANS.get(plan_id)
    if not plan: return

    await render_screen(
        callback, db, "payment", 
        keyboard=get_payment_methods(plan_id),
        plan_label=f"<tg-emoji emoji-id=\"5438496463044752972\">⏳</tg-emoji> <b>Оплата подписки на {plan_id} дней</b>",
        price=f"<b>{plan['price']} RUB</b>"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_balance_"))
async def process_pay_balance(callback: CallbackQuery, db: AsyncSession):
    if not callback.data: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    
    if not user or not plan: return
    
    if user.balance < plan["price"]:
        await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
        return
    
    payment_service = PaymentService(db)
    ext_id = f"bal_{user.id}_{int(datetime.now().timestamp())}"
    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="balance",
        amount=plan["price"],
        external_id=ext_id
    )
    
    user.balance -= plan["price"]
    await payment_service.process_success(ext_id)
    
    await callback.answer("✅ Оплата с баланса прошла успешно!", show_alert=True)
    await _show_profile(callback, db, user)

@router.callback_query(F.data.startswith("pay_cryptobot_"))
async def process_pay_cryptobot(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    amount_usd = float(plan["price"]) / settings.USD_RUB_RATE
    invoice = await cryptobot_service.create_invoice(
        amount=amount_usd,
        payload=f"{user.id}:{plan_id}",
        currency="USD"
    )
    
    if not invoice:
        await callback.answer("❌ Ошибка CryptoBot. Попробуйте позже.", show_alert=True)
        return

    payment_service = PaymentService(db)
    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="cryptobot",
        amount=plan["price"],
        external_id=str(invoice["invoice_id"])
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5361836987642815474", text="Оплатить", url=invoice["pay_url"])],
        [InlineKeyboardButton(icon_custom_emoji_id="5346300789558101141", text="Проверить оплату", callback_data=f"check_pay_{invoice['invoice_id']}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    if isinstance(callback.message, Message):
        await safe_edit(
            callback.message,
            f"<tg-emoji emoji-id=\"5361836987642815474\">💎</tg-emoji> <b>Счет CryptoBot создан!</b>\n\n"
            f"Тариф: <b>{plan['label']}</b>\n"
            f"Сумма: <b>{amount_usd:.2f} USDT</b>\n\n"
            f"<tg-emoji emoji-id=\"5346300789558101141\">📲</tg-emoji> <b>После оплаты нажмите кнопку \"Проверить оплату\"\n\n</b>"
            f"Нажмите кнопку ниже для оплаты:",
            reply_markup=keyboard
        )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_stars_"))
async def process_pay_stars(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    stars_amount = int(plan["price"])
    
    if isinstance(callback.message, Message):
        await callback.message.answer_invoice(
            title=f"VPN: {plan['label']}",
            description=f"Подписка на {plan_id} дней",
            payload=f"stars_{user.id}_{plan_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"<b>Оплата подписки на {plan_id} дней</b>", amount=stars_amount)]
        )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_sbp_"))
async def process_pay_sbp(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    amount = plan["price"]
    payment_service = PaymentService(db)
    
    # Create payment record
    payment = await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="sbp",
        amount=amount
    )
    
    # Generate Platega URL
    pay_url = await platega_service.create_payment(
        amount=amount,
        order_id=str(payment.id)
    )
    
    if not pay_url:
        await callback.answer("❌ Ошибка платежной системы. Попробуйте позже.", show_alert=True)
        return

    # Update payment with external_id
    payment.external_id = str(payment.id)
    await db.commit()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5265074015868822600", text="Оплатить через СБП", url=pay_url)],
        [InlineKeyboardButton(icon_custom_emoji_id="5346300789558101141", text="Проверить оплату", callback_data=f"check_pay_{payment.id}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    text = (
        f"<tg-emoji emoji-id=\"5188481279963715781\">📲</tg-emoji> <b>Оплата через СБП (Platega)</b>\n\n"
        f"Тариф: <b>{plan['label']}</b>\n"
        f"К оплате: <b>{amount} RUB</b>\n\n"
        f"<tg-emoji emoji-id=\"5346300789558101141\">📲</tg-emoji> После оплаты нажмите кнопку \"Проверить оплату\"\n"
        f"Нажмите кнопку ниже, чтобы перейти к оплате:"
    )
    if isinstance(callback.message, Message):
        await safe_edit(callback.message, text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_ton_"))
async def process_pay_ton(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    amount = plan["price"]
    payment_service = PaymentService(db)
    
    # Create payment record
    payment = await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="ton",
        amount=amount
    )
    
    # Generate TON payment info
    ton_info = await ton_service.create_invoice(amount, str(payment.id))
    pay_url = ton_info["pay_url"]
    ton_amount = ton_info.get("ton_amount", "...")
    
    # Update payment with external_id
    payment.external_id = str(payment.id)
    await db.commit()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(icon_custom_emoji_id="5377620962390857342", text="Открыть TON Кошелек", url=pay_url)],
        [InlineKeyboardButton(icon_custom_emoji_id="5346300789558101141", text="Проверить оплату", callback_data=f"check_pay_{payment.id}", style="danger")],
        [InlineKeyboardButton(icon_custom_emoji_id="5258236805890710909", text="Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    text = (
        f"<tg-emoji emoji-id=\"5265151230790884988\">💎</tg-emoji> <b>Оплата через TON Connect</b>\n\n"
        f"Тариф: <b>{plan['label']}</b>\n"
        f"Сумма: <b>{ton_amount} TON</b> ({amount} RUB)\n\n"
        f"<tg-emoji emoji-id=\"5429405838345265327\">📥</tg-emoji> <b>Адрес для перевода:</b>\n"
        f"<code>UQBO9ldjh-Z8h4PimediLifI5n-QSSf7lg6ND9itKamL1e97</code>\n\n"
        f"<tg-emoji emoji-id=\"5420323339723881652\">💬</tg-emoji> Комментарий (ОБЯЗАТЕЛЬНО): <code>{payment.id}</code>\n\n"
        f"<b>Перед переводом обязательно проверьте сумму, она должна совпадать с указанной выше</b> <tg-emoji emoji-id=\"5274099962655816924\">⚠️</tg-emoji>\n\n"
        f"Нажмите на кнопку ниже или переведите вручную с указанием комментария"
    )
    if isinstance(callback.message, Message):
        await safe_edit(callback.message, text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_cryptomus_"))
async def process_pay_cryptomus(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    plan_id = callback.data.split("_")[2]
    user = await _get_user_by_tg(db, callback.from_user.id)
    plan = settings.PLANS.get(plan_id)
    if not user or not plan: return

    payment_service = PaymentService(db)
    order_id = f"mus_{user.id}_{int(datetime.now().timestamp())}"
    
    invoice = await cryptomus_service.create_invoice(
        amount=float(plan["price"]),
        order_id=order_id
    )
    
    if not invoice:
        await callback.answer("❌ Ошибка CryptoMus. Попробуйте позже.", show_alert=True)
        return

    await payment_service.create_payment(
        user_id=user.id,
        tariff_id=plan_id,
        provider="cryptomus",
        amount=plan["price"],
        external_id=invoice["uuid"] # Cryptomus transaction UUID
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=invoice["url"])],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pay_order_{plan_id}")]
    ])
    
    if isinstance(callback.message, Message):
        await safe_edit(
            callback.message,
            f"🔗 <b>Счет CryptoMus создан!</b>\n\nТариф: {plan['label']}\nСумма: {plan['price']} RUB\n\nНажмите кнопку ниже для оплаты:",
            reply_markup=keyboard
        )
    await callback.answer()

@router.callback_query(F.data.startswith("check_pay_"))
async def process_check_pay(callback: CallbackQuery, db: AsyncSession):
    if not callback.data or not callback.message: return
    payment_id = int(callback.data.split("_")[2])
    
    # Get payment from DB
    stmt = select(Payment).where(Payment.id == payment_id)
    res = await db.execute(stmt)
    payment = res.scalar_one_or_none()
    
    if not payment:
        await callback.answer("⚠️ Платеж не найден.", show_alert=True)
        return
        
    if payment.status == PaymentStatus.SUCCESS:
         from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
         if isinstance(callback.message, Message):
             text = "✅ <b>Оплата получена!</b>\n\n"
             if payment.payload and payment.payload.startswith("dep_"):
                 text += f"Ваш баланс пополнен на <b>{payment.amount} RUB</b>.\nСпасибо за оплату!"
             else:
                 text += "Ваша подписка активирована. Приятного пользования!\n\nПерейдите в профиль, чтобы получить ключ."
                 
             await safe_edit(
                 callback.message,
                 text,
                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                     [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile_main")],
                     [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                 ])
             )
    else:
        # If TON, we could potentially check the blockchain here
        if payment.provider == "ton":
            is_paid = await ton_service.check_transaction(str(payment.id))
            if is_paid:
                payment_service = PaymentService(db)
                result = await payment_service.process_success(str(payment.id))
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
                if isinstance(callback.message, Message):
                    text = "✅ <b>Оплата получена!</b>\n\n"
                    if result and result.get("type") == "deposit":
                        text += f"Ваш баланс пополнен на <b>{result['amount']} RUB</b>.\nСпасибо за оплату!"
                    else:
                        text += "Ваша подписка активирована. Приятного пользования!\n\nПерейдите в профиль, чтобы получить ключ."

                    await safe_edit(
                        callback.message,
                        text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile_main")],
                            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                        ])
                    )
                return
            else:
                await callback.answer("⏳ Транзакция еще не найдена в блокчейне. Обычно это занимает 1-3 минуты.", show_alert=True)
        else:
            await callback.answer("⏳ Оплата еще не поступила. Попробуйте через минуту.", show_alert=True)

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment_handler(message: Message, db: AsyncSession):
    if not message.successful_payment: return
    payload = message.successful_payment.invoice_payload
    if payload.startswith("stars_"):
        parts = payload.split("_")
        user_id = int(parts[1])
        plan_id = parts[2]
        external_id = message.successful_payment.telegram_payment_charge_id
        
        payment_service = PaymentService(db)
        await payment_service.create_payment(
            user_id=user_id,
            tariff_id=plan_id,
            provider="stars",
            amount=message.successful_payment.total_amount,
            currency="XTR",
            external_id=external_id
        )
        await payment_service.process_success(external_id)
        await message.answer("✅ Оплата Stars прошла успешно! Подписка активирована.")


