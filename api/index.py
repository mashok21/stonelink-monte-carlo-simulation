import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DJANGO_ROOT = PROJECT_ROOT / "backend"

sys.path.insert(0, str(DJANGO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stonelink_backend.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
application = app
