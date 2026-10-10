from django.http import JsonResponse

from .models import AppSetting

# Still reachable during maintenance: the app's config (so it can show the
# maintenance screen), public content, scheduled jobs and Django admin.
OPEN_DURING_MAINTENANCE = ('/api/v1/app/', '/api/v1/auth/config', '/api/v1/cron/', '/admin/')


class MaintenanceModeMiddleware:
    """While maintenance mode is on, every other API call answers 503 with the admin's message."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith('/api/') and not path.startswith(OPEN_DURING_MAINTENANCE):
            setting = AppSetting.current()
            if setting.maintenance_mode:
                return JsonResponse({"detail": setting.maintenance_message or "The app is under maintenance. Please try again later.", "maintenance": True}, status=503)
        return self.get_response(request)
