"""Compatibility shim — scoring lives in fan.py (Singapore)."""

from __future__ import annotations

from .fan import FanItem, FanResult, evaluate_fan, payout_win

__all__ = ["FanItem", "FanResult", "evaluate_fan", "payout_win"]
