"""Singapore Mahjong tiles: 148 = 136 playable + 8 flowers + 4 animals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Suit(IntEnum):
    MAN = 0  # Millions / Characters
    PIN = 1  # Circles
    SOU = 2  # Bamboo
    WIND = 3  # E=0 S=1 W=2 N=3
    DRAGON = 4  # Haku=0 Hatsu=1 Chun=2
    FLOWER = 5  # 0-3 Season (red 1-4), 4-7 Flower set (blue 1-4)
    ANIMAL = 6  # 0=cat 1=mouse 2=chicken 3=centipede


@dataclass(frozen=True, order=True)
class Tile:
    suit: Suit
    value: int
    aka: bool = False  # unused in SG; kept for API compatibility

    def __post_init__(self) -> None:
        if self.suit in (Suit.MAN, Suit.PIN, Suit.SOU):
            if not 1 <= self.value <= 9:
                raise ValueError(f"suited value out of range: {self.value}")
        elif self.suit == Suit.WIND:
            if not 0 <= self.value <= 3:
                raise ValueError(f"wind value out of range: {self.value}")
        elif self.suit == Suit.DRAGON:
            if not 0 <= self.value <= 2:
                raise ValueError(f"dragon value out of range: {self.value}")
        elif self.suit == Suit.FLOWER:
            if not 0 <= self.value <= 7:
                raise ValueError(f"flower value out of range: {self.value}")
        elif self.suit == Suit.ANIMAL:
            if not 0 <= self.value <= 3:
                raise ValueError(f"animal value out of range: {self.value}")

    @property
    def is_suited(self) -> bool:
        return self.suit in (Suit.MAN, Suit.PIN, Suit.SOU)

    @property
    def is_honor(self) -> bool:
        return self.suit in (Suit.WIND, Suit.DRAGON)

    @property
    def is_flower(self) -> bool:
        return self.suit == Suit.FLOWER

    @property
    def is_animal(self) -> bool:
        return self.suit == Suit.ANIMAL

    @property
    def is_bonus(self) -> bool:
        """Flower or animal — exposed immediately, not used in sets."""
        return self.is_flower or self.is_animal

    @property
    def is_terminal(self) -> bool:
        return self.is_suited and self.value in (1, 9)

    @property
    def is_terminal_or_honor(self) -> bool:
        return self.is_honor or self.is_terminal

    @property
    def is_simple(self) -> bool:
        return self.is_suited and 2 <= self.value <= 8

    @property
    def flower_wind(self) -> int | None:
        """Season/Flower 1→E(0) … 4→N(3)."""
        if not self.is_flower:
            return None
        return self.value % 4

    @property
    def is_season_set(self) -> bool:
        return self.is_flower and 0 <= self.value <= 3

    @property
    def is_flower_set(self) -> bool:
        return self.is_flower and 4 <= self.value <= 7

    def same_tile(self, other: Tile) -> bool:
        return self.suit == other.suit and self.value == other.value

    def label(self) -> str:
        if self.suit == Suit.MAN:
            return f"{self.value}m"
        if self.suit == Suit.PIN:
            return f"{self.value}p"
        if self.suit == Suit.SOU:
            return f"{self.value}s"
        if self.suit == Suit.WIND:
            return ("E", "S", "W", "N")[self.value]
        if self.suit == Suit.DRAGON:
            return ("Haku", "Hatsu", "Chun")[self.value]
        if self.suit == Suit.FLOWER:
            if self.value <= 3:
                return f"Sea{self.value + 1}"
            return f"Flo{self.value - 3}"
        return ("Cat", "Mouse", "Chick", "Centi")[self.value]

    def short(self) -> str:
        return self.label()

    def unicode(self) -> str:
        if self.suit == Suit.MAN:
            return chr(0x1F007 + self.value - 1)
        if self.suit == Suit.PIN:
            return chr(0x1F019 + self.value - 1)
        if self.suit == Suit.SOU:
            return chr(0x1F010 + self.value - 1)
        if self.suit == Suit.WIND:
            return ("🀀", "🀁", "🀂", "🀃")[self.value]
        if self.suit == Suit.DRAGON:
            return ("🀆", "🀅", "🀄")[self.value]
        if self.suit == Suit.FLOWER:
            # Season plum/orchid/bamboo/chrys + flower variants
            return ("🀦", "🀧", "🀨", "🀩", "🀢", "🀣", "🀤", "🀥")[self.value]
        return ("🐱", "🐭", "🐔", "🐛")[self.value]

    def key(self) -> tuple[int, int, int]:
        return (int(self.suit), self.value, 0)


def tile_set_148() -> list[Tile]:
    """Full Singapore set: 136 playable + 8 flowers + 4 animals."""
    tiles: list[Tile] = []
    for suit in (Suit.MAN, Suit.PIN, Suit.SOU):
        for v in range(1, 10):
            tiles.extend(Tile(suit, v) for _ in range(4))
    for w in range(4):
        tiles.extend(Tile(Suit.WIND, w) for _ in range(4))
    for d in range(3):
        tiles.extend(Tile(Suit.DRAGON, d) for _ in range(4))
    for f in range(8):
        tiles.append(Tile(Suit.FLOWER, f))
    for a in range(4):
        tiles.append(Tile(Suit.ANIMAL, a))
    assert len(tiles) == 148
    return tiles


# Back-compat alias used by older imports
def tile_set_136(*, use_aka: bool = True) -> list[Tile]:
    return tile_set_148()


def counts_by_tile(tiles: list[Tile]) -> dict[tuple[Suit, int], int]:
    out: dict[tuple[Suit, int], int] = {}
    for t in tiles:
        k = (t.suit, t.value)
        out[k] = out.get(k, 0) + 1
    return out
