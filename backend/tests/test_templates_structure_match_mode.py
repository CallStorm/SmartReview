"""Tests for template structure match mode API."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.api.templates import get_template, update_template_structure_match_mode
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.models.user import User, UserRole
from app.schemas.template import StructureMatchModeUpdate


def _make_user(role: UserRole = UserRole.admin) -> User:
    user = MagicMock(spec=User)
    user.role = role
    return user


class TestStructureMatchModeApi(TestCase):
    def test_patch_sets_fuzzy_mode(self) -> None:
        db = MagicMock()
        scheme = MagicMock(spec=SchemeType)
        db.get.return_value = scheme
        tmpl = MagicMock(spec=SchemeTemplate)
        tmpl.id = 1
        tmpl.scheme_type_id = 10
        tmpl.minio_bucket = "b"
        tmpl.object_key = "k"
        tmpl.original_filename = "t.docx"
        tmpl.parsed_structure = '{"nodes":[]}'
        tmpl.review_workflow = None
        tmpl.full_document_review_config = None
        tmpl.content_review_rules = None
        tmpl.image_review_rules = None
        tmpl.image_review_missing_text = None
        tmpl.structure_match_mode = "exact"
        tmpl.parsed_at = None
        tmpl.updated_at = None
        db.query.return_value.filter.return_value.first.return_value = tmpl

        result = update_template_structure_match_mode(
            10,
            StructureMatchModeUpdate(mode="fuzzy"),
            db=db,
            _=_make_user(),
        )
        self.assertEqual(result.structure_match_mode, "fuzzy")
        self.assertEqual(tmpl.structure_match_mode, "fuzzy")
        db.commit.assert_called_once()

    def test_patch_rejects_missing_template(self) -> None:
        db = MagicMock()
        db.get.return_value = MagicMock(spec=SchemeType)
        db.query.return_value.filter.return_value.first.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            update_template_structure_match_mode(
                10,
                StructureMatchModeUpdate(mode="fuzzy"),
                db=db,
                _=_make_user(),
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_template_public_exposes_mode(self) -> None:
        db = MagicMock()
        db.get.return_value = MagicMock(spec=SchemeType)
        tmpl = MagicMock(spec=SchemeTemplate)
        tmpl.id = 1
        tmpl.scheme_type_id = 10
        tmpl.minio_bucket = "b"
        tmpl.object_key = "k"
        tmpl.original_filename = "t.docx"
        tmpl.parsed_structure = '{"nodes":[]}'
        tmpl.review_workflow = None
        tmpl.full_document_review_config = None
        tmpl.content_review_rules = None
        tmpl.image_review_rules = None
        tmpl.image_review_missing_text = None
        tmpl.structure_match_mode = "exact"
        tmpl.parsed_at = None
        tmpl.updated_at = None
        db.query.return_value.filter.return_value.first.return_value = tmpl

        result = get_template(10, db=db, _=_make_user(UserRole.user))
        self.assertIn(result.structure_match_mode, ("exact", "fuzzy"))
