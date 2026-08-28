"""
core/middleware.py
Har bir so'rovda (agar foydalanuvchi tizimga kirgan bo'lsa) kunlik faollik
(streak) ballini avtomatik tekshiradi va beradi. Foydalanuvchi kun davomida
saytda qolib, hech qayerdan chiqib-kirmasa ham, ertasi kuni birinchi
harakatida (sahifani ochganida) ball avtomatik qo'shiladi.
"""

from .models import Notification


class DailyStreakMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            earned = request.user.check_daily_streak()
            if earned:
                Notification.objects.create(
                    user=request.user,
                    title="🔥 Kunlik faollik uchun ball",
                    message=(
                        f"Bugun saytga kirganingiz uchun +{earned} ball qo'shildi "
                        f"(ketma-ket {request.user.streak_days} kun)!"
                    ),
                )
        return self.get_response(request)