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
