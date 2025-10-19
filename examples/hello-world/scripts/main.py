"""
Hello World Skill
Simple example skill that greets a user.
"""

from typing import Dict, Any
from pathlib import Path


async def run(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main skill execution function.

    Args:
        input_payload: Input data with 'name' field

    Returns:
        Dictionary with 'outputs' and 'artifacts' keys
    """
    # Extract name from input
    name = input_payload.get("name", "World")

    # Create greeting
    greeting = f"Hello, {name}! Welcome to open-skills."

    # Write greeting to an output file (optional artifact)
    output_file = Path("greeting.txt")
    output_file.write_text(greeting)

    # Return outputs and artifacts
    return {
        "outputs": {
            "greeting": greeting,
            "character_count": len(greeting),
        },
        "artifacts": [str(output_file)],
    }
