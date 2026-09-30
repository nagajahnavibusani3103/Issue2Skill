"""
Tests for Phase 3: Benchmark Dataset Schema & Integrity
- Verifies that benchmark/dataset.json exists and is valid JSON
- Verifies exactly 35 curated reference issues
- Verifies exactly 7 distinct categories with 5 issues each
- Verifies all required fields exist and conform to schemas
"""

import os
import json
import pytest

DATASET_PATH = os.path.join(os.path.dirname(__file__), "..", "benchmark", "dataset.json")


def test_benchmark_dataset_integrity():
    assert os.path.exists(DATASET_PATH), f"Benchmark dataset not found at {DATASET_PATH}"

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    assert isinstance(dataset, list), "Benchmark dataset must be a list of issues"
    assert len(dataset) == 35, f"Expected exactly 35 benchmark issues, found {len(dataset)}"

    categories = set()
    category_counts = {}
    issue_ids = set()

    expected_categories = {
        "bug_fix_skill",
        "feature_addition_skill",
        "refactoring_skill",
        "performance_optimization_skill",
        "security_vulnerability_skill",
        "tool_automation_skill",
        "ambiguous_and_conflicting_issues"
    }

    required_fields = [
        "id", "category", "title", "body", "expected_classification",
        "expected_blocking_gate", "target_skill_name", "key_requirements"
    ]

    for item in dataset:
        # Check required fields
        for field in required_fields:
            assert field in item, f"Issue {item.get('id', '?')} is missing required field '{field}'"

        # Unique IDs
        assert item["id"] not in issue_ids, f"Duplicate issue ID found: {item['id']}"
        issue_ids.add(item["id"])

        cat = item["category"]
        categories.add(cat)
        category_counts[cat] = category_counts.get(cat, 0) + 1

        # Check classification validity
        assert item["expected_classification"] in [
            "SKILL_COMPATIBLE", "AMBIGUOUS", "CONFLICTING", "UNSUPPORTED"
        ]

        # Check title and body non-empty
        assert len(item["title"].strip()) > 0
        assert len(item["body"].strip()) > 0

    # Verify exactly 7 categories
    assert categories == expected_categories, f"Categories mismatch: {categories} vs {expected_categories}"

    # Verify 5 issues per category
    for cat, count in category_counts.items():
        assert count == 5, f"Category '{cat}' has {count} issues; expected exactly 5"
