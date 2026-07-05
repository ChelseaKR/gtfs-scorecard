#!/usr/bin/env python3
"""WCAG 2.x relative-luminance contrast checker for the scorecard site.

Asserts every text/background pair we touch clears AAA: 7:1 for normal text,
4.5:1 for large text (>=18.66px bold or >=24px). Covers the default light
palette, the landing page tokens, the OS/explicit dark theme, and the
high-contrast theme. Run before committing the accessibility work:

    python3 pipeline/scripts/check_contrast.py
"""

from __future__ import annotations

import sys


def _lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(hexstr: str) -> float:
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg: str, bg: str) -> float:
    l1, l2 = lum(fg), lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# Each entry: (label, fg, bg, large?). Large text needs 4.5:1; normal needs 7:1.
# Tokens resolved per theme below; literal hexes pass through.
PAIRS: list[tuple[str, str, str, bool]] = [
    # ---- default light palette / app shared styles.css ----
    ("app --ink body on --paper", "ink", "paper", False),
    ("app --ink-soft on --paper", "ink-soft", "paper", False),
    ("app --ink-soft on --card", "ink-soft", "card", False),
    ("app --ink-soft on --paper-deep (fix-effort)", "ink-soft", "paper-deep", False),
    ("app --green link on --paper", "green", "paper", False),
    ("app --green link on --card", "green", "card", False),
    ("app --green-bright on --card (aeta/peer-note)", "green-bright", "card", False),
    ("app --error sev text on --card", "error", "card", False),
    ("app --warning sev text on --card", "warning", "card", False),
    ("app --info sev text on --card", "info", "card", False),
    # Fix NN badges use an explicit dark fill per theme (badge-error etc.),
    # not the brightened severity token, so white text clears AAA on them.
    ("app white on error badge fill", "#ffffff", "badge-error", False),
    ("app white on warning badge fill", "#ffffff", "badge-warning", False),
    ("app white on info badge fill", "#ffffff", "badge-info", False),
    ("app --paper on --green pressed chip", "paper", "green", False),
    # board (dark) text
    ("app --board-soft (score-of) on --board", "board-soft", "board", False),
    # The board hero text is a fixed light cream (#f4ecd9), independent of theme,
    # because the board ground is always dark; reel/title sit on it.
    ("app board title #f4f6f0 on --board", "#f4f6f0", "board", False),
    ("app --amber board kicker on --board", "amber", "board", False),
    ("app .chip text on --board", "#dfe7dd", "board", False),
    ("app footer link on --board", "#f4f6f0", "board", False),
    ("app footer text on --board", "#cfdcd2", "board", False),
    # 2.4.13 focus appearance: the dark chrome band (header + footer) rings its
    # controls in --amber, not the blue --focus (which is tuned for the light
    # page and drops to ~1.6:1 on pine). Amber on pine clears even the 7:1 text
    # bar, so testing it here also covers the 3:1 non-text focus requirement. The
    # header background is a literal #102a20 in every theme; the footer uses
    # --board (darker in dark/contrast), so #102a20 is the lightest ground.
    ("app --amber focus ring on pine #102a20", "amber", "#102a20", False),
    # ---- landing page inline tokens (web/index.html) ----
    ("landing --ink-soft on --paper", "L_ink-soft", "L_paper", False),
    ("landing --ink-soft on --paper-2", "L_ink-soft", "L_paper-2", False),
    ("landing --green on --paper (sectlabel/stop.n)", "L_green", "L_paper", False),
    ("landing --green on --paper-2 (who band)", "L_green", "L_paper-2", False),
    ("landing --rust on --paper card", "L_rust", "L_paper", False),
    ("landing --ink on --paper", "L_ink", "L_paper", False),
    ("landing .lede #dfe7dd on --pine", "#dfe7dd", "L_pine", False),
    ("landing .reassure #b9c7ba on --pine", "#b9c7ba", "L_pine", False),
    ("landing board .lab #b9c7ba on --pine-2", "#b9c7ba", "L_pine-2", False),
    ("landing footer #b9c7ba on --pine", "#b9c7ba", "L_pine", False),
    ("landing cta p #d3decf on --pine", "#d3decf", "L_pine", False),
    # Primary nav: cream stops on the pine wayfinding bar (theme-independent).
    ("nav active stop on pine", "#f4f6f0", "#102a20", False),
    ("nav inactive stop on pine", "#cfdcd2", "#102a20", False),
    # --on-pine is the cream text on the pine chrome (hero, board, cta, footer,
    # nav). It must stay light in EVERY theme; this pair is what would have caught
    # the dark-mode regression where the chrome text used --paper and went dark.
    ("landing --on-pine on --pine (hero/board/cta/footer/nav)", "L_on-pine", "L_pine", False),
    ("landing --on-pine on --pine-2 (board)", "L_on-pine", "L_pine-2", False),
    ("landing btn-primary #2a1c00 on --amber", "#2a1c00", "L_amber", False),
]

THEMES: dict[str, dict[str, str]] = {
    "light": {
        # app shared tokens
        "ink": "#20241f",
        "ink-soft": "#3d4339",
        "paper": "#f2f3ee",
        "paper-deep": "#e5e8df",
        "card": "#fbfcf8",
        "green": "#163a2c",
        "green-bright": "#1d4633",
        "error": "#8e2a23",
        "warning": "#6b490e",
        "info": "#3a4753",
        "board": "#102a20",
        "board-soft": "#bcccbd",
        "amber": "#fdc70a",
        "badge-error": "#8e2a23",
        "badge-warning": "#6b490e",
        "badge-info": "#3a4753",
        # landing tokens (light)
        "L_ink": "#15231c",
        "L_ink-soft": "#3c4840",
        "L_paper": "#f2f3ee",
        "L_paper-2": "#e5e8df",
        "L_green": "#11522a",
        "L_rust": "#822c12",
        "L_pine": "#102a20",
        "L_pine-2": "#163a2c",
        "L_on-pine": "#f4f6f0",
        "L_amber": "#fdc70a",
    },
    "dark": {
        "ink": "#e9e4d7",
        "ink-soft": "#c2c8bc",
        "paper": "#15181b",
        "paper-deep": "#0f1113",
        "card": "#1d2125",
        "green": "#7fd3a6",
        "green-bright": "#97e0bd",
        "error": "#f0938a",
        "warning": "#e7bd6a",
        "info": "#a9c4d6",
        "board": "#0c1410",
        "board-soft": "#cdd9ce",
        "amber": "#fdc70a",
        "badge-error": "#7e2a23",
        "badge-warning": "#5c3d0a",
        "badge-info": "#2f4452",
        # landing dark
        "L_ink": "#e9e4d7",
        "L_ink-soft": "#c2c8bc",
        "L_paper": "#15181b",
        "L_paper-2": "#1d2125",
        "L_green": "#7fd3a6",
        "L_rust": "#f0a07f",
        "L_pine": "#0c1410",
        "L_pine-2": "#14201a",
        "L_on-pine": "#e9e4d7",
        "L_amber": "#ffd34d",
    },
    "contrast": {
        "ink": "#000000",
        "ink-soft": "#1a1a1a",
        "paper": "#ffffff",
        "paper-deep": "#f2f2f2",
        "card": "#ffffff",
        "green": "#0a4420",
        "green-bright": "#0a4420",
        "error": "#7a0000",
        "warning": "#5a4900",
        "info": "#003a5a",
        "board": "#000000",
        "board-soft": "#f2f2f2",
        "amber": "#ffd34d",
        "badge-error": "#7a0000",
        "badge-warning": "#5a4900",
        "badge-info": "#003a5a",
        "L_ink": "#000000",
        "L_ink-soft": "#1a1a1a",
        "L_paper": "#ffffff",
        "L_paper-2": "#f2f2f2",
        "L_green": "#0a4420",
        "L_rust": "#7a1f00",
        "L_pine": "#000000",
        "L_pine-2": "#111111",
        "L_on-pine": "#ffffff",
        "L_amber": "#ffce6a",
    },
}


def resolve(token: str, theme: dict[str, str]) -> str:
    if token.startswith("#"):
        return token
    return theme[token]


def main() -> int:
    fails: list[str] = []
    for theme_name, theme in THEMES.items():
        print(f"\n=== theme: {theme_name} ===")
        for label, fg, bg, large in PAIRS:
            try:
                fgh, bgh = resolve(fg, theme), resolve(bg, theme)
            except KeyError:
                # Pair uses a token a theme doesn't define; skip it cleanly.
                continue
            r = ratio(fgh, bgh)
            need = 4.5 if large else 7.0
            ok = r >= need
            if not ok:
                fails.append(f"[{theme_name}] {label} ({r:.2f} < {need})")
            print(f"{'OK ' if ok else 'FAIL'} {r:5.2f} (need {need}) {label}  [{fgh} on {bgh}]")
    print()
    if fails:
        print(f"{len(fails)} FAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    print("All pairs pass AAA thresholds across every theme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
