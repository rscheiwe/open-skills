"""
Unit tests for skill bundle packing/parsing.
"""

import pytest
from pathlib import Path

from open_skills.core.packing import parse_skill_bundle, validate_skill_bundle
from open_skills.core.exceptions import SkillValidationError


def test_parse_valid_skill_bundle(sample_skill_bundle):
    """Test parsing a valid skill bundle."""
    bundle = parse_skill_bundle(sample_skill_bundle)

    assert bundle.metadata["name"] == "test_skill"
    assert bundle.metadata["version"] == "1.0.0"
    assert bundle.metadata["entrypoint"] == "scripts/main.py"


def test_validate_skill_bundle(sample_skill_bundle):
    """Test validating a skill bundle."""
    assert validate_skill_bundle(sample_skill_bundle) is True


def test_missing_skill_md(tmp_path):
    """Test error when SKILL.md is missing."""
    with pytest.raises(SkillValidationError, match="Missing SKILL.md"):
        parse_skill_bundle(tmp_path)


def test_invalid_yaml(tmp_path):
    """Test error with invalid YAML frontmatter."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("""---
invalid: yaml: content
---
""")

    with pytest.raises(SkillValidationError, match="Invalid YAML"):
        parse_skill_bundle(tmp_path)


def test_missing_required_fields(tmp_path):
    """Test error when required fields are missing."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("""---
name: test
---
""")

    with pytest.raises(SkillValidationError, match="Missing required fields"):
        parse_skill_bundle(tmp_path)
