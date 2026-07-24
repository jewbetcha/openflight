from __future__ import annotations

import sys
from pathlib import Path


def replace_footprint_blocks(text: str) -> tuple[str, int]:
    output: list[str] = []
    index = 0
    changed = 0
    marker = '\n\t(footprint "TestPoint_Pad_D1.5mm"'

    while True:
        start = text.find(marker, index)
        if start < 0:
            output.append(text[index:])
            break

        output.append(text[index:start])
        block_start = start + 1
        depth = 0
        block_end = None
        for pos in range(block_start, len(text)):
            char = text[pos]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    block_end = pos + 1
                    break
        if block_end is None:
            raise RuntimeError("unterminated TestPoint footprint block")

        block = text[block_start:block_end]
        new_block = block.replace("(end 0 0.95)", "(end 0 0.85)")
        new_block = new_block.replace("(end 1.25 0)", "(end 0.9 0)")
        if new_block != block:
            changed += 1
        output.append(new_block)
        index = block_end

    return "".join(output), changed


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: shrink_testpoint_graphics.py <board.kicad_pcb>", file=sys.stderr)
        return 2

    board = Path(sys.argv[1])
    text, changed = replace_footprint_blocks(board.read_text())
    if changed < 1:
        raise RuntimeError("no test point footprints changed")
    board.write_text(text)
    print(f"updated {changed} testpoint footprints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
