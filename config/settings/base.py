from decimal import ROUND_HALF_UP, getcontext
import environ
from pathlib import Path

# ─── Precisión decimal GLOBAL — crítico para montos ──────────────────────────
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP

env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = env('SECRET_KEY')

# Seguridad: Cargar hosts permitidos del entorno (fallback a localhost para dev)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])

# ─── Aplicaciones ────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Terceros
    'channels',
    'rest_framework',
    'drf_spectacular',
    'django_celery_beat',
    # Apps propias
    'apps.users',
    'apps.wallet',
    'apps.betting',
    'apps.odds',
    'apps.audit',
    'apps.fraud',
    'apps.dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
ASGI_APPLICATION = 'config.asgi.application'

# ─── Base de datos ───────────────────────────────────────────────────────────
DATABASES = {
    'default': env.db()
}

# ─── Channels + Redis ────────────────────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [env('REDIS_URL', default='redis://localhost:6379/0')],
        },
    },
}

# ─── Celery ──────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'America/Lima'

# ─── Celery Beat: tareas periódicas ─────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    'fetch-live-odds-every-30min': {
        'task': 'apps.odds.tasks.fetch_and_sync_odds',
        'schedule': crontab(minute='*/30'),
    },
    'sync-live-scores-every-5min': {
        'task': 'apps.odds.tasks.sync_live_scores',
        'schedule': crontab(minute='*/5'),
    },
}

# ─── The Odds API ────────────────────────────────────────────────────────────
ODDS_API_KEY = env('ODDS_API_KEY', default='')
ODDS_API_BASE_URL = 'https://api.the-odds-api.com/v4'
ODDS_API_SPORT = 'soccer_conmebol_copa_libertadores'           # Fútbol (Copa Libertadores)
ODDS_API_REGIONS = 'eu'             # Europa = formato decimal
ODDS_API_MARKETS = 'h2h,totals'    # 1X2 + Over/Under

# ─── Cache (idempotencia) ───────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://localhost:6379/0'),
    }
}

# ─── Internacionalización ───────────────────────────────────────────────────
LANGUAGE_CODE = 'es-pe'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True

# ─── Archivos estáticos ─────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# ─── Autenticación ──────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'
LOGIN_URL = '/users/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/users/login/'

# ─── DRF ─────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/minute',
        'user': '60/minute',
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'FairBet Lab API',
    'DESCRIPTION': 'Plataforma educativa de apuestas deportivas con moneda virtual.',
    'VERSION': '1.0.0',
}

# ─── Configuración de odds ──────────────────────────────────────────────────
OPERATOR_MARGIN = 0.05  # 5% margen por defecto

# ─── Juego responsable ──────────────────────────────────────────────────────
RESPONSIBLE_GAMBLING_MESSAGE = (
    "Apostar puede crear adicción. Juega responsablemente. "
    "Línea de ayuda: 0800-00000"
)

# ─── Templates ───────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.users.context_processors.responsible_gambling',
            ],
        },
    },
]

# ─── Logging estructurado (JSON) ────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
