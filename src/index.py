import os

from django_cf import DjangoCFDurableObject
from workers import DurableObject, WorkerEntrypoint

ENV_KEYS = (
    "BOOTSTRAP_ENABLED",
    "DJANGO_SECRET_KEY",
    "BOOTSTRAP_TOKEN",
    "DJANGO_SUPERUSER_USERNAME",
    "DJANGO_SUPERUSER_EMAIL",
    "DJANGO_SUPERUSER_PASSWORD",
)


class DjangoDO(DjangoCFDurableObject, DurableObject):
    def get_app(self):
        for key in ENV_KEYS:
            value = getattr(self.env, key, None)
            if value is not None:
                os.environ[key] = value

        from app.wsgi import application

        return application


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        do_id = self.env.DO_STORAGE.idFromName("singleton_instance")
        stub = self.env.DO_STORAGE.get(do_id)
        return await stub.fetch(request)
