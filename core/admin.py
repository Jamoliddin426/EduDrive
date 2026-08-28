"""
core/admin.py
Django Admin-panel orqali UGC moderatsiyasi va umumiy boshqaruv.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, Category, Resource, Review, Bookmark, Notification


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "telegram_id", "is_telegram_linked", "points")
    list_editable = ("points",)
    list_filter = ("role", "is_telegram_linked", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("EduDrive ma'lumotlari", {
            "fields": ("telegram_id", "telegram_username", "role", "points", "badges"),
            "description": "Avatar va bio foydalanuvchining o'zi tomonidan saytdagi profil sahifasida boshqariladi.",
        }),
    )
    actions = ["add_10_points", "add_50_points", "remove_10_points", "reset_points"]

    @admin.action(description="➕ Tanlanganlarga +10 ball qo'shish")
    def add_10_points(self, request, queryset):
        for user in queryset:
            user.add_points(10)

    @admin.action(description="➕ Tanlanganlarga +50 ball qo'shish")
    def add_50_points(self, request, queryset):
        for user in queryset:
            user.add_points(50)

    @admin.action(description="➖ Tanlanganlardan -10 ball ayirish")
    def remove_10_points(self, request, queryset):
        for user in queryset:
            user.points = max(0, user.points - 10)
            user.save(update_fields=["points"])

    @admin.action(description="🔄 Tanlanganlarning ballini 0 ga tushirish")
    def reset_points(self, request, queryset):
        queryset.update(points=0)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent_category", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "uploaded_by", "status", "download_count", "created_at")
    list_filter = ("status", "category", "uploaded_via")
    search_fields = ("title", "description")
    actions = ["approve_resources", "reject_resources"]
    prepopulated_fields = {"slug": ("title",)}

    def save_model(self, request, obj, form, change):
        """
        Admin sahifasida material qo'lda tahrirlanib, statusi "approved"ga
        o'zgartirilganda ham (bulk action orqali emas) +5 ball berilishini
        ta'minlaydi.
        """
        was_approved_before = False
        if change and obj.pk:
            was_approved_before = Resource.objects.filter(
                pk=obj.pk, status=Resource.Status.APPROVED
            ).exists()

        super().save_model(request, obj, form, change)

        if obj.status == Resource.Status.APPROVED and not was_approved_before:
            obj.uploaded_by.add_points(5)
            Notification.objects.create(
                user=obj.uploaded_by,
                title="Materialingiz tasdiqlandi ✅",
                message=f"'{obj.title}' materiali endi barchaga ko'rinadi. +5 ball qo'shildi!",
            )

    @admin.action(description="Tanlangan materiallarni tasdiqlash")
    def approve_resources(self, request, queryset):
        for resource in queryset.exclude(status=Resource.Status.APPROVED):
            resource.approve()
            resource.uploaded_by.add_points(5)
            Notification.objects.create(
                user=resource.uploaded_by,
                title="Materialingiz tasdiqlandi ✅",
                message=f"'{resource.title}' materiali endi barchaga ko'rinadi. +5 ball qo'shildi!",
            )

    @admin.action(description="Tanlangan materiallarni rad etish")
    def reject_resources(self, request, queryset):
        for resource in queryset:
            resource.reject("Admin tomonidan ommaviy rad etildi.")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "resource", "rating", "created_at")


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("user", "resource", "saved_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "is_read", "sent_via_bot", "created_at")
    list_filter = ("is_read", "sent_via_bot")
    help_text = "Foydalanuvchi (user) maydonini bo'sh qoldirsangiz, bu barchaga broadcast e'lon bo'ladi."
