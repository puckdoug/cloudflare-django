import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.getenv("DJANGO_DEBUG", "") == "1"

ALLOWED_HOSTS = ["dj.heroic.ch", "localhost", "127.0.0.1", "testserver"]
ALLOWED_HOSTS += [
    host for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if host
]

CSRF_TRUSTED_ORIGINS = ["https://dj.heroic.ch"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR.joinpath("templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "app.wsgi.application"

# Workers CI lacks the sqlite3 module. Empty DATABASES lets collectstatic run.
if os.getenv("WORKERS_CI") == "1" or os.getenv("DJANGO_TEST") == "1":
    DATABASES = {}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django_cf.db.backends.do",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR.parent.joinpath("staticfiles").joinpath("static")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

BOOTSTRAP_ENABLED = os.getenv("BOOTSTRAP_ENABLED", "1") == "1"
BOOTSTRAP_TOKEN = os.getenv("BOOTSTRAP_TOKEN", "")
