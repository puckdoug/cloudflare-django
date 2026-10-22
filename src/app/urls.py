from django.contrib import admin
from django.urls import path

from . import bootstrap, views

urlpatterns = [
    path("", views.home, name="home"),
    path("admin/", admin.site.urls),
    path("__bootstrap/migrate/", bootstrap.bootstrap_migrate),
    path("__bootstrap/admin/", bootstrap.bootstrap_admin),
]
