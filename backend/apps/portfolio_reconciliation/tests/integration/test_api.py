"""PORTFOLIO-RECONCILE-1 — integration tests for the drift-log API.

Verifies auth (OWNER/STAFF only), filtering, validation, and the summary
endpoint against real PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.portfolio_reconciliation.infrastructure.models import DriftRecord
from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
    EntityType,
)

pytestmark = pytest.mark.django_db

PATH = "/api/v1/portfolio-reconciliation/"

NOW = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)


def _seed_drift(
    *,
    account_id: uuid.UUID,
    entity_type: str = EntityType.POSITION.value,
    entity_key: str = "key",
    classification: str = DriftClassification.MISSING_IN_READ_MODEL.value,
    auto_repaired: bool = False,
    detected_at: datetime = NOW,
) -> DriftRecord:
    return DriftRecord.objects.create(
        account_id=account_id,
        entity_type=entity_type,
        entity_key=entity_key,
        classification=classification,
        expected_snapshot={"quantity": "100"},
        actual_snapshot={},
        auto_repaired=auto_repaired,
        detected_at=detected_at,
        repaired_at=NOW if auto_repaired else None,
    )


class TestDriftRecordListAPI:
    def test_requires_authentication(self, api_client: APIClient) -> None:
        response = api_client.get(PATH + "drift/")

        # With the global authenticators registered, an unauthenticated request
        # to a protected endpoint raises NotAuthenticated -> 401 (not 403).
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_viewer_role_is_forbidden(self, api_client: APIClient, viewer_user: object) -> None:
        api_client.force_authenticate(user=viewer_user)

        response = api_client.get(PATH + "drift/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_role_can_list_drift(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id)
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["entity_key"] == "key"
        assert response.data["results"][0]["classification"] == (
            DriftClassification.MISSING_IN_READ_MODEL.value
        )
        assert response.data["results"][0]["auto_repaired"] is False

    def test_owner_role_can_list_drift(
        self, api_client: APIClient, owner_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id)
        api_client.force_authenticate(user=owner_user)

        response = api_client.get(PATH + "drift/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1

    def test_filter_by_account_id(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        other_account = uuid.uuid4()
        _seed_drift(account_id=account.id, entity_key="wanted")
        _seed_drift(account_id=other_account, entity_key="other")
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/", {"account_id": str(account.id)})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["entity_key"] == "wanted"

    def test_filter_by_classification(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id, entity_key="stale",
                    classification=DriftClassification.STALE_IN_READ_MODEL.value)
        _seed_drift(account_id=account.id, entity_key="orphan",
                    classification=DriftClassification.ORPHANED_IN_READ_MODEL.value)
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(
            PATH + "drift/",
            {"classification": DriftClassification.ORPHANED_IN_READ_MODEL.value},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["entity_key"] == "orphan"

    def test_filter_by_auto_repaired(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id, entity_key="repaired", auto_repaired=True)
        _seed_drift(account_id=account.id, entity_key="unrepaired")
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/", {"auto_repaired": "true"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["entity_key"] == "repaired"

    def test_invalid_account_id_is_rejected(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id)
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/", {"account_id": "not-a-uuid"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_classification_is_rejected(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id)
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/", {"classification": "BOGUS"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_ordering_is_newest_first(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id, entity_key="old",
                    detected_at=NOW)
        _seed_drift(account_id=account.id, entity_key="new",
                    detected_at=datetime(2026, 8, 12, 9, 30, 0, tzinfo=timezone.utc))
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2
        assert response.data["results"][0]["entity_key"] == "new"

    def test_pagination_envelope(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        for i in range(3):
            _seed_drift(account_id=account.id, entity_key=f"key-{i}")
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/", {"page_size": "2"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 3
        assert len(response.data["results"]) == 2
        assert response.data["next"] is not None


class TestDriftSummaryAPI:
    def test_summary_requires_authentication(self, api_client: APIClient) -> None:
        response = api_client.get(PATH + "drift/summary/")

        # With the global authenticators registered, an unauthenticated request
        # to a protected endpoint raises NotAuthenticated -> 401 (not 403).
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_summary_returns_breakdown(
        self, api_client: APIClient, staff_user: object, account
    ) -> None:
        _seed_drift(account_id=account.id,
                    classification=DriftClassification.MISSING_IN_READ_MODEL.value)
        _seed_drift(account_id=account.id,
                    classification=DriftClassification.STALE_IN_READ_MODEL.value)
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/summary/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_records"] == 2
        assert response.data["classification_breakdown"][
            DriftClassification.MISSING_IN_READ_MODEL.value
        ] == 1
        assert response.data["classification_breakdown"][
            DriftClassification.STALE_IN_READ_MODEL.value
        ] == 1
        assert response.data["last_run_at"] is not None

    def test_summary_empty_db(
        self, api_client: APIClient, staff_user: object
    ) -> None:
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(PATH + "drift/summary/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_records"] == 0
        assert response.data["classification_breakdown"] == {}
        assert response.data["last_run_at"] is None
