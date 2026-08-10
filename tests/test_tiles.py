from mahjong.tiles import Suit, Tile, parse_tile, parse_tiles, tile_set_136


def test_tile_set_136_with_aka():
    tiles = tile_set_136(use_aka=True)
    assert len(tiles) == 136
    aka = [t for t in tiles if t.aka]
    assert len(aka) == 3
    assert {t.suit for t in aka} == {Suit.MAN, Suit.PIN, Suit.SOU}


def test_dora_next_wraps():
    assert Tile(Suit.MAN, 9).dora_next() == Tile(Suit.MAN, 1)
    assert Tile(Suit.WIND, 3).dora_next() == Tile(Suit.WIND, 0)  # N → E
    assert Tile(Suit.DRAGON, 2).dora_next() == Tile(Suit.DRAGON, 0)  # Chun → Haku


def test_parse_tiles():
    tiles = parse_tiles("123m45p EE Haku r5s")
    assert len(tiles) == 3 + 2 + 2 + 1 + 1
    assert tiles[-1].aka and tiles[-1].suit == Suit.SOU
    assert parse_tile("5m").value == 5
