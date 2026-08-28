# EduDrive

O'quv materiallari, konspektlar va darsliklar platformasi.
Django 5.x (Web) + Aiogram 3.x (Telegram Bot), bitta umumiy ma'lumotlar bazasi ustida ishlaydi.

## O'rnatish

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # va qiymatlarni to'ldiring

python manage.py makemigrations core
python manage.py migrate
python manage.py createsuperuser
```

## Ishga tushirish

Web-sayt:
```bash
python manage.py runserver
```

Telegram bot (loyihaning ROOT papkasidan, alohida terminalda):
```bash
python -m bot.main
```

## Muhim eslatmalar

- Bot va sayt bitta bazadan foydalanadi — `bot/main.py` ishga tushganda `django.setup()`
  chaqiriladi va `core.models` dagi modellarga bevosita murojaat qiladi.
- Admin-panel: `/admin/` — Category va Resource'larni shu yerdan ham boshqarish mumkin.
- Umumiy e'lon (broadcast) yuborish uchun Admin-panelda Notification yarating va
  `user` maydonini bo'sh qoldiring — bot buni har 15 soniyada tekshirib, barcha
  Telegram'ga ulangan foydalanuvchilarga yuboradi.
- Fayl caching: birinchi marta bot orqali yuborilgan fayl `telegram_file_id`
  sifatida saqlanadi va keyingi so'rovlarda serverga tegmasdan, to'g'ridan-to'g'ri
  Telegram serveridan lahzada yuboriladi.
