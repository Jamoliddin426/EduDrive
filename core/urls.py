"""
core/urls.py
EduDrive web-sayt yo'nalishlari.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("link-telegram/", views.link_telegram_view, name="link_telegram"),

    # Dashboard
    path("", views.home_view, name="home"),
    path("category/<slug:slug>/", views.category_detail_view, name="category_detail"),

    # Resource
    path("resource/<slug:slug>/", views.resource_detail_view, name="resource_detail"),
    path("resource/<slug:slug>/download/", views.resource_download_view, name="resource_download"),
    path("resource/<slug:slug>/preview/", views.resource_preview_view, name="resource_preview"),
    path("resource/<slug:slug>/preview/zip/<path:entry_name>/", views.resource_preview_zip_entry_view, name="resource_preview_zip_entry"),
    path("resource/<slug:slug>/bookmark/", views.toggle_bookmark_view, name="toggle_bookmark"),
    path("resource/<slug:slug>/moderate/", views.moderate_resource_view, name="moderate_resource"),
    path("resource/<slug:slug>/edit/", views.resource_edit_view, name="resource_edit"),
    path("resource/<slug:slug>/delete/", views.resource_delete_view, name="resource_delete"),

    # Upload & Profile
    path("upload/", views.upload_resource_view, name="upload_resource"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/reset-avatar/", views.reset_avatar_view, name="reset_avatar"),

    # Extra features
    path("leaderboard/", views.leaderboard_view, name="leaderboard"),
    path("api/search-suggestions/", views.search_suggestions_view, name="search_suggestions"),
    path("api/notifications/", views.notifications_dropdown_view, name="notifications_dropdown"),
    path("api/notifications/mark-read/", views.notifications_mark_read_view, name="notifications_mark_read"),

    # Moderatsiya (adminga kirmasdan)
    path("moderate/", views.moderation_dashboard_view, name="moderation_dashboard"),
    path("moderate/history/", views.moderation_history_view, name="moderation_history"),
]
