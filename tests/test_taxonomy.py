"""Taxonomy-as-data tests (offline)."""

from src.taxonomy import (
    TAXONOMY,
    get_category,
    is_valid_label,
    list_ids,
    load_taxonomy_from_json,
    render_full_prompt,
    render_prompt_section,
    severity_of,
)


def test_taxonomy_has_expected_labels():
    ids = list_ids()
    assert len(ids) >= 8
    for expected in ("billing", "bug_report", "security", "feature_request"):
        assert expected in ids


def test_get_category_returns_metadata():
    cat = get_category("security")
    assert cat is not None
    assert cat.severity == "critical"
    assert cat.sla_hours == 2
    assert get_category("nope") is None


def test_is_valid_label():
    assert is_valid_label("billing")
    assert not is_valid_label("refunds_and_stuff")
    assert not is_valid_label("")


def test_prompt_rendering_covers_all_labels():
    prompt = render_prompt_section()
    for cid in list_ids():
        assert cid in prompt


def test_full_prompt_includes_ticket():
    prompt = render_full_prompt("my invoice is wrong")
    assert "my invoice is wrong" in prompt
    assert "billing" in prompt


def test_load_taxonomy_from_json(tmp_path):
    import json

    data = [{
        "id": "custom", "name": "Custom", "description": "Custom cat",
        "keywords": ["custom"], "severity": "low", "sla_hours": 99,
        "examples": ["custom example"],
    }]
    p = tmp_path / "tax.json"
    p.write_text(json.dumps(data))
    cats = load_taxonomy_from_json(p)
    assert len(cats) == 1 and cats[0].id == "custom"


def test_severity_of_unknown_defaults_medium():
    assert severity_of("nonexistent") == "medium"
