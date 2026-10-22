# Django on Cloudflare Workers — Implementation Plan

**Goal:** Run a minimal Django site with a homepage and admin on Cloudflare Workers, backed by one Durable Object, at `https://dj.heroic.ch`, deployed only through CLI and CI.

**Architecture:** A Python Worker forwards every request to a singleton SQLite-backed Durable Object that serves Django's WSGI app through `django-cf`. Django dependencies are exported from the uv lock and vendored into `src/vendor`; the Cloudflare CLI (`cf`) builds and deploys the Worker using `cloudflare.config.ts` and `wrangler.config.ts`. A token-protected endpoint runs migrations and creates the first admin.

**Tech Stack:** Python 3.12+, Django 5.2.6, `django-cf` 0.2.17, uv, Cloudflare CLI 1.0.0-beta.20, Wrangler 4.151.3, Node 22.18+, GitHub Actions.

**Spec:** `README.md`

## Global Constraints

- Use `uv` for all Python dependency operations. Never use `pip`.
- Use `cf` for build, dev, deploy, zone checks, and account operations. Do not use `pywrangler`.
- Pin `cf` and `wrangler` in `package.json`; pin Python dependencies in `pyproject.toml` and `uv.lock`.
- Python runtime dependencies only: `django==5.2.6`, `django-cf==0.2.17`, `tzdata==2026.5`.
- Hostname: `dj.heroic.ch`. Zone: `heroic.ch`, active in the target Cloudflare account.
- No Cloudflare dashboard steps for routine work. The one-time API token creation is the only exception.
- Never commit secrets, `.dev.vars`, `src/vendor/`, `staticfiles/`, or `.cloudflare/`.
- Durable Object storage has no transactions. Do not rely on `transaction.atomic()`.
- Test command: `DJANGO_TEST=1 PYTHONPATH=src uv run python -m unittest discover -s tests -v`.
- Commit after every task.

---

### Task 1: Django scaffold and homepage

**Files:**
- Create: `pyproject.toml`
- Create: `uv.lock` (generated)
- Create: `src/manage.py`
- Create: `src/app/__init__.py`
- Create: `src/app/settings.py`
- Create: `src/app/urls.py`
- Create: `src/app/views.py`
- Create: `src/app/wsgi.py`
- Create: `src/app/templates/home.html`
- Create: `tests/test_views.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.settings` with `BOOTSTRAP_TOKEN`; URL name `home`; `app.wsgi.application`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_views.py
import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

import django

django.setup()

from django.test import Client, SimpleTestCase


class HomepageTests(SimpleTestCase):
    def test_homepage_renders(self):
        response = Client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django on Cloudflare Workers")
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `DJANGO_TEST=1 PYTHONPATH=src uv run python -m unittest discover -s tests -v`
Expected: FAIL. `uv` may report a missing project or Python may report a missing module; no tests pass.

- [ ] **Step 3: Create the Python project**

```toml
# pyproject.toml
[project]
name = "cloudflare-django"
version = "0.1.0"
description = "Django proof of concept on Cloudflare Workers"
requires-python = ">=3.12"
dependencies = [
    "django==5.2.6",
    "django-cf==0.2.17",
    "tzdata==2026.5",
]
```

Run: `uv sync`
Expected: creates `.venv` and `uv.lock`.

```python
# src/manage.py
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Did you run `uv sync`?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

```python
# src/app/__init__.py
```

```python
# src/app/settings.py
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
```

```python
# src/app/views.py
from django.shortcuts import render


def home(request):
    return render(request, "home.html")
```

```python
# src/app/urls.py
from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("admin/", admin.site.urls),
]
```

```python
# src/app/wsgi.py
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

application = get_wsgi_application()
```

```html
<!-- src/app/templates/home.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Django on Cloudflare Workers</title>
  </head>
  <body>
    <main>
      <h1>Django on Cloudflare Workers</h1>
      <p>Homepage served by Django in a Python Worker.</p>
      <p><a href="/admin/">Django admin</a></p>
    </main>
  </body>
</html>
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `DJANGO_TEST=1 PYTHONPATH=src uv run python -m unittest discover -s tests -v`
Expected: `OK` with one test.

- [ ] **Step 5: Run Django's system check**

Run: `cd src && DJANGO_TEST=1 uv run python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src tests
git commit -m "feat: scaffold Django homepage"
```

---

### Task 2: Token-protected bootstrap endpoints

**Files:**
- Create: `src/app/bootstrap.py`
- Create: `tests/test_bootstrap.py`
- Modify: `src/app/urls.py`
- Modify: `src/app/settings.py` (already contains `BOOTSTRAP_TOKEN`; no change expected)

**Interfaces:**
- Consumes: `settings.BOOTSTRAP_TOKEN`; `django.core.management.call_command`.
- Produces: `POST /__bootstrap/migrate/`, `POST /__bootstrap/admin/`; `app.bootstrap._create_superuser()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bootstrap.py
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

import django

django.setup()

from django.test import Client, SimpleTestCase, override_settings


@override_settings(BOOTSTRAP_TOKEN="", BOOTSTRAP_ENABLED=True)
class BootstrapDisabledTests(SimpleTestCase):
    def test_migrate_returns_404_when_token_unset(self):
        response = Client().post("/__bootstrap/migrate/")
        self.assertEqual(response.status_code, 404)

    def test_admin_returns_404_when_token_unset(self):
        response = Client().post("/__bootstrap/admin/")
        self.assertEqual(response.status_code, 404)


@override_settings(BOOTSTRAP_TOKEN="test-token", BOOTSTRAP_ENABLED=False)
class BootstrapFlagTests(SimpleTestCase):
    def test_migrate_returns_404_when_disabled(self):
        response = Client().post(
            "/__bootstrap/migrate/", HTTP_AUTHORIZATION="Bearer test-token"
        )
        self.assertEqual(response.status_code, 404)


@override_settings(BOOTSTRAP_TOKEN="test-token", BOOTSTRAP_ENABLED=True)
class BootstrapAuthTests(SimpleTestCase):
    def test_migrate_returns_401_with_wrong_token(self):
        response = Client().post(
            "/__bootstrap/migrate/", HTTP_AUTHORIZATION="Bearer wrong"
        )
        self.assertEqual(response.status_code, 401)

    def test_admin_returns_401_without_token(self):
        response = Client().post("/__bootstrap/admin/")
        self.assertEqual(response.status_code, 401)

    def test_get_is_not_allowed(self):
        response = Client().get(
            "/__bootstrap/migrate/", HTTP_AUTHORIZATION="Bearer test-token"
        )
        self.assertEqual(response.status_code, 405)

    @patch("app.bootstrap.call_command")
    def test_migrate_runs_with_valid_token(self, call_command):
        response = Client().post(
            "/__bootstrap/migrate/", HTTP_AUTHORIZATION="Bearer test-token"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "migrated"})
        call_command.assert_called_once_with(
            "migrate", interactive=False, verbosity=0
        )

    @patch("app.bootstrap._create_superuser", return_value=True)
    def test_admin_creates_user(self, create_superuser):
        response = Client().post(
            "/__bootstrap/admin/", HTTP_AUTHORIZATION="Bearer test-token"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "created"})
        create_superuser.assert_called_once_with()

    @patch("app.bootstrap._create_superuser", return_value=False)
    def test_admin_is_idempotent(self, create_superuser):
        response = Client().post(
            "/__bootstrap/admin/", HTTP_AUTHORIZATION="Bearer test-token"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "exists"})
        create_superuser.assert_called_once_with()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `DJANGO_TEST=1 PYTHONPATH=src uv run python -m unittest discover -s tests -v`
Expected: FAIL with `AttributeError` or 404 for the missing routes.

- [ ] **Step 3: Implement the bootstrap views**

```python
# src/app/bootstrap.py
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
```

- [ ] **Step 4: Wire the URLs**

```python
# src/app/urls.py
from django.contrib import admin
from django.urls import path

from . import bootstrap, views

urlpatterns = [
    path("", views.home, name="home"),
    path("admin/", admin.site.urls),
    path("__bootstrap/migrate/", bootstrap.bootstrap_migrate),
    path("__bootstrap/admin/", bootstrap.bootstrap_admin),
]
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `DJANGO_TEST=1 PYTHONPATH=src uv run python -m unittest discover -s tests -v`
Expected: `OK` with all tests passing.

- [ ] **Step 6: Commit**

```bash
git add src/app/bootstrap.py src/app/urls.py tests/test_bootstrap.py
git commit -m "feat: add token-protected bootstrap endpoints"
```

---

### Task 3: Worker entrypoint, cf configuration, and dependency vendoring

**Files:**
- Create: `package.json`
- Create: `wrangler.jsonc` (temporary)
- Create: `scripts/vendor.sh`
- Create: `src/index.py`
- Create: `cloudflare.config.ts` (generated by `cf migrate`, then edited)
- Create: `wrangler.config.ts` (generated by `cf migrate`, then edited)
- Create: `.gitignore`

**Interfaces:**
- Consumes: `app.wsgi.application`; runtime secrets exposed through `os.environ`.
- Produces: Worker name `cloudflare-django`; Durable Object class `DjangoDO`; binding `DO_STORAGE`; `scripts/vendor.sh`; `cf build` and `cf dev`.

- [ ] **Step 1: Create Node configuration and ignore rules**

```gitignore
# .gitignore
node_modules/
.venv/
__pycache__/
*.pyc
.dev.vars
.wrangler/
.cloudflare/
src/vendor/
staticfiles/*
!staticfiles/.gitkeep
.vendor-requirements.txt
```

```json
{
  "name": "cloudflare-django",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "cf build",
    "dev": "cf dev",
    "deploy": "cf deploy"
  },
  "devDependencies": {
    "cf": "1.0.0-beta.20",
    "wrangler": "4.151.3"
  }
}
```

```jsonc
// wrangler.jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "cloudflare-django",
  "main": "src/index.py",
  "compatibility_flags": ["python_workers"],
  "compatibility_date": "2026-03-08",
  "assets": { "directory": "./staticfiles" },
  "build": {
    "command": "WORKERS_CI=1 uv run --locked python src/manage.py collectstatic --noinput"
  },
  "python_modules": {
    "exclude": [
      "**/*.pyc",
      "**/__pycache__",
      "**/*.po",
      "**/*.css",
      "**/*.js",
      "**/*.svg",
      "**/*.png",
      "**/*.jpg"
    ]
  },
  "observability": { "enabled": true },
  "durable_objects": {
    "bindings": [{ "name": "DO_STORAGE", "class_name": "DjangoDO" }]
  },
  "migrations": [{ "tag": "v1", "new_sqlite_classes": ["DjangoDO"] }]
}
```

Run: `mkdir -p staticfiles && touch staticfiles/.gitkeep`

Run: `npm install`
Expected: creates `node_modules` and `package-lock.json` with `cf` and `wrangler` installed.

- [ ] **Step 2: Commit the scaffold so `cf migrate` has a clean worktree**

```bash
git add .gitignore package.json package-lock.json wrangler.jsonc staticfiles/.gitkeep
git commit -m "chore: add Cloudflare tooling"
```

Run: `git status --porcelain`
Expected: no output. `cf migrate` refuses to run otherwise.

- [ ] **Step 3: Run the migration**

Run: `npx cf migrate`
Expected: creates `cloudflare.config.ts` and `wrangler.config.ts`; reports required Durable Object follow-up work.

- [ ] **Step 4: Replace `cloudflare.config.ts` with the resolved configuration**

```ts
// cloudflare.config.ts
import { bindings, defineConfig, exports } from "cf/config";

export default defineConfig({
	worker: {
		name: "cloudflare-django",
		compatibilityDate: "2026-03-08",
		compatibilityFlags: ["python_workers"],
		entrypoint: "src/index.py",
		domains: ["dj.heroic.ch"],
		observability: { enabled: true },
		exports: {
			DjangoDO: exports.durableObject({ storage: "sqlite" }),
		},
		env: {
			DO_STORAGE: bindings.durableObject({
				worker: "cloudflare-django",
				exportName: "DjangoDO",
			}),
			BOOTSTRAP_ENABLED: bindings.text("1"),
			DJANGO_SECRET_KEY: bindings.secret(),
			BOOTSTRAP_TOKEN: bindings.secret(),
			DJANGO_SUPERUSER_USERNAME: bindings.secret(),
			DJANGO_SUPERUSER_EMAIL: bindings.secret(),
			DJANGO_SUPERUSER_PASSWORD: bindings.secret(),
		},
	},
});
```

- [ ] **Step 5: Update `wrangler.config.ts`**

```ts
// wrangler.config.ts
import { defineWranglerConfig } from "wrangler/experimental-config";

export default defineWranglerConfig({
	pythonModules: {
		exclude: [
			"**/*.pyc",
			"**/__pycache__",
			"**/*.po",
			"**/*.css",
			"**/*.js",
			"**/*.svg",
			"**/*.png",
			"**/*.jpg",
		],
	},
	build: {
		command:
			"WORKERS_CI=1 uv run --locked python src/manage.py collectstatic --noinput",
	},
	assetsDirectory: "./staticfiles",
});
```

- [ ] **Step 6: Delete the Wrangler configuration**

```bash
git rm wrangler.jsonc
```

- [ ] **Step 7: Create the Worker entrypoint**

```python
# src/index.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))

from app.wsgi import application
from django_cf import DjangoCFDurableObject
from workers import DurableObject, WorkerEntrypoint


class DjangoDO(DjangoCFDurableObject, DurableObject):
    def get_app(self):
        return application


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        do_id = self.env.DO_STORAGE.idFromName("singleton_instance")
        stub = self.env.DO_STORAGE.get(do_id)
        return await stub.fetch(request)
```

- [ ] **Step 8: Create the vendoring script**

```bash
#!/usr/bin/env bash
# scripts/vendor.sh
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf src/vendor
uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes \
  --output-file .vendor-requirements.txt
uv pip install --target src/vendor --no-compile -r .vendor-requirements.txt
rm -f .vendor-requirements.txt
```

Run: `chmod +x scripts/vendor.sh`
Run: `uv sync --locked`
Run: `./scripts/vendor.sh`
Expected: `src/vendor/django` exists and is about 34 MB.

- [ ] **Step 9: Build and verify the bundle**

Run: `npx cf build`
Expected: build completes. Wrangler validates `assets.directory` before running the build command, so `staticfiles/.gitkeep` must already exist.

Run: `test -d .cloudflare/output/v0/workers/default/bundle/vendor/django && echo BUNDLED`
Expected: prints `BUNDLED`.

Run: `npx cf deploy --dry-run`
Expected: reports the `DO_STORAGE` binding, approximately 6,000 KiB upload, and no errors.

- [ ] **Step 10: Verify locally**

Run: `npx cf dev` in one terminal.
Run: `curl -s http://localhost:8787/ | grep -q "Django on Cloudflare Workers" && echo OK`
Expected: prints `OK`. Stop the dev server afterwards.

- [ ] **Step 11: Commit**

```bash
git add .gitignore package.json package-lock.json cloudflare.config.ts wrangler.config.ts scripts/vendor.sh src/index.py
git commit -m "feat: configure cf Worker and dependency vendoring"
```

---

### Task 4: Local deploy script

**Files:**
- Create: `scripts/deploy.sh`
- Create: `.dev.vars.example`

**Interfaces:**
- Consumes: `scripts/vendor.sh`, `cf`, environment variables listed below.
- Produces: one-command deploy and bootstrap at `https://dj.heroic.ch`.

- [ ] **Step 1: Create the deploy script**

```bash
#!/usr/bin/env bash
# scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
: "${DJANGO_SECRET_KEY:?set DJANGO_SECRET_KEY}"
: "${BOOTSTRAP_TOKEN:?set BOOTSTRAP_TOKEN}"
: "${DJANGO_SUPERUSER_USERNAME:?set DJANGO_SUPERUSER_USERNAME}"
: "${DJANGO_SUPERUSER_EMAIL:?set DJANGO_SUPERUSER_EMAIL}"
: "${DJANGO_SUPERUSER_PASSWORD:?set DJANGO_SUPERUSER_PASSWORD}"

command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

if ! npx cf zones list 2>/dev/null | grep -q "heroic.ch"; then
  echo "heroic.ch was not found in this account's zones" >&2
  exit 1
fi

uv sync --locked
npm ci
./scripts/vendor.sh

secrets_file="$(mktemp)"
trap 'rm -f "$secrets_file"' EXIT

jq -n \
  --arg secret_key "$DJANGO_SECRET_KEY" \
  --arg bootstrap_token "$BOOTSTRAP_TOKEN" \
  --arg username "$DJANGO_SUPERUSER_USERNAME" \
  --arg email "$DJANGO_SUPERUSER_EMAIL" \
  --arg password "$DJANGO_SUPERUSER_PASSWORD" \
  '{
    DJANGO_SECRET_KEY: $secret_key,
    BOOTSTRAP_TOKEN: $bootstrap_token,
    DJANGO_SUPERUSER_USERNAME: $username,
    DJANGO_SUPERUSER_EMAIL: $email,
    DJANGO_SUPERUSER_PASSWORD: $password
  }' > "$secrets_file"

npx cf deploy --secrets-file "$secrets_file"

for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null https://dj.heroic.ch/; then
    break
  fi
  sleep 5
done

curl -fsS -X POST \
  -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
  https://dj.heroic.ch/__bootstrap/migrate/
echo
curl -fsS -X POST \
  -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
  https://dj.heroic.ch/__bootstrap/admin/
echo
```

Run: `chmod +x scripts/deploy.sh`
Run: `bash -n scripts/deploy.sh`
Expected: no syntax errors.

- [ ] **Step 2: Create the local secrets example**

```dotenv
# .dev.vars.example
DJANGO_SECRET_KEY=replace-me
BOOTSTRAP_TOKEN=replace-me
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=replace-me
```

- [ ] **Step 3: Commit**

```bash
git add scripts/deploy.sh .dev.vars.example
git commit -m "feat: add one-command deploy script"
```

---

### Task 5: GitHub Actions deployment

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: repository secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DJANGO_SECRET_KEY`, `BOOTSTRAP_TOKEN`, `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`.
- Produces: deployment on every push to `main`.

- [ ] **Step 1: Create the workflow**

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

concurrency:
  group: deploy-production
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      CF_SEND_TELEMETRY: "false"
      BOOTSTRAP_TOKEN: ${{ secrets.BOOTSTRAP_TOKEN }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Install dependencies
        run: |
          uv sync --locked
          npm ci

      - name: Run tests
        run: DJANGO_TEST=1 PYTHONPATH=src uv run python -m unittest discover -s tests -v

      - name: Vendor runtime dependencies
        run: ./scripts/vendor.sh

      - name: Build
        run: npx cf build

      - name: Write secrets file
        env:
          DJANGO_SECRET_KEY: ${{ secrets.DJANGO_SECRET_KEY }}
          BOOTSTRAP_TOKEN: ${{ secrets.BOOTSTRAP_TOKEN }}
          DJANGO_SUPERUSER_USERNAME: ${{ secrets.DJANGO_SUPERUSER_USERNAME }}
          DJANGO_SUPERUSER_EMAIL: ${{ secrets.DJANGO_SUPERUSER_EMAIL }}
          DJANGO_SUPERUSER_PASSWORD: ${{ secrets.DJANGO_SUPERUSER_PASSWORD }}
        run: |
          jq -n \
            --arg secret_key "$DJANGO_SECRET_KEY" \
            --arg bootstrap_token "$BOOTSTRAP_TOKEN" \
            --arg username "$DJANGO_SUPERUSER_USERNAME" \
            --arg email "$DJANGO_SUPERUSER_EMAIL" \
            --arg password "$DJANGO_SUPERUSER_PASSWORD" \
            '{
              DJANGO_SECRET_KEY: $secret_key,
              BOOTSTRAP_TOKEN: $bootstrap_token,
              DJANGO_SUPERUSER_USERNAME: $username,
              DJANGO_SUPERUSER_EMAIL: $email,
              DJANGO_SUPERUSER_PASSWORD: $password
            }' > "$RUNNER_TEMP/secrets.json"

      - name: Deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: npx cf deploy --prebuilt --secrets-file "$RUNNER_TEMP/secrets.json"

      - name: Remove secrets file
        if: always()
        run: rm -f "$RUNNER_TEMP/secrets.json"

      - name: Bootstrap site
        if: env.BOOTSTRAP_TOKEN != ''
        run: |
          for i in $(seq 1 30); do
            if curl -fsS -o /dev/null https://dj.heroic.ch/; then
              break
            fi
            sleep 5
          done
          curl -fsS -X POST -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
            https://dj.heroic.ch/__bootstrap/migrate/
          echo
          curl -fsS -X POST -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
            https://dj.heroic.ch/__bootstrap/admin/
```

- [ ] **Step 2: Validate the workflow file**

Run: `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/deploy.yml"); puts "YAML OK"'`
Expected: prints `YAML OK`.

- [ ] **Step 3: Set repository secrets before the first push**

Run these once, replacing the admin values:

```bash
gh secret set CLOUDFLARE_API_TOKEN --body "$CLOUDFLARE_API_TOKEN"
gh secret set CLOUDFLARE_ACCOUNT_ID --body "$CLOUDFLARE_ACCOUNT_ID"
gh secret set DJANGO_SECRET_KEY --body "$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
gh secret set BOOTSTRAP_TOKEN --body "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
gh secret set DJANGO_SUPERUSER_USERNAME --body "admin"
gh secret set DJANGO_SUPERUSER_EMAIL --body "admin@example.com"
gh secret set DJANGO_SUPERUSER_PASSWORD --body "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

Record the generated admin password in a password manager; it is not recoverable from the secret.

- [ ] **Step 4: Commit and push**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: deploy on push to main"
git push
```

- [ ] **Step 5: Watch the workflow**

Run: `gh run watch`
Expected: the workflow succeeds.

---

### Task 6: First production deploy and verification

**Files:**
- None.

**Interfaces:**
- Consumes: all prior tasks; Cloudflare API token; active `heroic.ch` zone.
- Produces: working site at `https://dj.heroic.ch`.

- [ ] **Step 1: Confirm the zone**

Run: `cf zones list | grep heroic.ch`
Expected: one row for `heroic.ch`. If absent, stop and add the zone to the account before deploying.

- [ ] **Step 2: Create the API token**

Create a token in the Cloudflare dashboard with these permissions:
- Account → Workers Scripts → Edit
- Account → Durable Objects → Edit
- Zone → DNS → Edit
- Zone → Workers Routes → Edit
- Zone → Zone → Read

Store it and the account ID as `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` locally.

- [ ] **Step 3: Verify the local deploy script**

Set the remaining environment variables from `.dev.vars.example`, then run: `./scripts/deploy.sh`
Expected: the redeploy succeeds, both bootstrap calls return JSON success (the admin call reports `exists`), and the script exits 0.

- [ ] **Step 4: Verify the site**

Run: `curl -s -o /dev/null -w '%{http_code}\n' https://dj.heroic.ch/`
Expected: `200`.

Run: `curl -s -o /dev/null -w '%{http_code}\n' https://dj.heroic.ch/admin/`
Expected: `200` or `302`.

- [ ] **Step 5: Verify admin and persistence**

1. Sign in at `https://dj.heroic.ch/admin/` with the bootstrap admin credentials.
2. Confirm the admin CSS loads.
3. Confirm the user and session data survive a refresh.
4. Trigger a second deployment: `git commit --allow-empty -m "chore: redeploy" && git push` and confirm the admin session data still exists.

- [ ] **Step 6: Disable bootstrap**

1. Change `BOOTSTRAP_ENABLED: bindings.text("1")` to `bindings.text("0")` in `cloudflare.config.ts`.
2. Run: `gh secret delete BOOTSTRAP_TOKEN`
3. Commit and push the config change.

Expected: the workflow skips its bootstrap step (no token secret), and `POST https://dj.heroic.ch/__bootstrap/migrate/` returns `404` even with the old token.

- [ ] **Step 7: Verify the GitHub Actions deployment**

Confirm the latest `main` workflow run is green and `https://dj.heroic.ch/` still returns `200`.

---

### Task 7: Record results in the README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: results from Tasks 1–6.
- Produces: a README that describes the working system rather than only the plan.

- [ ] **Step 1: Update the status**

Replace the paragraph that calls the README an implementation plan with a short status paragraph: deployed, URL, and deploy command.

- [ ] **Step 2: Record verification results**

Add a `## Verification results` section with:
- Deployment date.
- Workflow run URL.
- Bundle size from `cf deploy`.
- Homepage and admin status codes.
- Confirmation that bootstrap endpoints return `404` after removing the secret.

- [ ] **Step 3: Update limitations**

State whether Django admin, sessions, migrations, and persistence worked. Note any admin screens that failed due to the Durable Object backend.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: record deployment results"
git push
```

---

## Self-review notes

- Spec coverage: homepage, admin, Durable Object database, custom domain, uv, cf-first deploy, vendoring, token bootstrap, local script, CI, and verification all have tasks.
- The plan deliberately keeps `cf` as the only build/deploy tool after the spike; no `pywrangler` step remains.
- `domains: ["dj.heroic.ch"]` is used instead of Wrangler routes, matching the `cf` configuration reference.
- Secret names match across settings, deploy script, and workflow.
