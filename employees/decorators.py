from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

from employees.selectors import user_has_permission


def require_permission(codename: str):
    """Deny the view unless the user has the tenant permission codename.

    Unauthenticated users are redirected to login. Authenticated users
    without the permission get PermissionDenied (403).
    """

    def check_permission(user) -> bool:
        if not user.is_authenticated:
            return False
        if user_has_permission(user=user, codename=codename):
            return True
        raise PermissionDenied

    return user_passes_test(check_permission)
