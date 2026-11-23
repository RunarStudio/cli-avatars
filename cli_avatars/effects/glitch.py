"""Drag and right-click glitch. ``canvas`` needs create_rectangle and delete."""

import random


class GlitchFlash:
    LIFE = 10
    GRID = 12
    SHARED       = ["#aaaaaa", "#00ffee", "#ff6666"]
    PINK_PALETTE = ["#ff44aa", "#ff00ff", "#ff88cc", "#dd0066", "#ffaadd", "#cc00ff"] + SHARED
    DARK_PALETTE = ["#111111", "#000000", "#1a0a1a", "#0d000d", "#220011", "#0a0a0a"] + SHARED

    def __init__(self, canvas, ax, ay, aw, ah, pink: bool):
        self.canvas  = canvas
        self.life    = self.LIFE
        self.palette = self.PINK_PALETTE if pink else self.DARK_PALETTE
        self._items: list[int] = []
        # 20% inset so the matrix sits inside the avatar bounds
        inset_x = aw * 0.10;  inset_y = ah * 0.10
        self.mx  = ax + inset_x;  self.my = ay + inset_y
        self.mw  = aw * 0.80;     self.mh = ah * 0.80
        self._cw = self.mw / self.GRID
        self._ch = self.mh / self.GRID
        self._draw_cells()

    def _draw_cells(self):
        for _ in range(random.randint(6, 11)):
            col  = random.randint(0, self.GRID - 1)
            row  = random.randint(0, self.GRID - 1)
            span = random.randint(1, min(3, self.GRID - col))
            x0   = self.mx + col  * self._cw
            y0   = self.my + row  * self._ch
            item = self.canvas.create_rectangle(
                x0, y0, x0 + span * self._cw, y0 + self._ch,
                fill=random.choice(self.palette), outline="", width=0)
            self._items.append(item)

    def tick(self) -> bool:
        for item in self._items:
            self.canvas.delete(item)
        self._items.clear()
        self.life -= 1
        if self.life <= 0:
            return False
        self._draw_cells()
        return True
