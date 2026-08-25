# HackSoft Django Styleguide — Reference

Full source: https://github.com/HackSoftware/Django-Styleguide  
Example project: https://github.com/HackSoftware/Django-Styleguide-Example

---

## Overview

Separate concerns so code stays maintainable and testable.

| Layer | Responsibility |
|-------|----------------|
| Services | Push — writes, mutations, side effects |
| Selectors | Pull — reads, filters, visibility |
| Models | Data shape, simple validation, simple derived values |
| APIs | Interface — parse, auth, delegate, serialize |

**Properties vs selectors:** use a selector when the logic spans relations or risks N+1 in serialization.

---

## Models

### Base model

```python
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    created_at = models.DateTimeField(db_index=True, default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

### Validation — clean

```python
class Course(BaseModel):
    name = models.CharField(unique=True, max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()

    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError("End date cannot be before start date")
```

Call `full_clean()` in the service before `save()`:

```python
def course_create(*, name: str, start_date: date, end_date: date) -> Course:
    obj = Course(name=name, start_date=start_date, end_date=end_date)
    obj.full_clean()
    obj.save()
    return obj
```

### Validation — constraints

```python
class Meta:
    constraints = [
        models.CheckConstraint(
            name="start_date_before_end_date", check=Q(start_date__lt=F("end_date"))
        )
    ]
```

Since Django 4.1, `full_clean()` also validates constraints.

### Properties & methods

Use for simple, same-instance, non-relational derivations. Use methods when arguments are required or when setting one field must atomically set related fields (e.g. `set_new_secret()`).

---

## Services

Function-based (default):

```python
def user_create(*, email: str, name: str) -> User:
    user = User(email=email)
    user.full_clean()
    user.save()
    profile_create(user=user, name=name)
    confirmation_email_send(user=user)
    return user
```

Class-based — namespace, reuse, multi-step flows:

```python
class FileStandardUploadService:
    def __init__(self, user: BaseUser, file_obj):
        self.user = user
        self.file_obj = file_obj

    @transaction.atomic
    def create(self, file_name: str = "", file_type: str = "") -> File: ...
```

Module layout when large:

```
services/
├── __init__.py
├── jwt.py
└── oauth.py
```

### Service testing

- Cover business logic exhaustively
- Hit the database
- Mock async tasks and external systems
- Mock selectors already tested elsewhere

---

## Selectors

```python
def user_list(*, fetched_by: User) -> Iterable[User]:
    user_ids = user_get_visible_for(user=fetched_by)
    return User.objects.filter(Q(id__in=user_ids))
```

With django-filter:

```python
class BaseUserFilter(django_filters.FilterSet):
    class Meta:
        model = BaseUser
        fields = ("id", "email", "is_admin")


def user_list(*, filters=None):
    filters = filters or {}
    qs = BaseUser.objects.all()
    return BaseUserFilter(filters, qs).qs
```

---

## APIs & serializers

### List API (plain)

```python
class UserListApi(APIView):
    class OutputSerializer(serializers.Serializer):
        id = serializers.CharField()
        email = serializers.CharField()

    def get(self, request):
        users = user_list()
        data = self.OutputSerializer(users, many=True).data
        return Response(data)
```

### List API (filters + pagination)

```python
class UserListApi(ApiErrorsMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 1

    class FilterSerializer(serializers.Serializer):
        id = serializers.IntegerField(required=False)
        is_admin = serializers.NullBooleanField(required=False)
        email = serializers.EmailField(required=False)

    class OutputSerializer(serializers.Serializer):
        id = serializers.CharField()
        email = serializers.CharField()
        is_admin = serializers.BooleanField()

    def get(self, request):
        filters_serializer = self.FilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        users = user_list(filters=filters_serializer.validated_data)
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=self.OutputSerializer,
            queryset=users,
            request=request,
            view=self,
        )
```

### Create / update / detail

```python
class CourseCreateApi(APIView):
    class InputSerializer(serializers.Serializer):
        name = serializers.CharField()
        start_date = serializers.DateField()
        end_date = serializers.DateField()

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course_create(**serializer.validated_data)
        return Response(status=status.HTTP_201_CREATED)
```

### get_object util

```python
def get_object(model_or_queryset, **kwargs):
    try:
        return get_object_or_404(model_or_queryset, **kwargs)
    except Http404:
        return None
```

### Advanced serialization

When output is complex, use a dedicated serialize function with refetch + prefetch + in-memory caches instead of bloating the selector.

---

## URLs

```python
course_patterns = [
    path("", CourseListApi.as_view(), name="list"),
    path("<int:course_id>/", CourseDetailApi.as_view(), name="detail"),
    path("create/", CourseCreateApi.as_view(), name="create"),
    path("<int:course_id>/update/", CourseUpdateApi.as_view(), name="update"),
]

urlpatterns = [
    path("courses/", include((course_patterns, "courses"))),
]
```

---

## Settings

```
config/
├── django/
│   ├── base.py
│   ├── local.py
│   ├── production.py
│   └── test.py
├── settings/
│   ├── celery.py
│   ├── cors.py
│   └── sentry.py
├── env.py
└── urls.py
```

`base.py` imports all integration settings. Env-specific files only override.

Optional integration pattern (`config/settings/sentry.py`):

```python
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    ...
```

---

## Errors & exception handling

### Map Django ValidationError

```python
def custom_exception_handler(exc, ctx):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))
    response = exception_handler(exc, ctx)
    return response
```

### Approach 1 — always `detail`

Normalize list/dict details into `{"detail": ...}`; map `Http404`, `PermissionDenied`, Django `ValidationError`.

### Approach 2 — HackSoft `message` + `extra`

```python
{
    "message": "Validation error.",
    "extra": {"fields": {"email": ["This field cannot be blank."]}},
}
```

Define `ApplicationError` in `core.exceptions` for domain errors. Handler maps validation to `extra.fields`, other DRF errors to `message`/`extra`.

See Styleguide-Example: `styleguide_example/api/exception_handlers.py`

---

## Testing

Structure mirrors code:

```
app/tests/
├── factories.py
├── models/test_course.py
├── selectors/test_user_list.py
└── services/test_item_buy.py
```

Naming:

- File: `test_a_very_neat_service.py`
- Class: `AVeryNeatServiceTests(TestCase)`

Resources: factory_boy, faker, HackSoft blog posts on fakes/factories.

---

## Celery

Task as thin interface:

```python
@shared_task
def email_send(email_id):
    email = Email.objects.get(id=email_id)
    from styleguide_example.emails.services import email_send

    email_send(email)
```

Trigger from service:

```python
from styleguide_example.emails.tasks import email_send as email_send_task


@transaction.atomic
def user_complete_onboarding(user: User) -> User:
    ...
    transaction.on_commit(lambda: email_send_task.delay(email.id))
    return user
```

Rules:

1. Tasks call services (import service inside task body)
2. Import task with `_task` suffix at module level
3. Use `transaction.on_commit` for task dispatch
4. Retries / `on_failure` callbacks live in task; callbacks call services

Periodic tasks: Celery Beat + django-celery-beat; centralize definitions in `setup_periodic_tasks` management command.

---

## Cookbook

### Handling updates with a service

```python
def user_update(*, user: User, data) -> User:
    non_side_effect_fields = ["first_name", "last_name"]
    user, has_updated = model_update(
        instance=user,
        fields=non_side_effect_fields,
        data=data,
    )
    # side-effect fields handled here
    return user
```

Implementations: `model_update`, `user_update` in Styleguide-Example — include tests if copied.

---

## DX — mypy

Use when it helps; optional per project. Example configs: django-stubs, djangorestframework-stubs in Styleguide-Example.

---

## Why not other places?

| Location | Issue |
|----------|-------|
| APIs/serializers/forms | Fragments logic; hard to trace; abstractions hide behavior |
| Managers/querysets | Domain spans models; 3rd-party calls don't belong here |
| Signals | Implicit connections; hard to trace; OK for loose coupling / cache invalidation only |
| Model `save` | Side effects hidden from callers |

---

## Inspiration & alternatives

- Separation of concerns, Boundaries (Gary Bernhardt), Rails service objects
- [Django-Styleguide-Example](https://github.com/HackSoftware/Django-Styleguide-Example)
- cookiecutter-django for project bootstrap
- RFC 7807 for structured API errors
