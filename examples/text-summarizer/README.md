# Text Summarizer Example Skill

An example skill that demonstrates more complex text processing capabilities.

## Features

- Text statistics (word count, sentence count, averages)
- Key point extraction using a simple scoring algorithm
- Multiple output artifacts (Markdown summary, JSON stats)

## Testing Locally

```bash
cd examples/text-summarizer
open-skills validate .
open-skills run-local . tests/sample_input.json
```

## Expected Behavior

The skill will:
1. Analyze the input text
2. Extract the most important sentences based on position and length
3. Format them as bullet points
4. Generate statistics about the text
5. Create two artifact files:
   - `summary.md`: Formatted summary with key points and stats
   - `stats.json`: Detailed statistics in JSON format

## Customization

You can customize the behavior by:
- Changing `max_points` to control how many key points are extracted
- Modifying the scoring algorithm in `scripts/main.py`
- Adding additional text analysis features

## Production Notes

This is a demonstration implementation. For production use:
- Consider using NLP libraries like spaCy, NLTK, or transformers
- Implement proper sentence boundary detection
- Add support for different languages
- Handle edge cases (very short text, no punctuation, etc.)
- Add caching for repeated analysis
