import hmac
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def _authorized(request):
    """Return None when bootstrap is disabled, False when unauthorized, True when valid."""
    if not getattr(settings, "BOOTSTRAP_ENABLED", True):
        return None

    token = getattr(settings, "BOOTSTRAP_TOKEN", "")
    if not token:
        return None

    header = request.headers.get("Authorization", "")
    supplied = header.removeprefix("Bearer ").strip()
    return hmac.compare_digest(supplied.encode(), token.encode())


def _reject(auth):
    if auth is None:
        return JsonResponse({"error": "not found"}, status=404)
    if not auth:
        return JsonResponse({"error": "unauthorized"}, status=401)
    return None


def _create_superuser():
    User = get_user_model()
    username = os.environ["DJANGO_SUPERUSER_USERNAME"]
    email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
    password = os.environ["DJANGO_SUPERUSER_PASSWORD"]

    if User.objects.filter(username=username).exists():
        return False

    User.objects.create_superuser(
        username=username, email=email, password=password
    )
    return True


@csrf_exempt
@require_POST
def bootstrap_migrate(request):
    auth = _authorized(request)
    rejection = _reject(auth)
    if rejection is not None:
        return rejection

    call_command("migrate", interactive=False, verbosity=0)
    return JsonResponse({"status": "migrated"})


@csrf_exempt
@require_POST
def bootstrap_admin(request):
    auth = _authorized(request)
    rejection = _reject(auth)
    if rejection is not None:
        return rejection

    created = _create_superuser()
    return JsonResponse({"status": "created" if created else "exists"})
