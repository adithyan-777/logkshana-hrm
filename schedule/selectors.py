from django.db.models import Q, QuerySet

from schedule.models import Schedule, Timetable, TimetableBreak


def timetable_list(*, search: str = "") -> QuerySet[Timetable]:
    queryset = Timetable.objects.order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return queryset


def timetable_break_list(
    *, timetable: Timetable | None = None, search: str = ""
) -> QuerySet[TimetableBreak]:
    queryset = TimetableBreak.objects.select_related("timetable").order_by(
        "start_time", "name"
    )

    if timetable is not None:
        queryset = queryset.filter(timetable=timetable)

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(timetable__name__icontains=search)
        )

    return queryset


def schedule_list(*, search: str = "") -> QuerySet[Schedule]:
    queryset = Schedule.objects.select_related("timetable").order_by("name")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(timetable__name__icontains=search)
        )

    return queryset
