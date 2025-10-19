"""
Skill bundle parser and validator.
Handles SKILL.md parsing (YAML frontmatter + Markdown) and bundle validation.
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

from open_skills.core.exceptions import SkillValidationError
from open_skills.core.telemetry import get_logger

logger = get_logger(__name__)

# Regex pattern for YAML frontmatter
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Required fields in SKILL.md frontmatter
REQUIRED_FIELDS = ["name", "version", "entrypoint"]

# Optional fields with defaults
OPTIONAL_FIELDS = {
    "description": "",
    "inputs": [],
    "outputs": [],
    "tags": [],
    "allow_network": False,
    "timeout_seconds": None,
    "resources": [],
}


class SkillBundle:
    """Represents a parsed skill bundle."""

    def __init__(self, bundle_path: Path):
        """
        Initialize skill bundle from path.

        Args:
            bundle_path: Path to skill bundle directory

        Raises:
            SkillValidationError: If bundle is invalid
        """
        self.bundle_path = bundle_path.resolve()
        self.metadata: Dict[str, Any] = {}
        self.description_md: str = ""

        self._validate_structure()
        self._parse_skill_md()
        self._validate_metadata()
        self._validate_entrypoint()

    def _validate_structure(self) -> None:
        """Validate basic bundle directory structure."""
        if not self.bundle_path.is_dir():
            raise SkillValidationError(f"Bundle path is not a directory: {self.bundle_path}")

        skill_md = self.bundle_path / "SKILL.md"
        if not skill_md.exists():
            raise SkillValidationError(f"Missing SKILL.md in bundle: {self.bundle_path}")

    def _parse_skill_md(self) -> None:
        """Parse SKILL.md file (YAML frontmatter + Markdown description)."""
        skill_md_path = self.bundle_path / "SKILL.md"

        try:
            content = skill_md_path.read_text(encoding="utf-8")
        except Exception as e:
            raise SkillValidationError(f"Failed to read SKILL.md: {e}")

        # Extract YAML frontmatter
        match = FRONTMATTER_RE.match(content)
        if not match:
            raise SkillValidationError(
                "SKILL.md must start with YAML frontmatter (---\\n...\\n---)"
            )

        frontmatter_text = match.group(1)
        self.description_md = content[match.end() :].strip()

        # Parse YAML
        try:
            self.metadata = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError as e:
            raise SkillValidationError(f"Invalid YAML in SKILL.md frontmatter: {e}")

        if not isinstance(self.metadata, dict):
            raise SkillValidationError("SKILL.md frontmatter must be a YAML object/dict")

        # Apply defaults for optional fields
        for field, default in OPTIONAL_FIELDS.items():
            if field not in self.metadata:
                self.metadata[field] = default

    def _validate_metadata(self) -> None:
        """Validate metadata fields."""
        # Check required fields
        missing = [f for f in REQUIRED_FIELDS if f not in self.metadata]
        if missing:
            raise SkillValidationError(
                f"Missing required fields in SKILL.md: {', '.join(missing)}"
            )

        # Validate field types
        if not isinstance(self.metadata["name"], str) or not self.metadata["name"]:
            raise SkillValidationError("Field 'name' must be a non-empty string")

        if not isinstance(self.metadata["version"], str) or not self.metadata["version"]:
            raise SkillValidationError("Field 'version' must be a non-empty string")

        if not isinstance(self.metadata["entrypoint"], str) or not self.metadata["entrypoint"]:
            raise SkillValidationError("Field 'entrypoint' must be a non-empty string")

        # Validate version format (semantic versioning)
        version_pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9\-\.]+)?$"
        if not re.match(version_pattern, self.metadata["version"]):
            raise SkillValidationError(
                f"Invalid version format '{self.metadata['version']}'. "
                "Expected semantic versioning (e.g., 1.0.0)"
            )

        # Validate tags
        if not isinstance(self.metadata["tags"], list):
            raise SkillValidationError("Field 'tags' must be a list")

        # Validate inputs/outputs
        if not isinstance(self.metadata["inputs"], list):
            raise SkillValidationError("Field 'inputs' must be a list")

        if not isinstance(self.metadata["outputs"], list):
            raise SkillValidationError("Field 'outputs' must be a list")

    def _validate_entrypoint(self) -> None:
        """Validate that the entrypoint file exists."""
        entrypoint = self.metadata["entrypoint"]

        # Remove function name if present (scripts/main.py:run -> scripts/main.py)
        if ":" in entrypoint:
            file_path_str = entrypoint.split(":")[0]
        else:
            file_path_str = entrypoint

        entrypoint_path = self.bundle_path / file_path_str
        if not entrypoint_path.exists():
            raise SkillValidationError(
                f"Entrypoint file not found: {file_path_str} "
                f"(resolved to {entrypoint_path})"
            )

        if not entrypoint_path.is_file():
            raise SkillValidationError(
                f"Entrypoint is not a file: {file_path_str}"
            )

        # Check if it's a Python file
        if not entrypoint_path.suffix == ".py":
            logger.warning(
                "entrypoint_not_python",
                entrypoint=file_path_str,
                suffix=entrypoint_path.suffix,
            )

    def get_resources_paths(self) -> List[Path]:
        """
        Get list of resource file paths.

        Returns:
            List of Path objects for resources
        """
        resources_dir = self.bundle_path / "resources"
        if not resources_dir.exists():
            return []

        return [
            p for p in resources_dir.rglob("*")
            if p.is_file()
        ]

    def get_all_files(self) -> List[Path]:
        """
        Get all files in the bundle.

        Returns:
            List of Path objects for all files
        """
        return [
            p for p in self.bundle_path.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        ]

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert bundle to dictionary representation.

        Returns:
            Dictionary with metadata and description
        """
        return {
            "metadata": self.metadata,
            "description": self.description_md,
            "bundle_path": str(self.bundle_path),
        }

    def __repr__(self) -> str:
        return (
            f"<SkillBundle(name={self.metadata.get('name')}, "
            f"version={self.metadata.get('version')})>"
        )


def parse_skill_bundle(bundle_path: Path) -> SkillBundle:
    """
    Parse and validate a skill bundle.

    Args:
        bundle_path: Path to skill bundle directory

    Returns:
        Parsed SkillBundle instance

    Raises:
        SkillValidationError: If bundle is invalid
    """
    return SkillBundle(bundle_path)


def validate_skill_bundle(bundle_path: Path) -> bool:
    """
    Validate a skill bundle without raising exceptions.

    Args:
        bundle_path: Path to skill bundle directory

    Returns:
        True if valid, False otherwise
    """
    try:
        parse_skill_bundle(bundle_path)
        return True
    except SkillValidationError as e:
        logger.error("skill_validation_failed", bundle_path=str(bundle_path), error=str(e))
        return False


def create_skill_template(output_path: Path, name: str) -> None:
    """
    Create a skill bundle template.

    Args:
        output_path: Directory where the skill bundle will be created
        name: Name of the skill

    Raises:
        FileExistsError: If output path already exists
    """
    if output_path.exists():
        raise FileExistsError(f"Path already exists: {output_path}")

    # Create directory structure
    output_path.mkdir(parents=True)
    (output_path / "scripts").mkdir()
    (output_path / "resources").mkdir(exist_ok=True)
    (output_path / "tests").mkdir(exist_ok=True)

    # Create SKILL.md
    skill_md_content = f"""---
name: {name}
version: 1.0.0
entrypoint: scripts/main.py
description: A new skill that does something useful
inputs:
  - type: text
outputs:
  - type: text
tags: []
allow_network: false
---

# {name.replace('_', ' ').title()}

This skill does something useful.

## Usage

Describe how to use this skill here.

## Inputs

- **text**: Description of input

## Outputs

- **text**: Description of output
"""
    (output_path / "SKILL.md").write_text(skill_md_content, encoding="utf-8")

    # Create entrypoint script
    main_py_content = '''"""
Skill entrypoint.
"""

from typing import Dict, Any
from pathlib import Path


async def run(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main skill execution function.

    Args:
        input_payload: Input data dictionary

    Returns:
        Dictionary with 'outputs' and 'artifacts' keys
    """
    # Extract inputs
    text = input_payload.get("text", "")

    # Process (example: simple transformation)
    result = text.upper()

    # Write output artifact (optional)
    output_file = Path("output.txt")
    output_file.write_text(result)

    # Return outputs and artifacts
    return {
        "outputs": {
            "text": result,
            "length": len(result),
        },
        "artifacts": [str(output_file)],  # List of file paths
    }
'''
    (output_path / "scripts" / "main.py").write_text(main_py_content, encoding="utf-8")

    # Create test input
    test_input = """{"text": "hello world"}
"""
    (output_path / "tests" / "sample_input.json").write_text(test_input, encoding="utf-8")

    # Create README
    readme = f"""# {name}

This skill was created from the open-skills template.

## Testing Locally

```bash
open-skills run-local . tests/sample_input.json
```

## Publishing

```bash
open-skills publish .
```
"""
    (output_path / "README.md").write_text(readme, encoding="utf-8")

    logger.info("skill_template_created", path=str(output_path), name=name)
