from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpRequest

DEFAULT_PAGE_SIZE = 10


def paginate_queryset(
    request: HttpRequest, queryset, *, per_page: int = DEFAULT_PAGE_SIZE
):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page", 1)
    try:
        return paginator.page(page_number)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def list_pagination_context(
    request: HttpRequest,
    queryset,
    *,
    search: str,
    base_url: str,
    hx_target: str,
) -> dict:
    page_obj = paginate_queryset(request, queryset)
    return {
        "page_obj": page_obj,
        "search": search,
        "base_url": base_url,
        "pagination_target": hx_target,
        "pagination_mode": "htmx",
    }
