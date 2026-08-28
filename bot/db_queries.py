"""
bot/db_queries.py
Aiogram bot Django ORM modellariga bevosita murojaat qiladi (bitta umumiy baza).
Django sync ORM chaqiruvlari asyncio bilan ishlashi uchun `sync_to_async` bilan o'raladi.
Bu modul chaqirilishidan oldin bot/main.py da django.setup() bajarilgan bo'lishi shart.
"""

from asgiref.sync import sync_to_async
from django.utils.text import slugify

from core.models import CustomUser, Category, Resource, Notification


# ---------------------------------------------------------------------------
# USER
# ---------------------------------------------------------------------------
@sync_to_async
def get_or_create_user(telegram_id: int, username: str = "", full_name: str = ""):
    """
    /start bosilganda chaqiriladi:
    - Bazada shu telegram_id mavjud bo'lsa -> profilga ulanadi.
    - Mavjud bo'lmasa -> avtomatik yangi profil yaratiladi.
    """
    user, created = CustomUser.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "username": username or f"tg_{telegram_id}",
            "telegram_username": username,
            "first_name": full_name.split(" ")[0] if full_name else "",
            "is_telegram_linked": True,
        },
    )
    return user, created


@sync_to_async
def link_account_by_otp(telegram_id: int, otp_code: str):
    """
    Web-saytda generatsiya qilingan OTP kodni bot orqali tasdiqlab,
    mavjud Web hisobini shu Telegram ID bilan bog'laydi.
    """
    try:
        user = CustomUser.objects.get(otp_code=otp_code)
    except CustomUser.DoesNotExist:
        return None

    if not user.is_otp_valid():
        return None

    user.telegram_id = telegram_id
    user.is_telegram_linked = True
    user.otp_code = None
    user.otp_created_at = None
    user.save(update_fields=["telegram_id", "is_telegram_linked", "otp_code", "otp_created_at"])
    return user


@sync_to_async
def get_user_by_telegram_id(telegram_id: int):
    return CustomUser.objects.filter(telegram_id=telegram_id).first()


# ---------------------------------------------------------------------------
# CATEGORY
# ---------------------------------------------------------------------------
@sync_to_async
def get_root_categories():
    return list(Category.objects.filter(parent_category__isnull=True).order_by("order"))


@sync_to_async
def get_category_by_id(category_id: int):
    return Category.objects.filter(id=category_id).first()


# ---------------------------------------------------------------------------
# RESOURCE
# ---------------------------------------------------------------------------
@sync_to_async
def get_approved_resources_by_category(category_id: int, page: int = 1, page_size: int = 6):
    qs = Resource.objects.filter(
        category_id=category_id, status=Resource.Status.APPROVED
    ).order_by("-created_at")
    start = (page - 1) * page_size
    end = start + page_size
    total = qs.count()
    return list(qs[start:end]), total


@sync_to_async
def get_resource_by_id(resource_id: int):
    resource = Resource.objects.filter(id=resource_id).first()
    if resource:
        resource.cached_rating = resource.average_rating
    return resource


@sync_to_async
def create_pending_resource(
    title: str, description: str, category_id: int, telegram_user, telegram_file_id: str, file_type: str
):
    """FSM orqali bosqichma-bosqich yig'ilgan ma'lumotlarni pending statusda saqlaydi."""
    base_slug = slugify(title)[:250] or "resource"
    slug = base_slug
    counter = 1
    while Resource.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return Resource.objects.create(
        title=title,
        slug=slug,
        description=description,
        category_id=category_id,
        uploaded_by=telegram_user,
        uploaded_via="bot",
        telegram_file_id=telegram_file_id,
        file_type=file_type,
        status=Resource.Status.PENDING,
    )


@sync_to_async
def set_resource_status(resource_id: int, approve: bool, reason: str = ""):
    resource = Resource.objects.filter(id=resource_id).first()
    if not resource:
        return None, False

    if resource.status != Resource.Status.PENDING:
        return resource, True

    if approve:
        resource.approve()
        if resource.uploaded_by:
            resource.uploaded_by.add_points(5)
            Notification.objects.create(
                user=resource.uploaded_by,
                title="Materialingiz tasdiqlandi ✅",
                message=f"'{resource.title}' materiali endi barchaga ko'rinadi. +5 ball qo'shildi!",
                sent_via_bot=True,
            )
    else:
        resource.reject(reason)
        if resource.uploaded_by:
            reason_text = reason or "sabab ko'rsatilmagan"
            Notification.objects.create(
                user=resource.uploaded_by,
                title="Materialingiz rad etildi ❌",
                message=f"'{resource.title}' materiali rad etildi. Sabab: {reason_text}",
                sent_via_bot=True,
            )
    return resource, False


@sync_to_async
def increment_resource_download(resource_id: int):
    resource = Resource.objects.filter(id=resource_id).first()
    if resource:
        resource.increment_download()
        if resource.uploaded_by:
            resource.uploaded_by.add_points(2)
    return resource


# ---------------------------------------------------------------------------
# NOTIFICATION / BROADCAST
# ---------------------------------------------------------------------------
@sync_to_async
def get_all_telegram_linked_user_ids():
    return list(
        CustomUser.objects.filter(
            is_telegram_linked=True, telegram_id__isnull=False
        ).values_list("telegram_id", flat=True)
    )


@sync_to_async
def create_notification(user, title: str, message: str, link: str = ""):
    return Notification.objects.create(user=user, title=title, message=message, link=link, sent_via_bot=True)


@sync_to_async
def get_pending_resources(limit: int = 10):
    return list(
        Resource.objects.filter(status=Resource.Status.PENDING)
        .select_related("category", "uploaded_by")
        .order_by("created_at")[:limit]
    )


@sync_to_async
def notify_staff_new_pending_resource(resource):
    """Bot orqali yangi material yuklanganda, saytdagi moderatorlarga ham bildirishnoma yaratadi."""
    from django.urls import reverse
    staff_users = CustomUser.objects.filter(is_staff=True)
    for staff_user in staff_users:
        Notification.objects.create(
            user=staff_user,
            title="🆕 Yangi material moderatsiya kutmoqda (bot orqali)",
            message=f"'{resource.title}' materiali ({resource.uploaded_by.username} tomonidan, Telegram bot orqali) tasdiqlashni kutmoqda.",
            link=reverse("moderation_dashboard"),
        )


@sync_to_async
def get_unread_notifications(telegram_id: int):
    return list(
        Notification.objects.filter(
            user__telegram_id=telegram_id, is_read=False
        ).order_by("-created_at")[:10]
    )


# ---------------------------------------------------------------------------
# QIDIRUV, REYTING, KUNLIK MATERIAL, SAQLANGANLAR
# ---------------------------------------------------------------------------
@sync_to_async
def search_resources(query: str, limit: int = 8):
    from django.db.models import Q
    return list(
        Resource.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query),
            status=Resource.Status.APPROVED,
        )[:limit]
    )


@sync_to_async
def get_leaderboard(limit: int = 10):
    return list(CustomUser.objects.filter(points__gt=0).order_by("-points")[:limit])


@sync_to_async
def get_daily_resource():
    import hashlib
    from datetime import date
    ids = list(Resource.objects.filter(status=Resource.Status.APPROVED).values_list("id", flat=True))
    if not ids:
        return None
    seed = int(hashlib.md5(str(date.today()).encode()).hexdigest(), 16)
    resource = Resource.objects.get(id=ids[seed % len(ids)])
    if resource:
        resource.cached_rating = resource.average_rating
    return resource


@sync_to_async
def get_user_bookmarks_bot(telegram_id: int, limit: int = 10):
    from core.models import Bookmark
    return list(
        Bookmark.objects.filter(user__telegram_id=telegram_id)
        .select_related("resource")
        .order_by("-saved_at")[:limit]
    )


@sync_to_async
def toggle_bookmark_bot(telegram_id: int, resource_id: int):
    from core.models import Bookmark
    user = CustomUser.objects.filter(telegram_id=telegram_id).first()
    if not user:
        return None
    bookmark, created = Bookmark.objects.get_or_create(user=user, resource_id=resource_id)
    if not created:
        bookmark.delete()
        return False
    return True