"""Singapore Mahjong wall: 148 tiles, live draws + replacement from wall end."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .tiles import Tile, tile_set_148


@dataclass
class Wall:
    """
    Live wall for draws; replacements (kong / flower / animal) come from the end.
    Game ends when fewer than END_LIVE tiles remain for normal play (SG: 15 left).
    """

    tiles: list[Tile] = field(default_factory=list)
    # index from start = live draws; from end = replacements
    live_i: int = 0
    replace_i: int = 0  # how many taken from the end

    END_LIVE = 15  # when remaining_live hits this after a draw path, game winding down

    @classmethod
    def shuffled(cls, rng: random.Random | None = None) -> Wall:
        rng = rng or random.Random()
        tiles = tile_set_148()
        rng.shuffle(tiles)
        return cls(tiles=tiles)

    @property
    def remaining_live(self) -> int:
        return max(0, len(self.tiles) - self.live_i - self.replace_i)

    def draw(self) -> Tile | None:
        if self.remaining_live <= 0:
            return None
        t = self.tiles[self.live_i]
        self.live_i += 1
        return t

    def draw_replacement(self) -> Tile | None:
        """Kong / flower / animal replacement from opposite end of the wall."""
        if self.remaining_live <= 0:
            return None
        idx = len(self.tiles) - 1 - self.replace_i
        if idx < self.live_i:
            return None
        t = self.tiles[idx]
        self.replace_i += 1
        return t

    # Riichi API stubs (unused in SG)
    def dora_indicators(self) -> list[Tile]:
        return []

    def register_kan(self) -> None:
        pass
