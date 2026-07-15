### Task 3: 报告 schema 加 mappings 字段

**Files:**
- Modify: `backend/app/schemas/review_report.py`
- Test: `backend/tests/test_review_report.py`（若不存在则创建）

**Interfaces:**
- Produces: `ReportStep.mappings: list[dict[str, Any]]`（默认空 list）。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_review_report.py
from __future__ import annotations

from app.schemas.review_report import ReportStep, ReviewReportV1


def test_report_step_has_default_empty_mappings():
    step = ReportStep(step_id="structure", passed=True)
    assert step.mappings == []


def test_report_step_accepts_mappings():
    step = ReportStep(
        step_id="structure",
        passed=True,
        mappings=[{"template_node_id": "n1", "match_method": "exact"}],
    )
    assert step.mappings[0]["match_method"] == "exact"


def test_report_dump_includes_mappings():
    step = ReportStep(step_id="structure", passed=True, mappings=[{"template_node_id": "n1"}])
    report = ReviewReportV1(steps=[step])
    data = report.model_dump(mode="json")
    assert data["steps"][0]["mappings"] == [{"template_node_id": "n1"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_review_report.py -v`
Expected: FAIL — `ReportStep` has no attribute `mappings`.

- [ ] **Step 3: Add the field**

修改 `backend/app/schemas/review_report.py` 的 `ReportStep`，在 `issues` 字段后新增：

```python
    mappings: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_review_report.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/review_report.py backend/tests/test_review_report.py
git commit -m "feat: add mappings field to ReportStep for structure review"
```

---

