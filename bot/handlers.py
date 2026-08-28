"""
bot/handlers.py
EduDrive Telegram Bot uchun barcha handlerlar:
- /start, profil aniqlash
- /link <otp> orqali Web hisobni ulash
- Kategoriya va fayllar katalogi (inline pagination)
- Fayl yuborish FSM (nom -> kategoriya -> tavsif -> saqlash)
- Admin guruhda tasdiqlash/rad etish tugmalari
- Fayl olish (file_id orqali tezkor yuborish)
"""

import os

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)

from . import db_queries as db

router = Router()

ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "0"))
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://127.0.0.1:8000/")
PAGE_SIZE = 6


# ---------------------------------------------------------------------------
# FSM STATES
# ---------------------------------------------------------------------------
class UploadStates(StatesGroup):
    waiting_for_file = State()
    waiting_for_title = State()
    waiting_for_category = State()
    waiting_for_description = State()


class SearchStates(StatesGroup):
    waiting_for_query = State()


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    user, created = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or "",
    )

    if command.args and command.args.startswith("get_"):
        resource_id = command.args.replace("get_", "")
        if resource_id.isdigit():
            await send_resource_file(message, int(resource_id))
            return

    greeting = (
        f"Assalomu alaykum, {message.from_user.first_name}! 👋\n\n"
        "<b>EduDrive</b> — o'quv materiallari, konspektlar va darsliklar botiga xush kelibsiz.\n\n"
        "Quyidagi menyudan foydalaning:"
    )
    await message.answer(greeting, reply_markup=main_menu_keyboard())


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Kategoriyalar", callback_data="categories:1")],
        [
            InlineKeyboardButton(text="🔍 Qidirish", callback_data="search:start"),
            InlineKeyboardButton(text="✨ Kunlik material", callback_data="daily:show"),
        ],
        [
            InlineKeyboardButton(text="🏆 Reyting", callback_data="leaderboard:show"),
            InlineKeyboardButton(text="🔖 Saqlanganlarim", callback_data="mybookmarks:show"),
        ],
        [InlineKeyboardButton(text="📤 Material yuborish", callback_data="upload:start")],
        [InlineKeyboardButton(
            text="🌐 EduDrive Portal",
            url=WEBAPP_URL  # web_app=WebAppInfo(...) o'rniga oddiy url= ishlatildi (HTTP brauzerda ochiladi)
        )],
    ])


# ---------------------------------------------------------------------------
# /link <otp_code>
# ---------------------------------------------------------------------------
@router.message(Command("link"))
async def cmd_link(message: Message, command: CommandObject):
    if not command.args:
        await message.answer(
            "Web-saytdagi profilingizdan olingan kodni shu tarzda yuboring:\n"
            "<code>/link 123456</code>"
        )
        return

    otp = command.args.strip()
    user = await db.link_account_by_otp(message.from_user.id, otp)
    if user:
        await message.answer(
            f"✅ Muvaffaqiyat! Telegram hisobingiz <b>{user.username}</b> web profiliga ulandi."
        )
    else:
        await message.answer("❌ Kod noto'g'ri yoki muddati o'tgan. Saytdan yangi kod oling.")


# ---------------------------------------------------------------------------
# /admin
# ---------------------------------------------------------------------------
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    user = await db.get_user_by_telegram_id(message.from_user.id)

    if not user or not user.is_staff:
        return

    pending = await db.get_pending_resources(limit=10)

    if not pending:
        await message.answer(
            f"👋 Xush kelibsiz, <b>{user.username}</b>!\n\n"
            "✅ Hozircha kutayotgan material yo'q. Hammasi tozalangan!"
        )
        return

    await message.answer(
        f"👋 Xush kelibsiz, <b>{user.username}</b>!\n\n"
        f"🛡 <b>Moderatsiya paneli</b> — {len(pending)} ta material kutmoqda:"
    )

    for resource in pending:
        text = (
            f"📄 <b>{resource.title}</b>\n"
            f"{resource.description or ''}\n\n"
            f"📁 {resource.category.name} | 👤 {resource.uploaded_by.username}"
        )
        buttons = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"moderate:approve:{resource.id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"moderate:reject:{resource.id}"),
        ]])
        await message.answer(text, reply_markup=buttons)


# ---------------------------------------------------------------------------
# KATEGORIYALAR VA FAYLLAR KATALOGI
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("categories:"))
async def show_categories(callback: CallbackQuery):
    categories = await db.get_root_categories()

    buttons = [
        [InlineKeyboardButton(text=f"{cat.icon and '📁'} {cat.name}", callback_data=f"cat:{cat.id}:1")]
        for cat in categories
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="menu:main")])

    await callback.message.edit_text(
        "📚 Kategoriyani tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "Bosh menyu:", reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def show_resources_in_category(callback: CallbackQuery):
    _, category_id, page = callback.data.split(":")
    category_id, page = int(category_id), int(page)

    resources, total = await db.get_approved_resources_by_category(category_id, page, PAGE_SIZE)

    if not resources:
        await callback.answer("Bu kategoriyada hozircha material yo'q.", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text=f"📄 {r.title[:40]}", callback_data=f"res:{r.id}")]
        for r in resources
    ]

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"cat:{category_id}:{page - 1}"))
    if page * PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"cat:{category_id}:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="⬅️ Kategoriyalarga", callback_data="categories:1")])

    await callback.message.edit_text(
        f"📚 Materiallar ({page}-sahifa):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("res:"))
async def show_resource_detail(callback: CallbackQuery):
    resource_id = int(callback.data.split(":")[1])
    resource = await db.get_resource_by_id(resource_id)

    if not resource:
        await callback.answer("Material topilmadi.", show_alert=True)
        return

    rating = getattr(resource, "cached_rating", 0.0)

    text = (
        f"<b>{resource.title}</b>\n\n"
        f"{resource.description or 'Tavsif kiritilmagan.'}\n\n"
        f"⬇️ {resource.download_count} marta yuklangan | ⭐ {rating}"
    )
    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ Yuklab olish", callback_data=f"download:{resource.id}")],
        [InlineKeyboardButton(text="🔖 Saqlash / olib tashlash", callback_data=f"bookmark_toggle:{resource.id}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"cat:{resource.category_id}:1")],
    ])
    await callback.message.edit_text(text, reply_markup=buttons)
    await callback.answer()


@router.callback_query(F.data.startswith("download:"))
async def download_resource_callback(callback: CallbackQuery):
    resource_id = int(callback.data.split(":")[1])
    await send_resource_file(callback.message, resource_id)
    await callback.answer("Yuborilmoqda...")


@router.callback_query(F.data.startswith("bookmark_toggle:"))
async def bookmark_toggle_callback(callback: CallbackQuery):
    resource_id = int(callback.data.split(":")[1])
    result = await db.toggle_bookmark_bot(callback.from_user.id, resource_id)
    if result is None:
        await callback.answer("Avval profilingizni ulang: /link <kod>", show_alert=True)
    elif result:
        await callback.answer("🔖 Saqlandi!")
    else:
        await callback.answer("Saqlanganlardan olib tashlandi.")


async def send_resource_file(message: Message, resource_id: int):
    resource = await db.get_resource_by_id(resource_id)
    if not resource:
        await message.answer("❌ Material topilmadi.")
        return

    await db.increment_resource_download(resource_id)

    if resource.telegram_file_id:
        await message.answer_document(
            document=resource.telegram_file_id,
            caption=f"📄 {resource.title}",
        )
    else:
        site_url = os.environ.get("SITE_URL", "http://127.0.0.1:8000/")
        await message.answer(
            f"Faylni bu havoladan yuklab oling:\n{site_url}/resource/{resource.slug}/download/"
        )


# ---------------------------------------------------------------------------
# FAYL YUBORISH FSM
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "upload:start")
async def upload_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_for_file)
    await callback.message.edit_text(
        "📤 Materialingizni (PDF, DOCX, PPTX yoki rasm) shu yerga yuboring:"
    )
    await callback.answer()


@router.message(StateFilter(UploadStates.waiting_for_file), F.document | F.photo)
async def upload_receive_file(message: Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_type = message.document.file_name.split(".")[-1].lower() if message.document.file_name else "file"
    else:
        file_id = message.photo[-1].file_id
        file_type = "image"

    await state.update_data(telegram_file_id=file_id, file_type=file_type)
    await state.set_state(UploadStates.waiting_for_title)
    await message.answer("✅ Fayl qabul qilindi. Endi material nomini yuboring:")


@router.message(StateFilter(UploadStates.waiting_for_file))
async def upload_wrong_file(message: Message):
    await message.answer("Iltimos, fayl yoki rasm ko'rinishida yuboring.")


@router.message(StateFilter(UploadStates.waiting_for_title))
async def upload_receive_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)

    categories = await db.get_root_categories()
    buttons = [
        [InlineKeyboardButton(text=cat.name, callback_data=f"upload_cat:{cat.id}")]
        for cat in categories
    ]
    await state.set_state(UploadStates.waiting_for_category)
    await message.answer(
        "📁 Kategoriyani tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(StateFilter(UploadStates.waiting_for_category), F.data.startswith("upload_cat:"))
async def upload_receive_category(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split(":")[1])
    await state.update_data(category_id=category_id)
    await state.set_state(UploadStates.waiting_for_description)
    await callback.message.edit_text("📝 Endi material haqida qisqacha tavsif yozing:")
    await callback.answer()


@router.message(StateFilter(UploadStates.waiting_for_description))
async def upload_receive_description(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = await db.get_user_by_telegram_id(message.from_user.id)

    resource = await db.create_pending_resource(
        title=data["title"],
        description=message.text,
        category_id=data["category_id"],
        telegram_user=user,
        telegram_file_id=data["telegram_file_id"],
        file_type=data["file_type"],
    )

    await state.clear()
    await message.answer(
        "✅ Materialingiz qabul qilindi va moderatsiyaga yuborildi!\n"
        "Admin tasdiqlagach, u sayt va botda barchaga ko'rinadi."
    )

    await db.notify_staff_new_pending_resource(resource)

    if ADMIN_GROUP_ID:
        admin_buttons = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"moderate:approve:{resource.id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"moderate:reject:{resource.id}"),
        ]])
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"🆕 Yangi material moderatsiya kutmoqda:\n\n"
            f"<b>{resource.title}</b>\n{resource.description}\n\n"
            f"Yuboruvchi: {message.from_user.full_name} (@{message.from_user.username})",
            reply_markup=admin_buttons,
        )


# ---------------------------------------------------------------------------
# ADMIN MODERATSIYA
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("moderate:"))
async def moderate_resource(callback: CallbackQuery, bot: Bot):
    _, action, resource_id = callback.data.split(":")
    resource_id = int(resource_id)

    resource, already_processed = await db.set_resource_status(resource_id, approve=(action == "approve"))
    if not resource:
        await callback.answer("Material topilmadi.", show_alert=True)
        return

    if already_processed:
        current_status = "✅ Tasdiqlangan" if resource.status == "approved" else "❌ Rad etilgan"
        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n<i>ℹ️ Bu material allaqachon ko'rib chiqilgan ({current_status}).</i>"
        )
        await callback.answer("Bu material allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    status_text = "✅ Tasdiqlandi" if action == "approve" else "❌ Rad etildi"
    await callback.message.edit_text(f"{callback.message.html_text}\n\n<b>{status_text}</b>")

    if resource.uploaded_by and resource.uploaded_by.telegram_id:
        bonus_text = " (+5 ball qo'shildi!)" if action == "approve" else ""
        text = f"Materialingiz <b>{resource.title}</b> {status_text.lower()}.{bonus_text}"
        await bot.send_message(resource.uploaded_by.telegram_id, text)

    await callback.answer(status_text)


# ---------------------------------------------------------------------------
# QIDIRUV
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "search:start")
async def search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_for_query)
    await callback.message.edit_text("🔍 Qidiruv so'zini yozing (masalan: <i>matematika</i>):")
    await callback.answer()


@router.message(StateFilter(SearchStates.waiting_for_query))
async def search_receive_query(message: Message, state: FSMContext):
    await state.clear()
    results = await db.search_resources(message.text.strip())

    if not results:
        await message.answer(
            "😔 Hech narsa topilmadi. Boshqa so'z bilan urinib ko'ring.",
            reply_markup=main_menu_keyboard(),
        )
        return

    buttons = [
        [InlineKeyboardButton(text=f"📄 {r.title[:40]}", callback_data=f"res:{r.id}")]
        for r in results
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Bosh menyu", callback_data="menu:main")])
    await message.answer(
        f"🔍 \"{message.text}\" bo'yicha {len(results)} ta natija topildi:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# ---------------------------------------------------------------------------
# REYTING
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "leaderboard:show")
async def leaderboard_show(callback: CallbackQuery):
    top_users = await db.get_leaderboard(10)

    if not top_users:
        await callback.answer("Reytingda hozircha hech kim yo'q.", show_alert=True)
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Faollar reytingi</b>\n"]
    for i, u in enumerate(top_users):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {u.username} — <b>{u.points}</b> ball")

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bosh menyu", callback_data="menu:main")]
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=buttons)
    await callback.answer()


# ---------------------------------------------------------------------------
# KUNLIK MATERIAL
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "daily:show")
async def daily_resource_show(callback: CallbackQuery):
    resource = await db.get_daily_resource()
    if not resource:
        await callback.answer("Hozircha materiallar yo'q.", show_alert=True)
        return

    rating = getattr(resource, "cached_rating", 0.0)

    text = (
        f"✨ <b>Bugungi kun materiali</b>\n\n"
        f"<b>{resource.title}</b>\n{resource.description or ''}\n\n"
        f"⬇️ {resource.download_count} marta yuklangan | ⭐ {rating}"
    )
    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ Yuklab olish", callback_data=f"download:{resource.id}")],
        [InlineKeyboardButton(text="⬅️ Bosh menyu", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=buttons)
    await callback.answer()


# ---------------------------------------------------------------------------
# SAQLANGANLARIM
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "mybookmarks:show")
async def my_bookmarks_show(callback: CallbackQuery):
    bookmarks = await db.get_user_bookmarks_bot(callback.from_user.id)

    if not bookmarks:
        await callback.answer("Saqlangan materiallaringiz yo'q.", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text=f"📄 {b.resource.title[:40]}", callback_data=f"res:{b.resource.id}")]
        for b in bookmarks
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Bosh menyu", callback_data="menu:main")])
    await callback.message.edit_text(
        "🔖 Saqlangan materiallaringiz:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()