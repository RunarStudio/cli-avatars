"""Task registry (docs/task-backend-and-memory-map.md section 2): the one writer of board cards.

``Registry`` is the full API for Daniel, the UI and the emit CLI. ``AgentApi`` is the narrow
API for AIs. ``policy`` holds the rules; it does no I/O.
"""
