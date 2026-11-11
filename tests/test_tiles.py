"""Unit tests for Singapore Mahjong tiles."""

from mahjong.tiles import Suit, Tile, tile_set_148, tile_set_136


def test_tile_set_148_counts():
    tiles = tile_set_148()
    assert len(tiles) == 148
    flowers = [t for t in tiles if t.suit == Suit.FLOWER]
    animals = [t for t in tiles if t.suit == Suit.ANIMAL]
    assert len(flowers) == 8
    assert len(animals) == 4
    for suit in (Suit.MAN, Suit.PIN, Suit.SOU):
        for v in range(1, 10):
            assert sum(1 for t in tiles if t.suit == suit and t.value == v) == 4
    for w in range(4):
        assert sum(1 for t in tiles if t.suit == Suit.WIND and t.value == w) == 4
    for d in range(3):
        assert sum(1 for t in tiles if t.suit == Suit.DRAGON and t.value == d) == 4


def test_tile_set_136_alias_is_148():
    assert len(tile_set_136()) == 148


def test_bonus_helpers():
    f = Tile(Suit.FLOWER, 0)
    a = Tile(Suit.ANIMAL, 2)
    assert f.is_bonus and f.is_flower and f.flower_wind == 0
    assert a.is_bonus and a.is_animal
    assert f.label().startswith("Sea")
    assert a.unicode()
