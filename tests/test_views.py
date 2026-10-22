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
