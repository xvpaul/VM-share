# /app/methods/manager/__init__.py
from .ProcessManager import get_proc_registry
from .WebsockifyService import WebsockifyService

def get_websockify_service() -> WebsockifyService:
    return WebsockifyService(get_proc_registry())