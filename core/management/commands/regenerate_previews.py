"""
core/management/commands/regenerate_previews.py

Ishlatish:
    python manage.py regenerate_previews

Bazadagi barcha PDF materiallar uchun demo-preview faylni (DEMO_PREVIEW_PAGES
sozlamasiga mos ravishda) qaytadan generatsiya qiladi. DEMO_PREVIEW_PAGES
qiymatini o'zgartirgandan keyin (masalan 2dan 5ga) eski materiallarning
demosini yangilash uchun kerak.
"""

from django.core.management.base import BaseCommand
from core.models import Resource
from core.forms import generate_pdf_preview


class Command(BaseCommand):
    help = "Barcha PDF materiallar uchun demo-preview faylni qaytadan generatsiya qiladi."

    def handle(self, *args, **options):
        resources = Resource.objects.filter(file_type="pdf").exclude(file="")
        total = resources.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("PDF materiallar topilmadi."))
            return

        updated = 0
        for resource in resources:
            try:
                generate_pdf_preview(resource)
                updated += 1
                self.stdout.write(f"  ✅ {resource.title}")
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  ❌ {resource.title}: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nTayyor! {updated}/{total} ta material uchun demo-fayl yangilandi."
        ))