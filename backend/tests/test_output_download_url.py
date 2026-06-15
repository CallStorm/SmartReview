"""Tests for review task output download URL (export scheme)."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.review_tasks import get_output_download_url
from app.models.scheme_review_task import ReviewTaskStatus
from app.models.user import User, UserRole


def _make_user(role: UserRole = UserRole.user, user_id: int = 1) -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.role = role
    return user


def _make_task(
    *,
    task_id: int = 1,
    user_id: int = 1,
    status: str = ReviewTaskStatus.failed,
    object_key: str = "reviews/1/source.docx",
    output_object_key: str | None = None,
) -> MagicMock:
    task = MagicMock()
    task.id = task_id
    task.user_id = user_id
    task.status = status
    task.object_key = object_key
    task.output_object_key = output_object_key
    return task


class TestOutputDownloadUrl(TestCase):
    def test_pending_task_returns_409(self) -> None:
        db = MagicMock()
        db.query.return_value.options.return_value.filter.return_value.first.return_value = _make_task(
            status=ReviewTaskStatus.pending
        )
        user = _make_user()

        with self.assertRaises(HTTPException) as ctx:
            get_output_download_url(1, db=db, user=user)
        self.assertEqual(ctx.exception.status_code, 409)

    @patch("app.api.review_tasks.minio_storage.presigned_get_url", return_value="https://minio/out.docx")
    def test_succeeded_uses_output_object_key(self, mock_presign: MagicMock) -> None:
        db = MagicMock()
        db.query.return_value.options.return_value.filter.return_value.first.return_value = _make_task(
            status=ReviewTaskStatus.succeeded,
            output_object_key="reviews/1/annotated.docx",
        )
        user = _make_user()

        resp = get_output_download_url(1, db=db, user=user)
        self.assertEqual(resp.url, "https://minio/out.docx")
        mock_presign.assert_called_once_with("reviews/1/annotated.docx", expires_seconds=3600)

    @patch("app.api.review_tasks.minio_storage.presigned_get_url", return_value="https://minio/src.docx")
    def test_failed_without_output_falls_back_to_object_key(self, mock_presign: MagicMock) -> None:
        db = MagicMock()
        db.query.return_value.options.return_value.filter.return_value.first.return_value = _make_task(
            status=ReviewTaskStatus.failed,
            object_key="reviews/1/source.docx",
            output_object_key=None,
        )
        user = _make_user()

        resp = get_output_download_url(1, db=db, user=user)
        self.assertEqual(resp.url, "https://minio/src.docx")
        mock_presign.assert_called_once_with("reviews/1/source.docx", expires_seconds=3600)
