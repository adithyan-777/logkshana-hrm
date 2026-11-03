from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from users.forms import UsernameChangeForm


@login_required
@require_http_methods(["GET", "POST"])
def account_profile(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = UsernameChangeForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Username updated.")
            return redirect("account_profile")
        messages.error(request, "Username not updated. Please fix the errors below.")
        return render(request, "account/profile.html", {"form": form})

    return render(
        request,
        "account/profile.html",
        {"form": UsernameChangeForm(user=request.user)},
    )


@login_required
@require_http_methods(["GET"])
def settings_page(request: HttpRequest) -> HttpResponse:
    return render(request, "settings/index.html")
