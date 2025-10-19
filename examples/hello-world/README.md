# Hello World Example Skill

A minimal example skill that demonstrates the basic structure of an open-skills skill bundle.

## Testing Locally

```bash
cd examples/hello-world
open-skills validate .
open-skills run-local . tests/sample_input.json
```

## Expected Output

```json
{
  "greeting": "Hello, Alice! Welcome to open-skills.",
  "character_count": 42
}
```

Artifacts:
- `greeting.txt`: Text file containing the greeting
