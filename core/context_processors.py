"""
core/context_processors.py
Barcha shablonlarda (navbar kabi) global kontekst uchun ishlatiladi.
"""

from .models import Resource


def moderation_context(request):
    """Moderator (is_staff) foydalanuvchilar uchun navbarda kutayotgan materiallar sonini ko'rsatish."""
    if request.user.is_authenticated and request.user.is_staff:
        count = Resource.objects.filter(status=Resource.Status.PENDING).count()
        return {"pending_moderation_count": count}
    return {}
