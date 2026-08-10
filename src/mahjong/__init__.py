"""Pure Singapore Mahjong engine (no Telegram dependency)."""

from .tiles import Suit, Tile, tile_set_136, tile_set_148
from .game import Game, GamePhase

__all__ = ["Suit", "Tile", "tile_set_136", "tile_set_148", "Game", "GamePhase"]
