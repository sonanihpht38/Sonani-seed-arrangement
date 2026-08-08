# Tests for the core services: document sequences + tenancy helpers.

from django.test import TestCase

from modules.core.models import DocumentSequence
from modules.core.sequences import SequenceService
from modules.core.tenancy import get_current_tenant, tenant_context
from modules.core.testing import make_company


class SequenceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t1 = make_company("S1", "Seq One")
        cls.t2 = make_company("S2", "Seq Two")

    def test_sequential_unique_numbers(self):
        numbers = [SequenceService.next(self.t1.id, "invoice", prefix="INV")
                   for _ in range(25)]
        self.assertEqual(len(set(numbers)), 25)
        self.assertEqual(numbers[0], "INV-00001")
        self.assertEqual(numbers[24], "INV-00025")

    def test_sequences_are_per_tenant(self):
        a = SequenceService.next(self.t1.id, "po", prefix="PO")
        b = SequenceService.next(self.t2.id, "po", prefix="PO")
        self.assertEqual(a, "PO-00001")
        self.assertEqual(b, "PO-00001")  # each tenant counts independently

    def test_yearly_period_resets(self):
        from datetime import datetime, timezone as tz
        y25 = datetime(2025, 5, 1, tzinfo=tz.utc)
        y26 = datetime(2026, 5, 1, tzinfo=tz.utc)
        a = SequenceService.next(self.t1.id, "grn", prefix="GRN",
                                 period=DocumentSequence.Period.YEAR, when=y25)
        b = SequenceService.next(self.t1.id, "grn", prefix="GRN",
                                 period=DocumentSequence.Period.YEAR, when=y26)
        self.assertEqual(a, "GRN-2025-00001")
        self.assertEqual(b, "GRN-2026-00001")  # new year restarts at 1

    def test_rollback_releases_number(self):
        from django.db import transaction

        SequenceService.next(self.t1.id, "so")
        try:
            with transaction.atomic():
                SequenceService.next(self.t1.id, "so")
                raise RuntimeError("abort")
        except RuntimeError:
            pass
        # The aborted allocation rolled back with its transaction.
        self.assertEqual(SequenceService.next(self.t1.id, "so"), "00002")


class TenantContextTests(TestCase):
    def test_context_manager_sets_and_restores(self):
        self.assertIsNone(get_current_tenant())
        with tenant_context(7):
            self.assertEqual(get_current_tenant(), 7)
            with tenant_context(9):
                self.assertEqual(get_current_tenant(), 9)
            self.assertEqual(get_current_tenant(), 7)
        self.assertIsNone(get_current_tenant())
