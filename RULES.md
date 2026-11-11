# Singapore Mahjong — engine scope

Source of truth for what `src/mahjong/` implements. Club-friendly Singapore style
(not Japanese Riichi / not full tournament SG).

---

## Tile set

- **148 tiles**: man/pin/sou 1–9 ×4, winds E/S/W/N ×4, dragons ×4,
  **8 flowers** (4 seasons + 4 flowers), **4 animals** (cat, mouse, chicken, centipede).
- No aka-dora / no dora indicators.

---

## Wall

- Live draws from the front; flower/animal/kong **replacements from the wall end**.
- Hand ends in a draw when the **live wall is empty** (no remaining live tiles).

---

## Flowers & animals

- Drawn bonuses are **exposed immediately**; draw a replacement.
- Immediate set payouts (animal pairs, all seasons/flowers/animals, seat-flower pair).
- **Eight flowers** = special win. All three dragons / all four winds exposed = special win.

---

## Win shapes

| Shape | Implemented |
|-------|-------------|
| Standard 4 melds + pair | Yes (open or closed) |
| Seven pairs | Yes (house) |
| Thirteen wonders | Yes |

---

## Fan (scoring) — implemented subset

Chicken, Self-draw, Fully Concealed, All Chow, Ping Wu, All Pong, Hidden Treasure,
Dragon / Seat / Prevailing wind, Two/Three dragons, Three/Four winds,
Half Flush, Flush, Terminals patterns, Seven Pairs, Thirteen Wonders,
flowers/animals, Robbing a Kong, replacement / last-tile bonuses.

Default **min 1 fan**; payouts use fan as points (self-draw: each pays; discard: discarder pays).

---

## Not Riichi

No riichi, ippatsu, dora/ura, aka, fu, honba sticks (API stubs may exist for Telegram compat).

---

## Telegram bot

Group board + DM hand photos. Bots: Ah Beng / Ah Seng / Ah Lian.
