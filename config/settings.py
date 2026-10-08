"""Minimal settings: no admin/auth/sessions, because this is a stateless JSON API."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes"}


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")

INSTALLED_APPS = ["stations", "routing"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# File-based cache so every worker process shares route results (and the map page can
# find a route that another worker computed). No extra infrastructure required.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(BASE_DIR / ".cache"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

# ---- Fuel planning ----------------------------------------------------------------
FUEL_MAX_RANGE_MILES = float(os.environ.get("FUEL_MAX_RANGE_MILES", 500))
FUEL_MPG = float(os.environ.get("FUEL_MPG", 10))
# Range already in the tank at the start. Assumption: the vehicle leaves with a full
# tank, and that initial fuel is not counted as spend (only fuel bought en route is).
FUEL_INITIAL_RANGE_MILES = float(os.environ.get("FUEL_INITIAL_RANGE_MILES", FUEL_MAX_RANGE_MILES))
# Stations must be within this many miles of the route. We try the narrowest corridor
# first and only widen it (no extra API calls) if the route can't be driven otherwise.
CORRIDOR_MILES = (10.0, 25.0, 50.0)
ROUTE_MAX_POINTS = 3000  # route vertices kept for projection and the response geometry

# ---- External services (free, no API key) --------------------------------------------
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
OSRM_TIMEOUT = 25
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_TIMEOUT = 8
# Nominatim's usage policy requires an identifying User-Agent. Put your contact in it.
NOMINATIM_USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "fuel-route-api/1.0 (coding assessment)")

ROUTE_CACHE_TTL = 60 * 60 * 24

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"