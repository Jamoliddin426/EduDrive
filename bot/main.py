"""
bot/main.py
EduDrive Aiogram 3.x botining kirish nuqtasi.

MUHIM: Bot Django modellariga bevosita murojaat qilishi uchun,
Django sozlamalari ishga tushirilishidan oldin DJANGO_SETTINGS_MODULE
o'rnatilib, django.setup() chaqirilishi shart. Shu tufayli bu skript
loyihaning ROOT papkasidan quyidagicha ishga tushiriladi:

    python -m bot.main

.env fayli quyidagi o'zgaruvchilarni o'z ichiga olishi kerak:
    BOT_TOKEN=...
    ADMIN_GROUP_ID=-100...
    WEBAPP_URL=https://sizning-domain.uz/
    SITE_URL=https://sizning-domain.uz
    BOT_USERNAME=EduDriveBot
    DJANGO_SETTINGS_MODULE=edudrive.settings
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# DJANGO SOZLAMALARINI ISHGA TUSHIRISH (bot va sayt bitta bazani ishlatishi uchun)
# ---------------------------------------------------------------------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.environ.get("DJANGO_SETTINGS_MODULE", "edudrive.settings"))

import django  # noqa: E402
django.setup()

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

from bot.handlers import router  # noqa: E402
from bot import db_queries as db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]


# ---------------------------------------------------------------------------
# BROADCAST NOTIFICATION LOGIC
# Django Admin-panelida yangi e'lon (Notification, user=None maxsus signal)
# yaratilganda, bu background task barcha ulangan foydalanuvchilarga
# bildirishnoma yuborishi uchun signal handler bilan birga ishlaydi.
# Bu yerda -- Django signals (core/signals.py) orqali chaqiriladigan
# funksiya sifatida ham ishlatilishi mumkin.
# ---------------------------------------------------------------------------
async def broadcast_message(bot: Bot, title: str, message: str):
    telegram_ids = await db.get_all_telegram_linked_user_ids()
    text = f"📢 <b>{title}</b>\n\n{message}"

    sent, failed = 0, 0
    for tg_id in telegram_ids:
        try:
            await bot.send_message(tg_id, text)
            sent += 1
        except Exception as exc:  # foydalanuvchi botni bloklagan bo'lishi mumkin
            logger.warning("Broadcast xatosi (user %s): %s", tg_id, exc)
            failed += 1
        await asyncio.sleep(0.05)  # Telegram flood-limitidan qochish uchun

    logger.info("Broadcast yakunlandi: %s ta yuborildi, %s ta muvaffaqiyatsiz.", sent, failed)


async def periodic_broadcast_listener(bot: Bot):
    """
    Django admin-panelida yaratilgan, hali botga yuborilmagan (sent_via_bot=False,
    user=None -> umumiy e'lon) bildirishnomalarni har 15 soniyada tekshirib,
    barcha foydalanuvchilarga jo'natadi.
    """
    from asgiref.sync import sync_to_async
    from core.models import Notification

    @sync_to_async
    def get_pending_broadcasts():
        return list(Notification.objects.filter(user__isnull=True, sent_via_bot=False)[:5])

    @sync_to_async
    def mark_sent(notif_ids):
        Notification.objects.filter(id__in=notif_ids).update(sent_via_bot=True)

    while True:
        try:
            pending = await get_pending_broadcasts()
            for notif in pending:
                await broadcast_message(bot, notif.title, notif.message)
            if pending:
                await mark_sent([n.id for n in pending])
        except Exception:
            logger.exception("Broadcast listenerda xatolik yuz berdi.")
        await asyncio.sleep(15)


async def periodic_personal_notification_listener(bot: Bot):
    """
    Saytda (web moderatsiya, ball berish, sharh va h.k.) yaratilgan SHAXSIY
    bildirishnomalarni (user belgilangan, hali botga yuborilmagan) har 10
    soniyada tekshirib, agar foydalanuvchi Telegram'ga ulangan bo'lsa —
    to'g'ridan-to'g'ri botdan xabar yuboradi. Shu orqali bot va sayt bir xil
    bildirishnoma tizimini ishlatadi (sayt bell'i = bot xabari).
    """
    from asgiref.sync import sync_to_async
    from core.models import Notification

    @sync_to_async
    def get_pending_personal():
        return list(
            Notification.objects.filter(
                user__isnull=False,
                user__telegram_id__isnull=False,
                sent_via_bot=False,
            ).select_related("user")[:20]
        )

    @sync_to_async
    def mark_sent(notif_id):
        Notification.objects.filter(id=notif_id).update(sent_via_bot=True)

    while True:
        try:
            pending = await get_pending_personal()
            for notif in pending:
                try:
                    await bot.send_message(
                        notif.user.telegram_id,
                        f"🔔 <b>{notif.title}</b>\n\n{notif.message}",
                    )
                except Exception as exc:
                    logger.warning("Shaxsiy bildirishnoma yuborilmadi (user %s): %s", notif.user.telegram_id, exc)
                await mark_sent(notif.id)
        except Exception:
            logger.exception("Shaxsiy bildirishnoma listenerda xatolik yuz berdi.")
        await asyncio.sleep(10)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Broadcast va shaxsiy bildirishnomalar uchun background tasklar
    asyncio.create_task(periodic_broadcast_listener(bot))
    asyncio.create_task(periodic_personal_notification_listener(bot))

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("EduDrive bot ishga tushdi (polling rejimida)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
