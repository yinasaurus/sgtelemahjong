# Pre-launch ship check — Tele Mahjong (Singapore)

**Date:** 2026-11-11  
**Scope:** Read-only review of `c:\Users\USER\Documents\side_proj\tele mahjong`  
**Audience assumption:** friends-first public bot (group + solo bots)  
**Hosting:** undecided (Render paid worker / Oracle Always Free / local)

---

## 1. Verdict: **SHIP AFTER FIXES**

Playable Singapore Mahjong over Telegram exists end-to-end (engine + DM photos + group board + bots).  
It is **not launch-ready as-is**: the test suite is largely broken against the SG rewrite, README/product copy still say Riichi, live hands die on process restart, and image/font paths will look wrong on a Linux VM.  
For a **friends-only** soft launch after the blockers below, yes. For a discoverable public bot, fix blockers + auth/rate/spam items first.

---

## 2. STEP 1 — Understanding (summary)

- **Structure:** `main.py` entry; `src/mahjong/` pure engine; `src/bot/` Telegram UI/flow; `src/db/` SQLite session history; `assets/tiles/` FluffyStuff PNGs; `tests/` (stale Riichi-oriented).
- **Libraries:** `python-telegram-bot` 21–22, `python-dotenv`, `Pillow`, `pytest` (`requirements.txt`, `pyproject.toml`).
- **Updates:** long **polling** — `app.run_polling(...)` in `main.py` lines 73–74. No webhook path.
- **Commands:** registered at startup via `set_my_commands` for default/private/group scopes (`main.py` 47–52).
- **Game state:** in-memory `TableManager.tables` (`src/bot/state.py`). SQLite persists table metadata, seats, hand results, running totals — **not** the live `Game` object / wall / hands.
- **Images:** Pillow composes felt board + hand PNGs from `assets/tiles` (`src/bot/tile_art.py`, `table_view.py`); sent as `BytesIO` photos each refresh (`src/bot/flow.py` `refresh_board` / `send_hand_dm`). No Telegram `file_id` cache.
- **Ruleset:** club-style **Singapore Mahjong** (148 tiles, flowers/animals, fan) — `RULES.md`, `src/mahjong/fan.py`, in-bot `/rules` (`src/bot/guide.py`).

---

## 3. Blockers (must fix before launch)

### B1. Test suite does not match the SG engine (CI is red)
- **Problem:** Most tests import removed Riichi APIs (`PlayerState`, `parse_tiles`, `score_win`, aka/dora).  
- **Evidence:** `pytest` collection errors in `tests/test_game.py:3`, `tests/test_hand.py:8`, `tests/test_tiles.py:1`, `tests/test_scoring.py:2`, `tests/test_bot_player.py:16`. Remaining runnable tests: **2 failed, 6 passed** (`test_settlement` / `test_session_db` still expect Riichi 25k/uma).  
- **Why it matters:** You cannot trust a ship without a green core suite after a ruleset rewrite.  
- **Fix:** Rewrite/delete Riichi tests; add SG tile count, deal, claim priority, fan chicken/min-fan, flower flush tests. Align settlement tests with `SessionRules` defaults in `src/mahjong/settlement.py:9–14` (start/return/uma = 0).

### B2. Product docs still brand the bot as Japanese Riichi
- **Problem:** `README.md` opens with “Japanese Riichi”; `pyproject.toml` name/description `tele-mahjong-riichi` / “Riichi Mahjong Telegram bot”.  
- **Why it matters:** First thing friends (and you in 3 months) will read is wrong; BotFather “About” will drift from `/start`.  
- **Fix:** Rewrite README for SG + how to run/deploy; rename package metadata; drop Riichi from BotFather description.

### B3. Active games are lost on restart / deploy
- **Problem:** `TableManager.persist` only upserts lobby seats/rules (`src/bot/state.py:262–270` → `db.upsert_table`). Live `table.game` is never serialized. Process restart empties `self.tables` (`state.py:203`).  
- **Why it matters:** Oracle reboot, `systemctl restart`, OOM, or redeploy mid-hand orphans the table; users see “No table” with no recovery.  
- **Fix (pragmatic):** On startup, mark DB rows `active` as abandoned and announce “bot restarted — start a new table”; **or** serialize minimal game state. Document “restart = end hand” if friends-only.

### B4. Flower/animal tile faces hardcode Windows fonts (Linux host breaks look)
- **Problem:** `src/bot/tile_art.py` `_draw_bonus_face` uses `C:\Windows\Fonts\seguiemj.ttf` / `arialbd.ttf` (lines ~45–48). On Oracle/Ubuntu this falls through to `load_default()` — tiny unreadable bonus tiles.  
- **Why it matters:** SG set always deals flowers/animals; board/DM will look broken in production.  
- **Fix:** Ship a font under `assets/fonts/` or use DejaVu/Noto paths; keep Windows paths as fallback only.

### B5. Stale / conflicting BotFather + privacy guidance
- **Problem:** README still says disable Group Privacy (correct for groups) but describes Riichi. Code `/start` is SG (`guide.py`).  
- **Why it matters:** Privacy mode ON = bot ignores most group messages; menus via buttons still work, but `/menu` typed may not if privacy is on and bot isn’t @mentioned — [VERIFY] with your BotFather setting.  
- **Fix:** Update README with: Privacy Mode **off**, single instance only, SG description, command list matching `main.py:_COMMANDS`.

---

## 4. Should-fix soon

### S1. Unauthenticated `t:{chat}:end` abandon callback
- **Where:** `src/bot/handlers/callbacks.py:302–309` — no seat/host check; any callback with that data ends the table.  
- **Note:** Current keyboards prefer `endsession` (`keyboards.py`), but a crafted client callback can still hit `end`.  
- **Fix:** Require host or seated player (same as `cmd_endtable` in `commands.py:235–237`).

### S2. `concurrent_updates(True)` without per-table lock
- **Where:** `main.py:60`. Double-tap discard/claim can interleave two mutations on one `Game`.  
- **Fix:** `asyncio.Lock` per `chat_id` around game mutations in callback/timeout/bot loop.

### S3. No Telegram `file_id` reuse; PNG rebuilt every move
- **Where:** `flow.refresh_board` / `send_hand_dm` / `announce_discard` always `BytesIO(png)`.  
- **Why:** CPU + upload bandwidth; risk of hitting group rate limits during claim windows + pings + board edits.  
- **Fix:** Cache static single-tile `file_id`s; throttle board edits; coalesce bot-turn announcements.

### S4. No `RetryAfter` / 429 handling
- **Where:** send/edit paths catch broad `Exception` / `BadRequest` but not flood wait (`flow.py` board/DM/ping).  
- **Fix:** Catch `telegram.error.RetryAfter`, sleep `retry_after`, retry once.

### S5. Difficulty UX inconsistency
- **Where:** Engine supports `hard` (`bot_player.py` `BotDifficulty`); `.env` can set `hard` (`config.py`); but `/newtable diff=` and `fill_bots` reject anything but easy/normal (`commands.py:107–108`, `state.py:99` message still says “easy or normal”). Menu solo buttons are easy/normal only (`keyboards.py:73–80`).  
- **Fix:** Allow `hard` everywhere or remove it from config docs.

### S6. Wall “15 left” rule unused
- **Where:** `Wall.END_LIVE = 15` (`wall.py`); game ends only when `remaining_live <= 0` (`game.py:243`, `704–708`). Dead condition `<= END_LIVE and <= 0`.  
- **Fix:** Either enforce reserve-15 draw or update `RULES.md` / `/rules` to “play until wall empty”.

### S7. Settlement still talks uma/oka; defaults are zero
- **Where:** `SessionRules` zeros (`settlement.py:9–14`); UI strings still mention uma (`commands.py:241`, session_ops).  
- **Fix:** SG-friendly standings copy (fan points only) or restore optional uma.

### S8. No global PTB error handler / graceful shutdown hook
- **Where:** `main.py` has no `app.add_error_handler`. Callbacks swallow with user-facing “Error — try /table” (`callbacks.py:48–50`) — good — but unhandled command errors may be quieter than you want.  
- **Fix:** One error handler that logs `update` + chat_id.

### S9. No root `LICENSE`; package branding mismatch
- Tile art CC0 documented (`assets/tiles/LICENSE.txt`). Project has **no** top-level LICENSE. Name still Riichi in packaging.

### S10. Group rate-limit pressure
- Per discard: board photo edit + sticky discard photo + turn ping + N DM photo edits + bot loop. Easy to burst.  
- **Fix:** Prefer editing one board; skip ping if same seat; delay bot acts slightly (already 0.2–0.55s in `flow.py`).

---

## 5. Nice-to-have polish

- Cache rendered tile faces beyond `_load_face` LRU; cache board dimensions.
- Persist/restore lobby tables from SQLite on boot (seats only).
- `/privacy` one-liner: stores chat_id, user_id, display_name, scores; `/endtable` abandons; no full erase-me yet (`db/models.py` schema).
- Bot profile photo + About text in BotFather (SG mahjong, group play).
- Replace leftover Riichi stubs (`yaku.py`, riichi callbacks that only alert) with deletion for clarity.
- Dockerfile optional if you stick to systemd on Oracle (`deploy/tele-mahjong.service` already exists).
- Pin exact dependency versions (lockfile); `requirements.txt` uses ranges only.
- Drop committed `Singapore Mahjong Rules.pdf` from git if you don’t need it on the server (~600KB); keep local.

---

## 6. Launch-day checklist

- [ ] BotFather: name, About, description = **Singapore Mahjong** (not Riichi)
- [ ] BotFather: Group Privacy Mode **OFF**
- [ ] BotFather: command list matches `main.py` (`/start /menu /howto /rules /hand /standings /endsession` + any extras you keep)
- [ ] Confirm only **one** process runs (`systemctl` **or** PC — not both) to avoid `409 Conflict`
- [ ] `.env` / host env: `TELEGRAM_BOT_TOKEN`, `BOT_DIFFICULTY`, timeouts, `DATABASE_PATH` on persistent disk
- [ ] Token never committed ([VERIFY] rotate if it ever leaked in chat/logs outside git)
- [ ] Fonts for flowers work on host (smoke a hand with a flower)
- [ ] Green `pytest` for SG core tests
- [ ] Soft-launch with 1 group: solo vs 3 bots, then 2 humans + bots
- [ ] Monitoring: `journalctl -u tele-mahjong -f` (or host logs)
- [ ] Know how to `/endtable` / restart if stuck

---

## 7. Manual smoke-test script (Telegram)

### A. Private chat
1. Open bot → `/start`  
   **Expect:** Singapore welcome (`guide.START_PRIVATE`), not Riichi; buttons How to start / Rules / Add to group.
2. `/rules` → page through Basics / Calls / Flowers / Fan  
   **Expect:** SG content; no riichi/dora as required.
3. `/howto`  
   **Expect:** group-first instructions.

### B. Group — solo vs bots
1. Add bot to a group; make it admin if you want pin (`flow._pin_board`).
2. `/menu` → **Play solo (3 normal bots)**  
   **Expect:** table deals; group board photo; message about opening private chat.
3. Open private chat (Start once if needed) → hand photo with numbered tiles.  
   **Expect:** flowers/animals readable (not blank garbage).
4. Discard via numbered buttons.  
   **Expect:** group sticky “threw …” updates; bots eventually discard; your DM refreshes; no stack traces in chat.
5. When claim buttons appear, tap **Skip** once.  
   **Expect:** `answerCallbackQuery` toast; game continues (timeout ~60s if AFK — `CLAIM_TIMEOUT_S`).
6. If you can WIN (self-draw / game), tap it.  
   **Expect:** hand-over message with **fan** (not “han/fu” preferred — note `flow.py` end text still uses `fan` via `sc.han` field naming).
7. **Next hand** → new deal.  
   **Expect:** works without creating a second table.
8. **End session** → standings text.  
   **Expect:** table gone; `/menu` can start fresh.

### C. Auth / stale buttons
1. From a non-seated group member, tap an old **My hand** / discard button if visible.  
   **Expect:** “Not your seat” / “You’re not seated” (`callbacks.py` `_auth_seat`).
2. After session end, tap old **Next hand**.  
   **Expect:** “No table” / safe alert — not a crash.

### D. Restart resilience
1. Mid-hand, restart the process.  
   **Expect today:** in-memory table gone (document this). After B3 fix: graceful abandon message.

### E. Dual instance (negative test)
1. Run two `python main.py`.  
   **Expect:** Telegram `Conflict` / flaky updates — confirm you only ship one.

---

## 8. Top 10 missing tests

1. `test_tile_set_148_counts` — 148 tiles; 8 flowers; 4 animals; 4× each suited/honor.  
2. `test_new_hand_deal_and_flower_flush` — 13/14 shapes after bonus replacements; no bonus left in concealed.  
3. `test_claim_priority_win_over_pong` — win beats pong; closest-from-discarder among multiple wins (`game.resolve_claims`).  
4. `test_chow_only_from_left` — non-next seat cannot chi.  
5. `test_miss_rule_blocks_later_pong_or_win` — skipped claim tiles enter `missed` / temp furiten.  
6. `test_evaluate_fan_chicken_and_min_fan` — chicken legal at min_fan=1; invalid shape returns `None`.  
7. `test_evaluate_fan_all_chow_ping_wu_self_draw` — known 14-tile closed chow hand fan list.  
8. `test_open_hand_win_after_pong` — free-tile length ≠ 14 still `is_winning_hand`.  
9. `test_bot_normal_always_takes_ron` — `choose_claim_action` returns RON when eligible.  
10. `test_auth_seat_rejects_other_player_discard_callback` — handler-level or pure `_auth_seat` unit test.

---

## 9. [VERIFY] — check yourself

- [ ] BotFather **Group Privacy** current setting (README claims it must be off).  
- [ ] Whether your real token ever appeared in a **public** GitHub remote, screenshot, or shared log (local `.env` is gitignored; `git grep` on HEAD did **not** find `8735584402` / `AAH7` in tracked text; rotate if unsure).  
- [ ] Hosting choice: Render Background Worker = paid; Oracle free VM = fonts + systemd; local PC = sleep/USB issues.  
- [ ] Whether friends need uma/oka or raw fan totals (code defaults to 0 uma).  
- [ ] Acceptable behaviour on restart mid-hand (abandon vs restore).  
- [ ] Whether “wall ends at 15 remaining” is a house rule you care about (`END_LIVE` unused).  
- [ ] Telegram Bot API flood limits under 4-player human table (not fully load-tested here).  
- [ ] Pin permission: without admin, board won’t stick (`flow._pin_board` swallows errors).

---

## 10. Security / secrets snapshot

| Check | Result |
|--------|--------|
| `.env` gitignored | Yes (`.gitignore`) |
| `.env.example` present | Yes (placeholder token) |
| Token in current git tree | Not found via `git grep -a` for known token fragments |
| SQL | Parameterized in `src/db/models.py` |
| `eval` / shell | Not found in `src/` |
| User errors leak stacks | Callbacks catch and show short alert (`callbacks.py:48–50`) |
| Webhook secret | N/A (polling) |

---

## 11. Area scores (blunt)

| Area | Grade | Note |
|------|-------|------|
| Security | B | Secrets OK locally; craftable `end` callback; no flood control |
| Game correctness | B- | SG engine smoke OK; tests red; wall-15 / fan house rules need honesty |
| Telegram behaviour | B | Auth on discards/claims good; concurrent + spam risk |
| Images/assets | B- | CC0 tiles OK; flower fonts / no file_id cache hurt prod |
| State/reliability | C+ | Restart kills live games; timers exist; no locks |
| Deploy | C+ | Procfile/render/systemd present; docs stale; no healthcheck |
| UX | B+ | `/start`/`/rules` SG copy is solid; README lies |
| Hygiene | C | Broken tests, Riichi naming, no project LICENSE |

---

*End of report. No other files were modified. Say which blockers/should-fixes you want applied next.*
