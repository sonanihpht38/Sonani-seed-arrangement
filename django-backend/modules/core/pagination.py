# ===================== SHARED / CROSS-CUTTING: pagination =====================
# The one list envelope every module returns: {results,total,page,page_size,
# total_pages}. Mirrored by the frontend's Paginated<T> type.

import math


def page_params(request, default_size=20, max_size=100):
    """Parse ?page= / ?page_size= safely; clamp size to [1, max_size]."""
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get("page_size", default_size))
    except (TypeError, ValueError):
        page_size = default_size
    page_size = max(1, min(page_size, max_size))
    return page, page_size


def paginate_envelope(items, total, page, page_size):
    return {
        "results": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


