from django.http import Http404
from django_tenants.utils import get_public_schema_name


class CompanyMembershipMiddleware:
    """Deny authenticated users access to company schemas they don't belong to.

    Replaces ``tenant_users``' TenantAccessMiddleware. Membership is tracked
    on ``Company.members`` (owners are auto-added on save). Non-members get
    a 404 so company existence isn't leaked. Anonymous users, the public
    schema, and superusers pass through untouched.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        user = getattr(request, "user", None)
        if (
            tenant is not None
            and tenant.schema_name != get_public_schema_name()
            and user is not None
            and user.is_authenticated
            and not user.is_superuser
            and not tenant.members.filter(pk=user.pk).exists()
        ):
            raise Http404
        return self.get_response(request)
