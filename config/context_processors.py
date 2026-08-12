from config.navigation import active_section, breadcrumbs_for, page_action_for


def navigation(request):
    return {
        "nav_section": active_section(request),
        "breadcrumbs": breadcrumbs_for(request),
        "page_action": page_action_for(request),
    }
