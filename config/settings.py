"""
Django settings for the Madresa Library check-in / check-out system.

Everything environment-specific is read from environment variables (or a .env
file next to manage.py). See .env.example for the full list.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "library",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Local development falls back to SQLite so the app runs with zero setup.
# Production sets DATABASE_URL to a Postgres connection string.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "America/Chicago")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compressed but not manifest-hashed: no collectstatic needed to run tests,
    # and the admin's static files are served by WhiteNoise in production.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "admin:index"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", True)

# ---------------------------------------------------------------------------
# Library-specific settings
# ---------------------------------------------------------------------------
LIBRARY_DEFAULT_LOAN_DAYS = int(os.environ.get("DEFAULT_LOAN_DAYS", "14"))
LIBRARY_LOAN_DAY_CHOICES = [7, 14, 21, 30]

# ---------------------------------------------------------------------------
# Unfold admin theme
# ---------------------------------------------------------------------------
from django.urls import reverse_lazy  # noqa: E402
from django.utils.translation import gettext_lazy as _  # noqa: E402

UNFOLD = {
    "SITE_TITLE": "Madresa Library",
    "SITE_HEADER": "Madresa Burhaniyah Dallas",
    "SITE_SUBHEADER": "Library",
    "SITE_SYMBOL": "menu_book",
    "SITE_URL": None,
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "DASHBOARD_CALLBACK": "library.dashboard.dashboard_callback",
    "COLORS": {
        "primary": {
            "50": "#ecfdf5",
            "100": "#d1fae5",
            "200": "#a7f3d0",
            "300": "#6ee7b7",
            "400": "#34d399",
            "500": "#10b981",
            "600": "#059669",
            "700": "#047857",
            "800": "#065f46",
            "900": "#064e3b",
            "950": "#022c22",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Circulation"),
                "separator": False,
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                    {
                        "title": _("Check out"),
                        "icon": "output",
                        "link": reverse_lazy("admin:library_checkout"),
                    },
                    {
                        "title": _("Check in"),
                        "icon": "input",
                        "link": reverse_lazy("admin:library_checkin"),
                    },
                    {
                        "title": _("Loans"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:library_loan_changelist"),
                    },
                ],
            },
            {
                "title": _("Catalog"),
                "separator": True,
                "items": [
                    {
                        "title": _("Books"),
                        "icon": "book_2",
                        "link": reverse_lazy("admin:library_book_changelist"),
                    },
                    {
                        "title": _("Shelves"),
                        "icon": "shelves",
                        "link": reverse_lazy("admin:library_shelf_changelist"),
                    },
                    {
                        "title": _("Categories"),
                        "icon": "label",
                        "link": reverse_lazy("admin:library_category_changelist"),
                    },
                ],
            },
            {
                "title": _("Administration"),
                "separator": True,
                "items": [
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Groups"),
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
}
