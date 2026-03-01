# auth_app/views/home.py

from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def home(request):
    _ = request
    """
    Simple home endpoint for health check or API root.
    Returns a JSON message confirming the server is running.
    """
    # The `request` parameters are required by Django view signatures
    # even if it's not directly used.
    return JsonResponse({'message': 'Hello, Django is running!'})
