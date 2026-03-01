#Django-Allauth/Django_Settings/settings.py


from pathlib import Path
from datetime import timedelta
#from dotenv import load_dotenv
#load_dotenv()  # automatically read .env in project root
import os



# ---------------------------------------------------------
# Development Email Backend (console)
# ---------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'auth@mail.paulkeys.dev'
SERVER_EMAIL = 'auth@mail.paulkeys.dev'  # system-level sender
EMAIL_TIMEOUT = 20


# =========================
# EMAIL SETTINGS (Postfix on port 587 via STARTTLS)
# =========================
#EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

#EMAIL_HOST = os.getenv("SMTP_SERVER", "mail.paulkeys.dev")
#EMAIL_PORT = int(os.getenv("SMTP_PORT", 587))

# STARTTLS should be enabled for port 587
#EMAIL_USE_TLS = os.getenv("SMTP_TLS", "True").lower() in ("true", "1", "t")
#EMAIL_USE_SSL = False  # ⚠️ Must stay False (SSL is for port 465)

#EMAIL_HOST_USER = os.getenv("SMTP_USERNAME", "auth@mail.paulkeys.dev")
#EMAIL_HOST_PASSWORD = os.getenv("SMTP_PASSWORD", "")

#DEFAULT_FROM_EMAIL = os.getenv("SMTP_FROM", EMAIL_HOST_USER)
#SERVER_EMAIL = EMAIL_HOST_USER  # Django system-level sender

#EMAIL_TIMEOUT = 20



BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-$1%bow9y6xn%e9(4c5a1*lwjr-8m6x!%kkbuzpdy-6hocs%1dz'
DEBUG = True

# ---------------------------------------------------------
# DEBUG / PRODUCTION FLAG
# ---------------------------------------------------------
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")
IS_PRODUCTION = not DEBUG  # treat debug=False as production

# ---------------------------------------------------------
# SESSION & CSRF COOKIES (DEV vs PROD)
# ---------------------------------------------------------
if IS_PRODUCTION:
    # ---------------- Production ----------------
    ALLOWED_HOSTS = ["hostall.site", "www.hostall.site"]

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SESSION_COOKIE_SAMESITE = "None"   # Required for cross-site
    CSRF_COOKIE_SAMESITE = "None"

    SESSION_COOKIE_DOMAIN = ".hostall.site"  # real domain
    CSRF_COOKIE_DOMAIN = ".hostall.site"

    CORS_ALLOWED_ORIGINS = [
        "https://hostall.site",
        "https://www.hostall.site",
    ]

    CSRF_TRUSTED_ORIGINS = [
        "https://hostall.site",
        "https://www.hostall.site",
    ]
else:
    # ---------------- Development ----------------
    ALLOWED_HOSTS = ["*"]  # allow all dev hosts

    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

    SESSION_COOKIE_SAMESITE = "Lax"  # safe for localhost
    CSRF_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_DOMAIN = None
    CSRF_COOKIE_DOMAIN = None

    # Add any dev frontend ports here
    DEV_FRONTEND_PORTS = [3000, 4000, 4011, 8034, 8035, 5173]
    CORS_ALLOWED_ORIGINS = [f"http://localhost:{p}" for p in DEV_FRONTEND_PORTS] + \
                           [f"http://127.0.0.1:{p}" for p in DEV_FRONTEND_PORTS]

    CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# ---------------------------------------------------------
# Common settings (both dev + prod)
# ---------------------------------------------------------
CSRF_COOKIE_HTTPONLY = False       # frontend JS must read it
SESSION_COOKIE_HTTPONLY = True     # keep session cookie HTTP-only
CORS_ALLOW_CREDENTIALS = True

# Allow standard headers + CSRF
from corsheaders.defaults import default_headers, default_methods

CORS_ALLOW_HEADERS = list(default_headers) + ["x-csrftoken"]
CORS_ALLOW_METHODS = list(default_methods)







# ---------------------------------------------------------
# Installed Applications
# ---------------------------------------------------------
INSTALLED_APPS = [
    # Default Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third-party apps
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'drf_yasg',
    'channels',

    # Local apps
    
    'auth_app.apps.AuthAppConfig',
    
]

# ---------------------------------------------------------
# Middleware
# ---------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # must be first
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]



ROOT_URLCONF = 'Django_Settings.urls'

# ---------------------------------------------------------
# Templates
# ---------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # optional
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'Django_Settings.wsgi.application'

# ---------------------------------------------------------
# Database (PostgreSQL)
# ---------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "knightindustrytech"),
        "USER": os.getenv("DB_USER", "kit"),
        "PASSWORD": os.getenv("DB_PASSWORD", "admin123Pw"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),  # container name in Docker
        "PORT": os.getenv("DB_PORT", "5432"),
        
    }
}




# ---------------------------------------------------------
# Password Validators
# ---------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------
# Localization
# ---------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------
# Static Files
# ---------------------------------------------------------
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------
# Django-Allauth Settings
# ---------------------------------------------------------
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_LOGOUT_ON_GET = True

ACCOUNT_EMAIL_SUBJECT_PREFIX = "[AllAuth] "
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http"



# ---------------------------------------------------------
# Social Account Providers (Allauth)
# ---------------------------------------------------------
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    },
    
}



# ---------------------------------------------------------
# REST Framework & JWT
# ---------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',       # ✅ add this
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # keep JWT
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',  # optional but keeps profile open
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# ---------------------------------------------------------
# Email Backend
# ---------------------------------------------------------
#EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'











GOOGLE_SOCIAL_CALLBACK = "http://127.0.0.1:8034/api/social-login/google/callback/"
















#---------  CENTER LOGGING  ----------------

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ----------------- CENTRAL LOGGING -----------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "auth.log",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "auth_app": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}





# Django static settings
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # where collectstatic puts all files

# Only include extra static dirs if you actually have them
STATICFILES_DIRS = [
    # BASE_DIR / 'extra_static',  # uncomment if you have extra static files outside apps
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Optional Media support (uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


AUTH_USER_MODEL = "auth_app.CustomUser"

# ASGI & Channels
ASGI_APPLICATION = "Django_Settings.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_rabbitmq.core.RabbitmqChannelLayer",
        "CONFIG": {
            "host": "amqp://admin:admin@127.0.0.1:5672/%2f",
        },
    },
}











