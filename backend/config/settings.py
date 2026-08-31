"""
Django settings for GroundTruth backend.

Phase 1 範圍：專案初始化、DB Schema、CRUD API。
JWT 細部設定（FR-1a）留待後續 Phase 補齊，這裡先安裝套件保留擴充點。
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me-at-least-32-bytes")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.crm",
    "apps.erp",
    "apps.procurement",
    "apps.audit",
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

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "groundtruth"),
        "USER": os.environ.get("POSTGRES_USER", "groundtruth"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "groundtruth"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# Phase 1 不使用 Django 內建 auth User model 做業務邏輯（roles/users 為自訂表），
# 但保留 contrib.auth 供 admin 後台與 session 使用。

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hant"
TIME_ZONE = "Asia/Taipei"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}
REFRESH_COOKIE_NAME = "groundtruth_refresh"
REFRESH_COOKIE_SECURE = os.environ.get("REFRESH_COOKIE_SECURE", "false").lower() == "true"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Phase 1：先開放 AllowAny 以利 CRUD 驗收；使用者對外 JWT 認證（FR-1a 前半）留待 Vue 前端串接時（Phase 4）套用。
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    # Phase 2：n8n↔Django 內部端點另外用 InternalApiKeyAuthentication + IsAuthenticated 明確保護，
    # 不放進 DEFAULT_AUTHENTICATION_CLASSES 全域套用，避免影響一般 CRUD 端點的 AllowAny 行為。
}

# n8n ↔ Django 內部服務認證（FR-1a）與流程協調用設定。
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
N8N_INQUIRY_WEBHOOK_URL = os.environ.get("N8N_INQUIRY_WEBHOOK_URL", "http://localhost:5678/webhook/inquiry")
N8N_INQUIRY_PARSE_WEBHOOK_URL = os.environ.get(
    "N8N_INQUIRY_PARSE_WEBHOOK_URL", "http://localhost:5678/webhook/purchase-request-candidate",
)
# FR-6a：供應商模糊比對案件核准後，Django 主動呼叫這支 n8n webhook，交還流程重新走
# 遮罩→LLM 解析（見 services/inquiry_resume_service.py、n8n/workflows/inquiry-flow.json 的續傳分支）。
N8N_RESUME_WEBHOOK_URL = os.environ.get("N8N_RESUME_WEBHOOK_URL", "http://localhost:5678/webhook/inquiry/resume")
