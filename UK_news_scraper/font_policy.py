from __future__ import annotations

import sys


ENGLISH_FONT = "Times New Roman"
# macOS ships BiauKaiTC as 標楷體-繁; Windows uses DFKai-SB.
CHINESE_FONT = "BiauKaiTC" if sys.platform == "darwin" else "DFKai-SB"


def _is_chinese_character(char: str) -> bool:
    code = ord(char)
    return (
        0x2E80 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2FA1F
        or 0xFF00 <= code <= 0xFFEF
    )


def language_runs(value: str) -> list[tuple[str, str]]:
    """Split mixed text into font runs without changing its visible contents."""
    runs: list[tuple[str, list[str]]] = []
    for char in value:
        is_chinese = _is_chinese_character(char)
        font = CHINESE_FONT if is_chinese else ENGLISH_FONT
        if not char.isalnum() and not is_chinese and runs:
            font = runs[-1][0]
        if runs and runs[-1][0] == font:
            runs[-1][1].append(char)
        else:
            runs.append((font, [char]))
    return [(font, "".join(chars)) for font, chars in runs]
