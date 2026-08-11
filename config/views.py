from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods


@login_required
@require_http_methods(["GET"])
def account_profile(request: HttpRequest) -> HttpResponse:
    return render(request, "account/profile.html")
