"""Auto-routing: pick a mode from the prompt, mirroring website/index.html.

Heuristic only. It looks at length, a few complexity phrases and question
count; it knows nothing about difficulty or model confidence. The rules and
thresholds match routeMode() on the site, and spec/routing_cases.json is
checked against both implementations so they cannot drift silently.
"""

import re

SPROUT_MAX_WORDS = 12
FOREST_MIN_WORDS = 35
COMPLEXITY_MARKERS = (
    "compare", "pros and cons", "versus", "in detail", "step by step",
    "trade-off", "trade-offs", "explain both",
)
_FENCE = re.compile(r"```.*?```", re.DOTALL)


def route_mode(prompt):
    """Return 'sprout', 'canopy' or 'full' (the site calls full 'forest')."""
    prose = _FENCE.sub(" ", prompt)
    lowered = prose.lower()
    words = len(prose.split())
    has_marker = any(m in lowered for m in COMPLEXITY_MARKERS)
    if has_marker or prose.count("?") >= 2 or words >= FOREST_MIN_WORDS:
        return "full"
    if words <= SPROUT_MAX_WORDS:
        return "sprout"
    return "canopy"
