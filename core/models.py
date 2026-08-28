"""
core/models.py
EduDrive platformasining asosiy ma'lumotlar bazasi modellari.
Bu modellar bir vaqtning o'zida Django Web-sayt va Aiogram Telegram Bot
tomonidan ishlatiladi (bitta umumiy PostgreSQL/SQLite baza).
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta


# ---------------------------------------------------------------------------
# 1. CUSTOM USER MODEL (Web + Telegram uchun yagona profil)
# ---------------------------------------------------------------------------
class CustomUser(AbstractUser):
    """
    Standart Django User modeliga qo'shimcha maydonlar bilan kengaytirilgan
    foydalanuvchi modeli. Telegram va Web hisoblarini bog'lash uchun
    telegram_id va OTP maydonlari qo'shilgan.
    """

    class Role(models.TextChoices):
        STUDENT = "student", "O'quvchi / Talaba"
        TEACHER = "teacher", "O'qituvchi"
        ADMIN = "admin", "Administrator"

    telegram_id = models.BigIntegerField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="Foydalanuvchining Telegram chat ID raqami"
    )
    telegram_username = models.CharField(max_length=64, null=True, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True, default="avatars/default.png")
    bio = models.TextField(max_length=500, blank=True)
    points = models.PositiveIntegerField(default=0, help_text="Faollik uchun to'plangan ballar")
    badges = models.JSONField(default=list, blank=True, help_text="['Top Uploader', 'Verified'] kabi belgilar")

    # Kunlik faollik (streak) tizimi
    last_active_date = models.DateField(null=True, blank=True)
    streak_days = models.PositiveIntegerField(default=0)

    # Hisoblarni bog'lash uchun bir martalik kod (OTP)
    otp_code = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    is_telegram_linked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "custom_users"
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"

    def __str__(self):
        return self.username

    def add_points(self, amount: int):
        self.points = models.F("points") + amount
        self.save(update_fields=["points"])
        self.refresh_from_db(fields=["points"])   # <-- SHU QATORNI QO'SHING    

    def check_daily_streak(self):
        """
        Har kuni birinchi marta kirganda chaqiriladi (login paytida).
        Ketma-ket kunlar sonini hisoblab, faollik uchun ball beradi:
        - Oddiy kun uchun: +1 ball
        - 7 kunlik ketma-ketlik uchun: qo'shimcha +10 ball bonus
        Kun uzilib qolsa, streak 1 dan qayta boshlanadi.
        """
        today = timezone.localdate()
        if self.last_active_date == today:
            return 0  # bugun allaqachon hisoblangan

        if self.last_active_date == today - timedelta(days=1):
            self.streak_days += 1
        else:
            self.streak_days = 1

        self.last_active_date = today
        earned = 1
        if self.streak_days % 7 == 0:
            earned += 10  # haftalik bonus

        self.points = models.F("points") + earned
        self.save(update_fields=["last_active_date", "streak_days", "points"])
        self.refresh_from_db(fields=["points"])
        return earned

    def is_otp_valid(self) -> bool:
        """OTP kod yaratilganidan keyin 10 daqiqa amal qiladi."""
        if not self.otp_code or not self.otp_created_at:
            return False
        return (timezone.now() - self.otp_created_at).total_seconds() < 600


# ---------------------------------------------------------------------------
# 2. CATEGORY (bo'limlar / kichik bo'limlar)
# ---------------------------------------------------------------------------
class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    icon = models.CharField(
        max_length=50, default="folder",
        help_text="Lucide icon nomi, masalan: 'book-open', 'code', 'flask-conical'"
    )
    parent_category = models.ForeignKey(
        "self", null=True, blank=True, related_name="subcategories",
        on_delete=models.CASCADE
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "categories"
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"
        ordering = ["order", "name"]

    def __str__(self):
        if self.parent_category:
            return f"{self.parent_category.name} → {self.name}"
        return self.name

    def get_absolute_url(self):
        return reverse("category_detail", kwargs={"slug": self.slug})


# ---------------------------------------------------------------------------
# 3. RESOURCE (yuklangan fayl / konspekt / darslik)
# ---------------------------------------------------------------------------
class Resource(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        APPROVED = "approved", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, related_name="resources", on_delete=models.PROTECT)

    # Fayl web orqali serverga, yoki Telegram orqali file_id ko'rinishida saqlanishi mumkin
    file = models.FileField(upload_to="resources/%Y/%m/", null=True, blank=True)
    telegram_file_id = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Telegram serveridan tezkor yuborish uchun cache qilingan file_id"
    )
    file_size_kb = models.PositiveIntegerField(default=0)
    file_type = models.CharField(max_length=20, blank=True, help_text="pdf, docx, pptx, image...")

    # Demo ko'rish uchun: PDF materiallarning faqat birinchi 2-3 sahifasidan
    # avtomatik generatsiya qilingan namuna fayl (yuklab olishsiz ko'rish uchun).
    preview_file = models.FileField(upload_to="previews/%Y/%m/", null=True, blank=True)
    cover_image = models.ImageField(
        upload_to="covers/%Y/%m/", null=True, blank=True,
        help_text="Material muqovasi/skrinshoti (avtomatik yoki qo'lda yuklanishi mumkin)"
    )

    uploaded_by = models.ForeignKey(
        CustomUser, related_name="uploaded_resources", on_delete=models.CASCADE
    )
    uploaded_via = models.CharField(
        max_length=10,
        choices=[("web", "Web-sayt"), ("bot", "Telegram Bot")],
        default="web"
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.CharField(max_length=255, blank=True)

    download_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "resources"
        verbose_name = "O'quv materiali"
        verbose_name_plural = "O'quv materiallari"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("resource_detail", kwargs={"slug": self.slug})

    @property
    def average_rating(self):
        agg = self.reviews.aggregate(avg=models.Avg("rating"))
        return round(agg["avg"] or 0, 1)

    @property
    def reviews_count(self):
        return self.reviews.count()

    @property
    def is_pdf(self) -> bool:
        return self.file_type.lower() == "pdf"

    @property
    def is_image(self) -> bool:
        return self.file_type.lower() in ("jpg", "jpeg", "png", "webp", "image")

    @property
    def is_zip(self) -> bool:
        return self.file_type.lower() == "zip"

    @property
    def is_office_doc(self) -> bool:
        return self.file_type.lower() in ("docx", "pptx", "txt", "md", "csv")

    @property
    def has_demo_preview(self) -> bool:
        return (
            bool(self.preview_file) or self.is_image
            or (self.is_zip and bool(self.file))
            or (self.is_office_doc and bool(self.file))
        )

    def approve(self):
        self.status = self.Status.APPROVED
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_at"])

    def reject(self, reason: str = ""):
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.save(update_fields=["status", "rejection_reason"])

    def increment_download(self):
        self.download_count = models.F("download_count") + 1
        self.save(update_fields=["download_count"])

    def increment_view(self):
        self.view_count = models.F("view_count") + 1
        self.save(update_fields=["view_count"])


# ---------------------------------------------------------------------------
# 4. REVIEW (sharh va reyting)
# ---------------------------------------------------------------------------
class Review(models.Model):
    user = models.ForeignKey(CustomUser, related_name="reviews", on_delete=models.CASCADE)
    resource = models.ForeignKey(Resource, related_name="reviews", on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        choices=[(i, str(i)) for i in range(1, 6)]
    )
    comment = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviews"
        verbose_name = "Sharh"
        verbose_name_plural = "Sharhlar"
        unique_together = ("user", "resource")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} → {self.resource} ({self.rating}★)"


# ---------------------------------------------------------------------------
# 5. BOOKMARK (saqlangan materiallar)
# ---------------------------------------------------------------------------
class Bookmark(models.Model):
    user = models.ForeignKey(CustomUser, related_name="bookmarks", on_delete=models.CASCADE)
    resource = models.ForeignKey(Resource, related_name="bookmarked_by", on_delete=models.CASCADE)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bookmarks"
        verbose_name = "Xatcho'p"
        verbose_name_plural = "Xatcho'plar"
        unique_together = ("user", "resource")
        ordering = ["-saved_at"]

    def __str__(self):
        return f"{self.user} → {self.resource}"


# ---------------------------------------------------------------------------
# 6. NOTIFICATION (bildirishnomalar - Web va Bot uchun umumiy)
# ---------------------------------------------------------------------------
class Notification(models.Model):
    user = models.ForeignKey(
        CustomUser, related_name="notifications", on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Bo'sh qoldirilsa, bu umumiy e'lon (broadcast) hisoblanadi va barcha "
                   "Telegram'ga ulangan foydalanuvchilarga bot orqali yuboriladi."
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True, help_text="Ichki yo'nalish, masalan: /resource/123/")
    is_read = models.BooleanField(default=False)

    # Aiogram bot orqali yuborilganini kuzatish uchun
    sent_via_bot = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "Bildirishnoma"
        verbose_name_plural = "Bildirishnomalar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} → {self.user}"

    def mark_as_read(self):
        self.is_read = True
        self.save(update_fields=["is_read"])
    