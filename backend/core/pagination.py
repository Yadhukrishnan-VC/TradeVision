"""
TradeVision AI — DRF pagination classes.

All paginated API responses follow the envelope::

    {
        "count":    <total items>,
        "next":     <url | null>,
        "previous": <url | null>,
        "results":  [...]
    }
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    """
    Default pagination for all API endpoints.

    Page size defaults to 20. Clients may request up to 100 items per page
    via the ``page_size`` query parameter.
    """

    page_size: int = 20
    page_size_query_param: str = "page_size"
    max_page_size: int = 100

    def get_paginated_response(self, data: list) -> Response:
        """Wrap paginated data in the standard envelope."""
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: dict) -> dict:
        """OpenAPI schema for the paginated response envelope."""
        return {
            "type": "object",
            "required": ["count", "results"],
            "properties": {
                "count": {"type": "integer", "example": 42},
                "next": {"type": "string", "nullable": True, "format": "uri"},
                "previous": {"type": "string", "nullable": True, "format": "uri"},
                "results": schema,
            },
        }


class LargeResultsPagination(PageNumberPagination):
    """
    Pagination for admin and bulk-export endpoints.

    Page size defaults to 100 with a maximum of 500. Use sparingly — prefer
    StandardResultsPagination for user-facing endpoints.
    """

    page_size: int = 100
    page_size_query_param: str = "page_size"
    max_page_size: int = 500

    def get_paginated_response(self, data: list) -> Response:
        """Wrap paginated data in the standard envelope."""
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
