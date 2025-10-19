---
name: text_summarizer
version: 1.0.0
entrypoint: scripts/main.py
description: Summarizes long text into key bullet points
inputs:
  - type: text
    name: text
    description: Long text to summarize
  - type: integer
    name: max_points
    description: Maximum number of bullet points (default 5)
    optional: true
outputs:
  - type: text
    name: summary
    description: Summary in bullet points
  - type: object
    name: stats
    description: Statistics about the text
tags: [nlp, summarization, text, processing]
allow_network: false
timeout_seconds: 30
---

# Text Summarizer Skill

A more complex example that demonstrates text processing capabilities.

## What it does

This skill takes a long piece of text and:
1. Analyzes the text (word count, sentence count, etc.)
2. Extracts key points
3. Creates a bullet-point summary
4. Generates a statistics report

## Usage

### Input

```json
{
  "text": "Your long text here...",
  "max_points": 5
}
```

### Output

```json
{
  "summary": "• Point 1\n• Point 2\n• Point 3",
  "stats": {
    "word_count": 150,
    "sentence_count": 8,
    "avg_sentence_length": 18.75
  }
}
```

## Artifacts

- `summary.md`: Markdown file with the formatted summary
- `stats.json`: JSON file with detailed statistics

## Algorithm

This is a simple implementation that:
1. Splits text into sentences
2. Scores sentences by length and position
3. Selects top N sentences as summary points

*Note: This is a demonstration. For production use, consider using NLP libraries like spaCy or transformers.*
