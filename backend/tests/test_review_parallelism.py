"""Parallelism helpers and review settings bounds."""

from __future__ import annotations

import time
from unittest import TestCase

from pydantic import ValidationError

from app.schemas.review_settings import ReviewSettingsUpdate
from app.services.review_pipeline import _bounded_parallel_map
from app.services.review_settings import (
    MAX_PARALLELISM,
    MIN_PARALLELISM,
    _clamp_parallelism,
    DEFAULT_CONTENT_CONCURRENCY,
)


class TestClampParallelism(TestCase):
    def test_clamps_low_and_high(self) -> None:
        self.assertEqual(_clamp_parallelism(None, default=4), 4)
        self.assertEqual(_clamp_parallelism(0, default=4), MIN_PARALLELISM)
        self.assertEqual(_clamp_parallelism(-5, default=4), MIN_PARALLELISM)
        self.assertEqual(_clamp_parallelism(99, default=4), MAX_PARALLELISM)
        self.assertEqual(_clamp_parallelism(3, default=4), 3)


class TestBoundedParallelMap(TestCase):
    def test_results_sorted_by_work_index(self) -> None:
        def work(i: int) -> int:
            time.sleep(0.01 * (3 - i))
            return i * 10

        out = _bounded_parallel_map(concurrency=2, items=[(2, 2), (0, 0), (1, 1)], worker=work)
        out.sort(key=lambda x: x[0])
        self.assertEqual([x[1] for x in out], [0, 10, 20])

    def test_empty_items(self) -> None:
        self.assertEqual(_bounded_parallel_map(concurrency=4, items=[], worker=lambda x: x), [])


class TestReviewSettingsSchema(TestCase):
    def test_parallelism_fields_required(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewSettingsUpdate(
                review_timeout_seconds=120,
                prompt_debug_enabled=False,
            )  # type: ignore[call-arg]

    def test_parallelism_bounds(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewSettingsUpdate(
                review_timeout_seconds=120,
                prompt_debug_enabled=False,
                worker_parallel_tasks=0,
                compilation_basis_concurrency=DEFAULT_CONTENT_CONCURRENCY,
                context_consistency_concurrency=DEFAULT_CONTENT_CONCURRENCY,
                content_concurrency=DEFAULT_CONTENT_CONCURRENCY,
            )
