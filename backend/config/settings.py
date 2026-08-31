"""Django 설정. 로컬 개발용 — 이 프로젝트는 인증/DB 없이 app/ 패키지를 감싸는
무상태 추론 API라서 커스텀 모델은 없다(Django 기본 auth/admin용 sqlite만 존재)."""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_ROOT = BASE_DIR.parent  # doctor/ — app/ 패키지와 데이터 엑셀이 여기 있다

# app.* 모듈을 import할 수 있도록 저장소 루트를 sys.path에 추가.
# (엑셀 상대경로 때문에 프로세스 자체는 항상 REPO_ROOT를 cwd로 실행해야 한다 — manage.py 주석 참고)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SECRET_KEY = "dev-only-not-for-production-1a2b3c4d5e6f"
DEBUG = True
# 이 데모는 원래부터 로컬호스트 전용이 아니다 — vite.config.ts가 host: true로 0.0.0.0에 띄우고,
# docker-compose.yml도 0.0.0.0:8501/:8000으로 포트를 열어서 같은 네트워크(서강대 협업팀 등)의
# 다른 IP에서 접속하는 걸 의도적으로 허용한다. nginx.conf가 원래 Host 헤더를 그대로 백엔드로
# 넘기므로(proxy_set_header Host $host), 접속하는 협업자 IP를 하나하나 하드코딩하면 IP가 바뀌거나
# 새 협업자가 늘 때마다 다시 막힌다(실제로 163.239.25.34 접속 때 DisallowedHost로 막혔던 사례) —
# 이미 DEBUG=True로 스택트레이스까지 노출되는 개발용 설정이라 호스트 목록만 와일드카드로 풀어도
# 추가로 새로 생기는 위험은 크지 않다고 판단해 "*"로 둔다. 진짜 프로덕션 배포 시에는 반드시
# 실제 도메인 목록으로 좁혀야 한다.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "pipeline",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# 실제로는 vite.config.ts(dev)/nginx.conf(prod) 둘 다 /api를 same-origin 프록시로 넘겨서
# 브라우저가 백엔드로 직접 요청하지 않기 때문에 이 목록은 지금 흐름에서는 안 쓰인다 — 그래도 누가 프록시를
# 거치지 않고 8000에 직접 fetch하는 경우(디버깅 등)를 대비해 실제 프론트 포트(8778, 2026-08-31부로
# 8777에서 변경, vite.config.ts에서 커스텀 지정)로 맞춰둔다. 배포 시에는 실제 프론트 도메인으로 교체해야 한다.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8778",
    "http://127.0.0.1:8778",
]
