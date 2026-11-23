"""Entry point. Code lives in cli_avatars/. Kept for python overlay.py,
--selftest, the PyInstaller spec and old imports."""

# DPI awareness runs at import, before tkinter and before any tk.Tk().
import cli_avatars.desktop.capabilities  # noqa: F401

from cli_avatars.app.main import main, run_selftest
from cli_avatars.app.shell import OverlayApp
from cli_avatars.model.agent import AgentInfo
from cli_avatars.physics.geometry import child_flight_mode, elastic_endpoints
from cli_avatars.physics.leash import leash_px_from_config
from cli_avatars.tuning import TUNING
from cli_avatars.world.avatar import Avatar

# Copies of the defaults. Config Apply writes TUNING. Movers read TUNING.
FLY_BOB = TUNING.fly_bob
GRAVITY = TUNING.gravity
SPRING_DAMP = TUNING.spring_damp
SPRING_K = TUNING.spring_k
SPRING_MAX_SPEED = TUNING.spring_max_speed
SPRING_REST = TUNING.spring_rest
SUBAGENT_LEASH_MAX = TUNING.subagent_leash_max
WALK_SPEED = TUNING.walk_speed

if __name__ == "__main__":
    raise SystemExit(main())
