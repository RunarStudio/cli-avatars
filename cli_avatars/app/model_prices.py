"""USAGE.1: list prices per million tokens, used only when a CLI reports tokens but no cost. Estimated; edit freely.

A model name takes the row of its longest matching prefix; a model with no row gets no cost ("—").
"""

AS_OF = "2026-11-27"
LABEL = "estimated"
USD_PER_MILLION = {  # prefix: (input, output)
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "grok-4-fast": (0.20, 0.50),
    "grok-4": (3.0, 15.0),
    "grok-code-fast": (0.20, 1.50),
    "grok-3-mini": (0.30, 0.50),
}
