from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render

from . import service_manager


def _is_superuser(user):
    return user.is_authenticated and user.is_active and user.is_superuser


def _selected_log_component(request):
    component_id = request.GET.get("log") or "upload_worker"
    if component_id not in service_manager.COMPONENTS:
        component_id = "upload_worker"
    return component_id


@login_required
@user_passes_test(_is_superuser, login_url="permission_denied")
def dashboard(request):
    selected_log = _selected_log_component(request)
    context = {
        "components": service_manager.get_all_component_statuses(),
        "selected_log": selected_log,
        "selected_log_label": service_manager.COMPONENTS[selected_log]["label"],
        "log_text": service_manager.tail_log(selected_log),
    }
    return render(request, "config/dashboard.html", context)


@login_required
@user_passes_test(_is_superuser, login_url="permission_denied")
def start_component(request, component_id):
    if request.method != "POST":
        return redirect("config:dashboard")

    concurrency = request.POST.get("concurrency")
    success, message = service_manager.start_component(component_id, concurrency)
    (messages.success if success else messages.error)(request, message)
    return redirect("config:dashboard")


@login_required
@user_passes_test(_is_superuser, login_url="permission_denied")
def stop_component(request, component_id):
    if request.method != "POST":
        return redirect("config:dashboard")

    success, message = service_manager.stop_component(component_id)
    (messages.success if success else messages.warning)(request, message)
    return redirect("config:dashboard")


@login_required
@user_passes_test(_is_superuser, login_url="permission_denied")
def restart_component(request, component_id):
    if request.method != "POST":
        return redirect("config:dashboard")

    concurrency = request.POST.get("concurrency")
    success, message = service_manager.restart_component(component_id, concurrency)
    (messages.success if success else messages.error)(request, message)
    return redirect("config:dashboard")

