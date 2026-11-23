"""Particle burst. ``canvas`` is any object with create_oval, coords, and delete."""

import math
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: str
    life: int
    max_life: int
    canvas_id: Optional[int] = None


class BurstEffect:
    N = 14
    LIFE = 50

    def __init__(self, cx, cy, color, extra_colors=None, n=None, life=None, speed_max=4.0):
        base_palette = [color, "#ffffff", "#ffdd44", "#88ffcc", "#ff88cc", "#aaddff"]
        if extra_colors:
            base_palette = list(extra_colors) + [color, "#ffffff"]
        n    = n    or self.N
        life = life or self.LIFE
        self.particles = []
        for i in range(n):
            ang   = (i / n) * 2 * math.pi + random.uniform(-0.3, 0.3)
            speed = random.uniform(1.5, speed_max)
            self.particles.append(Particle(
                x=cx, y=cy,
                vx=math.cos(ang)*speed, vy=math.sin(ang)*speed - 2.5,
                color=random.choice(base_palette),
                life=life, max_life=life,
            ))

    def tick(self, canvas: object) -> bool:
        alive = False
        for p in self.particles:
            if p.life <= 0:
                if p.canvas_id:
                    canvas.delete(p.canvas_id)
                    p.canvas_id = None
                continue
            alive = True
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.12
            p.life -= 1
            r  = max(1, int(5*p.life/p.max_life))
            x0,y0 = int(p.x)-r, int(p.y)-r
            x1,y1 = int(p.x)+r, int(p.y)+r
            if p.canvas_id:
                canvas.coords(p.canvas_id, x0,y0,x1,y1)
            else:
                p.canvas_id = canvas.create_oval(x0,y0,x1,y1, fill=p.color, outline="", tags="burst")
        return alive

    def cleanup(self, canvas: object) -> None:
        for p in self.particles:
            if p.canvas_id:
                canvas.delete(p.canvas_id)
