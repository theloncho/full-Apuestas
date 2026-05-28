from .base import *  # noqa: F401, F403

DEBUG = True

# En desarrollo, usar InMemoryChannelLayer si Redis no está disponible
# (el docker-compose ya provee Redis)
