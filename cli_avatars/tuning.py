"""Runtime tunables and the fixed overlay constants.

Config Apply writes fields on ``TUNING``. Movers read ``TUNING.gravity``
(and the other fields) when they run. A name imported from this module
would be a copy of the default and would ignore Apply.
"""

from dataclasses import dataclass

from bundle_paths import asset_path

AVATAR_W = 32
AVATAR_H = 32
FLOOR_MARGIN = 2
PERCH_MIN_LEN = 40    # px: shorter visible pieces of a window top are dropped
PERCH_MIN_Y = 40      # px: perches higher than this would put the avatar's head off screen
CHROMA_KEY = "#010101"

# px; a larger separation must not overflow the spring impulse.
# Not runtime-tunable.
SPRING_SPAN = 1.0e6

THROW_SCALE = 0.4   # fraction of mouse delta → throw velocity on drag release
FLOOR_LINE_COLOR = "#44aaff"

WALL_MARGIN = 6           # px proximity to latch onto a wall
WALL_CLIMB_SPEED = 1.4    # px/frame upward climb velocity
WALL_CLIMB_CHANCE = 0.4   # probability of climbing vs passing through on contact

BODY_COLORS = [
    "#4488ff", "#ff6644", "#44cc88", "#dd44cc",
    "#ffaa22", "#22ccff", "#ff4488", "#88ff44",
]

SPRITES_DIR = asset_path("Sprites")

# Skin cycling order for real sessions (index 0 = first real session)
REAL_SESSION_SKINS = ["caine", "meowatar", "amongo", "michimaru",
                      "ember_mage", "forest_scout", "frost_wanderer"]

# Default spring rest. The leash radius is this times 3 at startup.
# Apply can change spring_rest later; it does not recompute the leash.
_DEFAULT_SPRING_REST = 80


@dataclass
class Tuning:
    overlay_fps: int = 20
    window_scan_rate: float = 0.25   # s between window scans
    session_scan_rate: float = 2.0
    gravity: float = 0.55
    walk_speed: float = 1.8
    jump_vel: float = -10.0
    spring_rest: float = _DEFAULT_SPRING_REST   # px rest length of elastic line
    spring_k: float = 0.04                      # spring stiffness
    spring_damp: float = 0.94                   # velocity damping for spring avatars
    # px. A fly child bobs around a point this far above the parent's head.
    fly_bob: float = 3.0
    # px/frame. The hang stays under this, so a fast move reels the child in.
    spring_max_speed: float = 12.0
    # px. A child stays inside this circle around the parent's center.
    # config.json subagent.leash_px overrides it when that value is positive.
    subagent_leash_max: float = _DEFAULT_SPRING_REST * 3
    floor_line_alpha: float = 0.0    # 0.0=off, 1.0=solid
    overlay_alpha: float = 1.0       # window alpha: 0.1–1.0
    test_subagents: int = 0          # set > 0 to spawn fake subagents on the demo avatar
    avatar_scale: float = 2.5        # global sprite scale multiplier


TUNING = Tuning()
