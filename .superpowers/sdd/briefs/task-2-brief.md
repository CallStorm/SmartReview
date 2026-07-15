### Task 2: 模板模型与迁移加列

**Files:**
- Modify: `backend/app/models/scheme_template.py`
- Create: `backend/alembic/versions/022_template_structure_match_mode.py`

**Interfaces:**
- Produces: `SchemeTemplate.structure_match_mode: Mapped[str]`（默认 `"exact"`，取值 `"exact" | "fuzzy"`）。

- [ ] **Step 1: Add the column to the model**

修改 `backend/app/models/scheme_template.py`，在 `full_document_review_config` 字段后、`parsed_at` 之前新增：

```python
    structure_match_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="exact", default="exact"
    )
```

（`String` 已在文件顶部 import。）

- [ ] **Step 2: Create the alembic migration**

```python
# backend/alembic/versions/022_template_structure_match_mode.py
"""add structure_match_mode to templates

Revision ID: 022
Revises: 021
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column(
            "structure_match_mode",
            sa.String(length=16),
            nullable=False,
            server_default="exact",
        ),
    )


def downgrade() -> None:
    op.drop_column("templates", "structure_match_mode")
```

- [ ] **Step 3: Verify migration is wired (head check)**

Run: `cd backend && python -m alembic heads`
Expected: a single head `022` (or `022 (...)`). If two heads appear, the `down_revision` is wrong — fix it.

- [ ] **Step 4: Run a fresh sqlite migration smoke test**

Run:
```bash
cd backend && rm -f /tmp/sr_test.db && SR_DATABASE_URL="sqlite:////tmp/sr_test.db" python -m alembic upgrade head
```
Expected: `Running upgrade 021 -> 022` printed, exit 0. (Uses an ephemeral sqlite file; the env may already bind `SR_DATABASE_URL` — if not, this still exercises migration DDL on a throwaway DB. If `SR_DATABASE_URL` is not honored, fall back to running `python -c "from alembic.config import Config; from alembic import command; command.upgrade(Config('alembic.ini'), 'head')"` against a throwaway URL set via `SQLALCHEMY_DATABASE_URL` env if the alembic env reads it; otherwise skip and rely on Step 3 + Task 11 integration.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/scheme_template.py backend/alembic/versions/022_template_structure_match_mode.py
git commit -m "feat: add structure_match_mode column to templates"
```

---

