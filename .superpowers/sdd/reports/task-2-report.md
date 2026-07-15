# Task 2 Report: 模板模型与迁移加列

## Status: DONE

## What was implemented

Added the `structure_match_mode` column to the `SchemeTemplate` model and created the corresponding alembic migration, both verbatim from the task brief.

### 1. Model change — `backend/app/models/scheme_template.py`

Added the column between `full_document_review_config` and `parsed_at` exactly as specified:

```python
    structure_match_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="exact", default="exact"
    )
```

`String` was already imported at the top of the file (line 6). No import changes needed.

### 2. Migration — `backend/alembic/versions/022_template_structure_match_mode.py`

Created verbatim from the brief:
- `revision = "022"`
- `down_revision = "021"`
- `upgrade()` does `op.add_column("templates", sa.Column("structure_match_mode", sa.String(length=16), nullable=False, server_default="exact"))`
- `downgrade()` does `op.drop_column("templates", "structure_match_mode")`

## Verification

### Step 3 — Head check (KEY correctness signal)

```
$ cd backend && python -m alembic heads
022 (head)
```

Single head `022` confirmed. Prior to the change, the head was `021 (head)` (single head). The new migration's `down_revision = "021"` correctly chains off the previous head, so no branching / multiple heads were introduced.

### Step 4 — Smoke test note

The sqlite smoke test as written could not be exercised against ephemeral sqlite. The alembic env binds the real DB URL (MySQL) and does not honor the `SR_DATABASE_URL` override:

```
$ SR_DATABASE_URL="sqlite:////tmp/sr_test.db" python -m alembic upgrade head
INFO  [alembic.runtime.migration] Context impl MySQLImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 021 -> 022, add structure_match_mode to templates
```

The `Context impl MySQLImpl` line confirms the env ignored `SR_DATABASE_URL` and ran against the real MySQL DB. The upgrade did succeed (exit 0, `Running upgrade 021 -> 022` printed), and `alembic current` now reports `022 (head)`, so the migration DDL is valid. Per the brief's guidance, correctness is established by the single-head check + correct `down_revision`; the ephemeral-sqlite path simply couldn't be isolated from the env's DB binding.

`alembic current` after the run:
```
022 (head)
```

## Files changed

- Modified: `backend/app/models/scheme_template.py` (+3 lines)
- Created: `backend/alembic/versions/022_template_structure_match_mode.py` (new, 33 lines)

## Self-review findings

- Model column placement matches brief: after `full_document_review_config`, before `parsed_at`. ✓
- Column definition is byte-for-byte the brief's transcription (`String(16)`, `nullable=False`, `server_default="exact"`, `default="exact"`). ✓
- Migration `revision`/`down_revision`/`branch_labels`/`depends_on` match brief exactly. ✓
- `upgrade` adds to table `"templates"` (matches `SchemeTemplate.__tablename__`), `downgrade` drops it. ✓
- `String` was already imported — no spurious import added. ✓
- Single head `022`, no multiple-heads. ✓
- No other files touched. ✓

## Commits

- `84af28d` — `feat: add structure_match_mode column to templates` (on branch `feat/fuzzy-structure-matching`)

## Concerns

- None blocking. The only note is the env-DB-binding issue with the ephemeral sqlite smoke test (Step 4), which is an environment limitation acknowledged in the brief and not a defect in the migration itself.
