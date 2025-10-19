"""
Text Summarizer Skill
Extracts key points from long text.
"""

import json
import re
from typing import Dict, Any, List
from pathlib import Path


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    # Simple sentence splitter (not perfect, but works for demo)
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if s.strip()]


def calculate_stats(text: str) -> Dict[str, Any]:
    """Calculate text statistics."""
    words = text.split()
    sentences = split_into_sentences(text)

    return {
        "word_count": len(words),
        "character_count": len(text),
        "sentence_count": len(sentences),
        "avg_sentence_length": len(words) / len(sentences) if sentences else 0,
        "avg_word_length": sum(len(w) for w in words) / len(words) if words else 0,
    }


def extract_key_points(text: str, max_points: int = 5) -> List[str]:
    """
    Extract key points from text.

    Simple algorithm:
    - Split into sentences
    - Score by position (first sentences get higher score)
    - Score by length (medium-length sentences preferred)
    - Return top N
    """
    sentences = split_into_sentences(text)

    if len(sentences) <= max_points:
        return sentences

    # Score sentences
    scored = []
    for i, sentence in enumerate(sentences):
        word_count = len(sentence.split())

        # Position score (earlier sentences = higher score)
        position_score = 1.0 - (i / len(sentences))

        # Length score (prefer medium length: 10-25 words)
        if 10 <= word_count <= 25:
            length_score = 1.0
        elif word_count < 10:
            length_score = word_count / 10
        else:
            length_score = max(0.5, 1.0 - (word_count - 25) / 50)

        # Combined score
        score = (position_score * 0.6) + (length_score * 0.4)
        scored.append((score, sentence))

    # Sort by score and take top N
    scored.sort(reverse=True, key=lambda x: x[0])
    return [s[1] for s in scored[:max_points]]


async def run(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main skill execution function.

    Args:
        input_payload: Input data with 'text' and optional 'max_points'

    Returns:
        Dictionary with 'outputs' and 'artifacts' keys
    """
    # Extract inputs
    text = input_payload.get("text", "")
    max_points = input_payload.get("max_points", 5)

    if not text:
        return {
            "outputs": {
                "summary": "No text provided",
                "stats": {},
            },
            "artifacts": [],
        }

    # Calculate statistics
    stats = calculate_stats(text)

    # Extract key points
    key_points = extract_key_points(text, max_points)

    # Format summary as bullet points
    summary_text = "\n".join(f"• {point}" for point in key_points)

    # Create markdown artifact
    summary_md = Path("summary.md")
    summary_md.write_text(f"""# Text Summary

## Key Points

{summary_text}

## Statistics

- **Words:** {stats['word_count']}
- **Sentences:** {stats['sentence_count']}
- **Average Sentence Length:** {stats['avg_sentence_length']:.1f} words
- **Average Word Length:** {stats['avg_word_length']:.1f} characters
""")

    # Create stats JSON artifact
    stats_json = Path("stats.json")
    stats_json.write_text(json.dumps(stats, indent=2))

    # Return outputs
    return {
        "outputs": {
            "summary": summary_text,
            "stats": stats,
            "point_count": len(key_points),
        },
        "artifacts": [
            str(summary_md),
            str(stats_json),
        ],
    }
