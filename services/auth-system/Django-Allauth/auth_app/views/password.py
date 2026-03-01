from django.http import JsonResponse

def reset_password_api(request):
    return JsonResponse({
        "endpoint": "reset_password_api",
        "status": "ok"
    })


def reset_password_confirm_view(request):
    return JsonResponse({
        "endpoint": "reset_password_confirm_view",
        "status": "ok"
    })
