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
