from django.http import JsonResponse


def social_login_api(request, provider=None):
    """
    Basic placeholder response for initiating social login.
    """
    return JsonResponse({
        "endpoint": "social_login_api",
        "provider": provider,
        "status": "ok",
        "message": f"Social login initiated for: {provider}"
    })


def social_login_callback(request):
    """
    Basic placeholder response for handling OAuth callback.
    """
    return JsonResponse({
        "endpoint": "social_login_callback",
        "status": "ok",
        "message": "Social login callback received"
    })
