from django.shortcuts import render
from products.models import SiteSettings

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow access to admin and management (staff) even in maintenance mode
        if request.path.startswith('/admin/') or request.path.startswith('/management/'):
            return self.get_response(request)

        # Skip for media and static files
        if request.path.startswith('/media/') or request.path.startswith('/static/'):
            return self.get_response(request)

        # Check maintenance mode
        settings = SiteSettings.load()
        if settings.maintenance_mode:
            # Only block non-staff users
            if not request.user.is_staff:
                return render(request, 'maintenance.html', status=503)

        return self.get_response(request)
