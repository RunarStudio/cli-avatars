"""Flight mode and the ends of the elastic line.

``child_flight_mode`` is the one physics helper that reads the sprite
registry. The mode is passed into the spring step so spring.py does not
import sprites.
"""

from cli_avatars.sprites.registry import subagent_sprite_mode


def child_flight_mode(avatar: object) -> str:
    """``fly`` when this child was spawned with a fly sheet. Otherwise ground.

    An explicit ``_sub_mode`` wins, including in tests that have no registry.
    Orchestrators are not given one, so they stay ground and keep gravity.
    """
    mode = getattr(avatar, "_sub_mode", None)
    if mode in ("fly", "ground"):
        return mode
    skin = getattr(getattr(avatar, "agent", None), "skin", "")
    return subagent_sprite_mode(str(skin or ""))


def elastic_endpoints(parent: object, child: object, mode: str) -> tuple[float, float, float, float]:
    """Spring line ends. Fly starts at the head and runs upward to the child."""
    x1 = child.x + child.aw / 2.0
    y1 = child.y + child.ah / 2.0
    x0 = parent.x + parent.aw / 2.0
    if mode == "fly":
        y0 = float(parent.y)
    else:
        y0 = parent.y + parent.ah / 2.0
    return x0, y0, x1, y1
