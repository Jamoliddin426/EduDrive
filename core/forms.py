"""
core/forms.py
Ro'yxatdan o'tish, kirish, fayl yuklash va sharh qoldirish uchun formalar.
"""

import io
import random
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify

from .models import CustomUser, Resource, Review, Category
from .file_utils import sniff_file_type

User = get_user_model()

INPUT_CLASSES = (
    "w-full rounded-xl border border-gray-300 dark:border-gray-700 "
    "bg-white/70 dark:bg-gray-900/70 px-4 py-3 backdrop-blur-sm "
    "focus:ring-2 focus:ring-indigo-500 focus:outline-none"
)


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="E-mail pochta",
        widget=forms.EmailInput(attrs={"placeholder": "example@mail.com"})
    )
    telegram_id = forms.CharField(
        required=False,
        label="Telegram ID",
        help_text="Ixtiyoriy: Telegram ID'ingizni kiriting.",
        widget=forms.TextInput(attrs={"placeholder": " Masalan: 12345678"})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({"class": INPUT_CLASSES})
            if name == "username":
                field.widget.attrs.update({"placeholder": "Foydalanuvchi nomi"})

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Ushbu foydalanuvchi nomi (username) allaqachon band.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Ushbu e-mail pochta bilan allaqachon ro'yxatdan o'tilgan.")
        return email

    def clean_telegram_id(self):
        tg_id = self.cleaned_data.get("telegram_id")
        if tg_id:
            if not tg_id.isdigit():
                raise forms.ValidationError("Telegram ID faqat raqamlardan iborat bo'lishi kerak.")
            if User.objects.filter(telegram_id=tg_id).exists():
                raise forms.ValidationError("Bu Telegram ID allaqachon boshqa hisobga ulangan.")
        return tg_id

    def save(self, commit=True):
        user = super().save(commit=False)
        tg_id = self.cleaned_data.get("telegram_id")
        if tg_id:
            user.telegram_id = int(tg_id)
            user.is_telegram_linked = True
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Login"})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASSES, "placeholder": "Parol"})
    )


class TelegramLinkForm(forms.Form):
    otp_code = forms.CharField(max_length=6, min_length=6)

    def clean_otp_code(self):
        code = self.cleaned_data["otp_code"]
        if not code.isdigit():
            raise forms.ValidationError("OTP kod faqat raqamlardan iborat bo'lishi kerak.")
        return code

    @staticmethod
    def generate_otp(user: CustomUser) -> str:
        code = str(random.randint(100000, 999999))
        user.otp_code = code
        user.otp_created_at = timezone.now()
        user.save(update_fields=["otp_code", "otp_created_at"])
        return code


class ResourceUploadForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ["title", "description", "category", "file"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-gray-300 dark:border-gray-700 "
                         "bg-white/70 dark:bg-gray-900/70 px-4 py-3 backdrop-blur-sm "
                         "focus:ring-2 focus:ring-indigo-500 focus:outline-none",
                "placeholder": "Masalan: Matematik Analiz I-qism konspekti",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-gray-300 dark:border-gray-700 "
                         "bg-white/70 dark:bg-gray-900/70 px-4 py-3 backdrop-blur-sm "
                         "focus:ring-2 focus:ring-indigo-500 focus:outline-none",
                "rows": 4,
                "placeholder": "Material haqida qisqacha ma'lumot... (majburiy)",
            }),
            "category": forms.Select(attrs={
                "class": "w-full rounded-xl border border-gray-300 dark:border-gray-700 "
                         "bg-white/70 dark:bg-gray-900/70 px-4 py-3 backdrop-blur-sm",
            }),
            "file": forms.ClearableFileInput(attrs={
                "class": "w-full rounded-xl border-2 border-dashed border-indigo-400 "
                         "px-4 py-6 cursor-pointer",
            }),
        }

    new_category = forms.CharField(
        required=False, max_length=120,
        label="Yoki yangi kategoriya nomi",
        widget=forms.TextInput(attrs={
            "class": "w-full rounded-xl border border-gray-300 dark:border-gray-700 "
                     "bg-white/70 dark:bg-gray-900/70 px-4 py-3 backdrop-blur-sm "
                     "focus:ring-2 focus:ring-indigo-500 focus:outline-none",
            "placeholder": "Ro'yxatda yo'q bo'lsa, shu yerga yangi nom yozing...",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = True
        self.fields["description"].required = True
        self.fields["file"].required = True
        self.fields["category"].required = False
        self.fields["category"].queryset = Category.objects.all().select_related("parent_category")
        self.fields["category"].label_from_instance = lambda obj: str(obj)

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        new_category_name = cleaned_data.get("new_category", "").strip()

        if category and new_category_name:
            raise forms.ValidationError(
                "Ikkalasini birdaniga tanlamang — iltimos 2sidan birini tanlang: "
                "yo ro'yxatdan kategoriya tanlang, yo yangi nom yozing."
            )

        if not category and not new_category_name:
            raise forms.ValidationError(
                "Kategoriyani ro'yxatdan tanlang yoki yangisining nomini yozing."
            )
        return cleaned_data

    def save(self, commit=True, user=None):
        resource = super().save(commit=False)
        resource.uploaded_by = user
        resource.uploaded_via = "web"

        new_category_name = self.cleaned_data.get("new_category", "").strip()
        if new_category_name:
            base_slug = slugify(new_category_name)[:130] or "kategoriya"
            category, created = Category.objects.get_or_create(
                name__iexact=new_category_name,
                defaults={"name": new_category_name, "slug": base_slug},
            )
            if created:
                slug = base_slug
                counter = 1
                while Category.objects.filter(slug=slug).exclude(id=category.id).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                if slug != category.slug:
                    category.slug = slug
                    category.save(update_fields=["slug"])
            resource.category = category

        base_slug = slugify(resource.title)[:250] or "resource"
        slug = base_slug
        counter = 1
        while Resource.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        resource.slug = slug

        if resource.file:
            resource.file_size_kb = resource.file.size // 1024
            ext_from_name = resource.file.name.split(".")[-1].lower()
            resource.file.seek(0)
            head = resource.file.read()
            resource.file.seek(0)
            resource.file_type = sniff_file_type(head, fallback_ext=ext_from_name)

        if commit:
            resource.save()
            if resource.file_type == "pdf":
                generate_pdf_preview(resource)
        return resource


DEMO_PREVIEW_PAGES = 5


def generate_pdf_preview(resource: Resource) -> bool:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return False

    try:
        resource.file.open("rb")
        data = resource.file.read()

        if not data.startswith(b"%PDF"):
            return False

        reader = PdfReader(io.BytesIO(data))
        writer = PdfWriter()

        page_count = min(DEMO_PREVIEW_PAGES, len(reader.pages))
        for i in range(page_count):
            writer.add_page(reader.pages[i])

        buffer = io.BytesIO()
        writer.write(buffer)
        buffer.seek(0)

        resource.preview_file.save(
            f"preview_{resource.slug}.pdf", ContentFile(buffer.read()), save=True
        )
        return True
    except Exception:
        return False
    finally:
        resource.file.close()


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.RadioSelect(),
            "comment": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-gray-300 dark:border-gray-700 "
                         "bg-white/70 dark:bg-gray-900/70 px-4 py-3",
                "rows": 3,
                "placeholder": "Fikringizni yozing...",
            }),
        }


class AvatarUploadForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["avatar"]
        widgets = {
            "avatar": forms.ClearableFileInput(attrs={
                "class": "hidden", "id": "avatar-input", "accept": "image/*",
            }),
        }


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["avatar", "bio"]
        widgets = {
            "avatar": forms.ClearableFileInput(attrs={
                "class": "hidden", "id": "avatar-input", "accept": "image/*",
            }),
            "bio": forms.Textarea(attrs={
                "class": INPUT_CLASSES, "rows": 3,
                "placeholder": "O'zingiz haqingizda qisqacha...",
            }),
        }


class SearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=200)
    category = forms.CharField(required=False)
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("new", "Yangi qo'shilganlar"),
            ("popular", "Eng ko'p yuklanganlar"),
            ("rating", "Eng yuqori baholanganlar"),
        ],
    )