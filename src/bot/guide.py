"""Player-facing how-to-start + rules book (Telegram-sized)."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- How to start -----------------------------------------------------------

START_PRIVATE = (
    "🀄 Welcome to Singapore Mahjong\n\n"
    "This private chat is only for your secret hand.\n"
    "You start the game in a GROUP — not here.\n\n"
    "How to start (first time)\n"
    "1) Tap Add me to a group\n"
    "2) In the group, send /start or /menu\n"
    "3) Tap Play solo (bots) or Friends\n"
    "4) Friends tap Join seat\n"
    "5) When dealt, open this chat once (Start once only)\n"
    "6) Tap numbered buttons here to throw tiles\n\n"
    "Tips\n"
    "• Group = board / ponds / whose turn\n"
    "• Here = your hand only\n"
    "• /rules — short rules book\n"
    "• /howto — this guide again"
)

START_GROUP_FRESH = (
    "🀄 Singapore Mahjong — start here\n\n"
    "This GROUP is where the table lives.\n\n"
    "Quick start\n"
    "1) Tap Play solo (easiest) — you + 3 bots\n"
    "2) Or Friends… then everyone taps Join\n"
    "3) Open the bot in private once so you get your hand\n"
    "4) Throw tiles with the numbered buttons in DM\n"
    "5) Watch ponds / turns on the group board\n\n"
    "More\n"
    "📖 Rules book  ·  ❓ How to start  ·  /rules /howto"
)

START_GROUP_ACTIVE = (
    "🀄 A table is already open in this group.\n\n"
    "• Friends: tap Join\n"
    "• Seated: Board / My hand / Scores\n"
    "• Stuck? /howto or 📖 Rules book"
)

HOWTO = (
    "❓ How to start\n\n"
    "1) Someone adds the bot to a Telegram group\n"
    "2) In the group send /menu (or /start)\n"
    "3) Tap a Play button:\n"
    "    • Solo = you + bots (instant)\n"
    "    • Friends = humans join empty seats\n"
    "4) Each human opens the bot in PRIVATE once\n"
    "    (tap Open private chat → Start — only once)\n"
    "5) Your hand photo arrives in DM\n"
    "6) Tap numbered buttons to discard\n"
    "7) Group shows who threw what + whose turn\n\n"
    "Calls (chow/pong/kong/win): buttons appear in DM\n"
    "when you can call.\n\n"
    "Singapore style: flowers & animals, no riichi/dora.\n\n"
    "Commands: /menu /hand /rules /howto /standings"
)

# --- Rules book pages -------------------------------------------------------

RULES_PAGES: list[tuple[str, str]] = [
    (
        "Basics",
        "📖 Rules · Basics (Singapore)\n\n"
        "Goal: make a winning hand and declare self-draw "
        "or WIN (game) on someone’s discard.\n\n"
        "Standard win shape\n"
        "• 4 sets + 1 pair\n"
        "• Set = chow / pong / kong\n"
        "Also: seven pairs, or thirteen wonders.\n\n"
        "Tiles\n"
        "• Characters · Circles · Bamboo (1–9)\n"
        "• Winds · Dragons\n"
        "• 8 flowers + 4 animals (expose + replace)\n\n"
        "Turns\n"
        "Draw → (optional kong/win) → discard one tile.",
    ),
    (
        "Calls",
        "📖 Rules · Calls\n\n"
        "When someone discards, others may call (DM buttons):\n\n"
        "• CHOW — sequence, only the next seat\n"
        "• PONG — triplet (any seat)\n"
        "• KONG — quad from discard\n"
        "• WIN (game) — win on that discard\n"
        "• Skip — decline\n\n"
        "Priority: win > kong/pong > chow.\n"
        "After chow/pong you must discard (no draw).\n\n"
        "Miss rule: if you skip a win/pong you could take, "
        "you may not claim that tile type for a while.",
    ),
    (
        "Flowers",
        "📖 Rules · Flowers & animals\n\n"
        "Drawn flowers/animals are exposed immediately; "
        "you take a replacement from the wall end.\n\n"
        "• Each flower/animal = fan when you win\n"
        "• Seat flower = extra\n"
        "• Animal pairs / full sets pay bonus points now\n"
        "• Eight flowers = instant win\n\n"
        "No riichi and no dora in this ruleset.",
    ),
    (
        "Fan",
        "📖 Rules · Fan (scoring)\n\n"
        "Need at least 1 fan to win (chicken hand counts).\n\n"
        "Easy fan\n"
        "• Chicken · Self-draw · All Chow · Ping Wu\n"
        "• Dragon / seat / prevailing wind pong\n"
        "• Flowers & animals\n\n"
        "Bigger\n"
        "• All Pong · Half Flush · Flush · Seven Pairs\n"
        "• Thirteen Wonders · Hidden Treasure\n\n"
        "Self-draw → each pays; discard win → discarder pays.\n"
        "Session: /standings · End session.",
    ),
    (
        "This bot",
        "📖 Rules · This bot\n\n"
        "What you do in Telegram\n"
        "• Group = public board (ponds, turn, last throw)\n"
        "• DM = your hand photo + action buttons\n"
        "• Throw = tap a numbered button (matches badge)\n"
        "• Timeout = auto-throw if you AFK too long\n\n"
        "Bots: Ah Beng / Ah Seng / Ah Lian fill empty seats.\n\n"
        "Help: /howto   Menu: /menu   Hand: /hand",
    ),
]


def rules_page(index: int) -> tuple[str, int]:
    """Return (text, clamped_index)."""
    if not RULES_PAGES:
        return ("No rules loaded.", 0)
    i = max(0, min(index, len(RULES_PAGES) - 1))
    return RULES_PAGES[i][1], i


def rules_keyboard(chat_id: int, index: int) -> InlineKeyboardMarkup:
    n = len(RULES_PAGES)
    i = max(0, min(index, n - 1))
    title = RULES_PAGES[i][0]
    rows: list[list[InlineKeyboardButton]] = []
    tab_row: list[InlineKeyboardButton] = []
    for j, (name, _) in enumerate(RULES_PAGES):
        label = f"·{name}·" if j == i else name
        tab_row.append(
            InlineKeyboardButton(label, callback_data=f"m:{chat_id}:rules:{j}")
        )
        if len(tab_row) == 3:
            rows.append(tab_row)
            tab_row = []
    if tab_row:
        rows.append(tab_row)
    nav: list[InlineKeyboardButton] = []
    if i > 0:
        nav.append(
            InlineKeyboardButton(
                "← Prev", callback_data=f"m:{chat_id}:rules:{i - 1}"
            )
        )
    nav.append(
        InlineKeyboardButton(f"{i + 1}/{n} {title}", callback_data=f"m:{chat_id}:rules:{i}")
    )
    if i < n - 1:
        nav.append(
            InlineKeyboardButton(
                "Next →", callback_data=f"m:{chat_id}:rules:{i + 1}"
            )
        )
    rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton("❓ How to start", callback_data=f"m:{chat_id}:howto"),
            InlineKeyboardButton("🀄 Menu", callback_data=f"m:{chat_id}:menu"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def howto_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📖 Rules book", callback_data=f"m:{chat_id}:rules:0"
                )
            ],
            [InlineKeyboardButton("🀄 Menu", callback_data=f"m:{chat_id}:menu")],
        ]
    )
