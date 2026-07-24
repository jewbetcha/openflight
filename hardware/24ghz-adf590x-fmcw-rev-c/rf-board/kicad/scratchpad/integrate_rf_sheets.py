from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

KICAD_DIR = Path(__file__).resolve().parent.parent
ROOT = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.kicad_sch"
PROJECT = "openflight-24ghz-fmcw-rf-rev-c"
ROOT_UUID = "0f000000-0000-4000-8000-000000000001"


@dataclass(frozen=True)
class Sheet:
    filename: str
    name: str
    uuid: str
    page: int
    x: float
    expected_interface_labels: int


SHEETS = (
    Sheet(
        "pll.kicad_sch", "PLL + Ramp Generator", "0f000000-0000-4000-8000-000000002001", 2, 20, 7
    ),
    Sheet("tx.kicad_sch", "ADF5901 Transmitter", "0f000000-0000-4000-8000-000000002002", 3, 90, 8),
    Sheet("rx.kicad_sch", "ADF5904 Receiver", "0f000000-0000-4000-8000-000000002003", 4, 160, 18),
)


def sheet_block(sheet: Sheet) -> str:
    path = f"/{ROOT_UUID}/{sheet.uuid}"
    return f'''\t(sheet
\t\t(at {sheet.x} 165)
\t\t(size 60 25)
\t\t(stroke (width 0.1524) (type solid) (color 0 0 0 0))
\t\t(fill (color 0 0 0 0.0000))
\t\t(uuid "{sheet.uuid}")
\t\t(property "Sheet name" "{sheet.name}" (id 0) (at {sheet.x} 164.2884 0)
\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t)
\t\t(property "Sheet file" "{sheet.filename}" (id 1) (at {sheet.x} 190.6546 0)
\t\t\t(effects (font (size 1.27 1.27)) (justify left top))
\t\t)
\t\t(instances
\t\t\t(project "{PROJECT}"
\t\t\t\t(path "{path}" (page "{sheet.page}"))
\t\t\t)
\t\t)
\t)
'''


def globalize_interface_labels(sheet: Sheet) -> None:
    path = KICAD_DIR / sheet.filename
    text = path.read_text(encoding="utf-8")
    hierarchical_count = text.count("(hierarchical_label ")

    if hierarchical_count:
        if hierarchical_count != sheet.expected_interface_labels:
            raise RuntimeError(
                f"{sheet.filename}: expected {sheet.expected_interface_labels} hierarchical labels, "
                f"found {hierarchical_count}"
            )
        text = text.replace("(hierarchical_label ", "(global_label ")
    elif text.count("(global_label ") < sheet.expected_interface_labels:
        raise RuntimeError(
            f"{sheet.filename}: interface labels are neither hierarchical nor global"
        )

    if sheet.filename == "rx.kicad_sch":
        text = text.replace(
            'project "openflight-24ghz-fmcw-rf-rev-c-rx"',
            f'project "{PROJECT}"',
        )
        for number in range(1, 20):
            old = f'"#PWR{number:03d}"'
            new = f'"#PWR{200 + number:03d}"'
            old_count = text.count(old)
            if old_count:
                if old_count != 2:
                    raise RuntimeError(
                        f"rx.kicad_sch: expected two uses of {old}, found {old_count}"
                    )
                text = text.replace(old, new)
            elif text.count(new) != 2:
                raise RuntimeError(f"rx.kicad_sch: expected two uses of {new}")

    if sheet.filename == "pll.kicad_sch":
        for number in (*range(1, 7), *range(8, 19), *range(20, 25)):
            old = f'"#PWR{number:02d}"'
            new = f'"#PWR{100 + number:03d}"'
            old_count = text.count(old)
            if old_count:
                if old_count != 2:
                    raise RuntimeError(
                        f"pll.kicad_sch: expected two uses of {old}, found {old_count}"
                    )
                text = text.replace(old, new)
            elif text.count(new) != 2:
                raise RuntimeError(f"pll.kicad_sch: expected two uses of {new}")

    if sheet.filename == "tx.kicad_sch":
        text = text.replace(
            '"openflight-revc:C_0402"',
            '"Capacitor_SMD:C_0402_1005Metric"',
        )
        text = text.replace(
            '"openflight-revc:R_0402"',
            '"Resistor_SMD:R_0402_1005Metric"',
        )

    if sheet.filename == "rx.kicad_sch":
        for reference in [
            *(f"C{number}" for number in range(70, 92)),
            *(f"R{number}" for number in range(60, 68)),
        ]:
            marker = f'property "Reference" "{reference}"'
            start = text.find(marker)
            if start < 0 or text.find(marker, start + 1) >= 0:
                raise RuntimeError(f"rx.kicad_sch: expected one placed symbol {reference}")
            end = text.find("\n\t(symbol ", start + len(marker))
            if end < 0:
                end = len(text)
            block = text[start:end]
            footprint = (
                "Capacitor_SMD:C_0402_1005Metric"
                if reference.startswith("C")
                else "Resistor_SMD:R_0402_1005Metric"
            )
            empty = 'property "Footprint" ""'
            populated = f'property "Footprint" "{footprint}"'
            if empty in block:
                block = block.replace(empty, populated, 1)
                text = text[:start] + block + text[end:]
            elif populated not in block:
                raise RuntimeError(f"rx.kicad_sch: unexpected footprint for {reference}")

    path.write_text(text, encoding="utf-8")


def connect_reference_clock() -> None:
    tx_path = KICAD_DIR / "tx.kicad_sch"
    tx_text = tx_path.read_text(encoding="utf-8")
    local_refin = '(label "REFIN"'
    global_refin = '(global_label "REFIN"'
    if tx_text.count(local_refin) == 1:
        tx_text = tx_text.replace(local_refin, global_refin, 1)
    elif tx_text.count(global_refin) != 1:
        raise RuntimeError("tx.kicad_sch: expected exactly one local or global REFIN label")
    tx_path.write_text(tx_text, encoding="utf-8")

    pll_path = KICAD_DIR / "pll.kicad_sch"
    pll_text = pll_path.read_text(encoding="utf-8")
    if global_refin not in pll_text:
        marker = '\t(global_label "+3V3_RX" (shape input) (at 50.7 62.54 0)'
        if pll_text.count(marker) != 1:
            raise RuntimeError("pll.kicad_sch: could not locate REFIN label insertion point")
        refin_label = """\t(global_label "REFIN" (shape output) (at 41.91 52.38 270)
\t\t(effects (font (size 1.27 1.27)) (justify right))
\t\t(uuid "0f000000-0000-4000-8000-000000002101")
\t)
"""
        pll_text = pll_text.replace(marker, refin_label + marker, 1)
    elif pll_text.count(global_refin) != 1:
        raise RuntimeError("pll.kicad_sch: expected exactly one REFIN global label")
    pll_path.write_text(pll_text, encoding="utf-8")


def integrate_root() -> None:
    text = ROOT.read_text(encoding="utf-8")
    reference_map = {
        "C2I": "C2",
        "C2O": "C3",
        "C3I": "C4",
        "C3O": "C5",
        "C8I": "C6",
        "C8O": "C7",
        "R2A": "R1",
        "R3A": "R2",
    }
    for old_reference, new_reference in reference_map.items():
        old = f'"{old_reference}"'
        new = f'"{new_reference}"'
        old_count = text.count(old)
        if old_count:
            if old_count != 2:
                raise RuntimeError(f"root schematic: expected two uses of {old}, found {old_count}")
            text = text.replace(old, new)
        elif text.count(new) != 2:
            raise RuntimeError(f"root schematic: expected two uses of {new}")

    missing = [sheet for sheet in SHEETS if f'property "Sheet file" "{sheet.filename}"' not in text]
    if missing:
        if len(missing) != len(SHEETS):
            raise RuntimeError("root schematic contains only a partial RF-sheet integration")
        marker = "\n\t(sheet_instances\n"
        if text.count(marker) != 1:
            raise RuntimeError("root schematic: expected exactly one sheet_instances section")
        blocks = "\n".join(sheet_block(sheet) for sheet in SHEETS)
        text = text.replace(marker, "\n" + blocks + marker, 1)

    for sheet in SHEETS:
        if text.count(f'property "Sheet file" "{sheet.filename}"') != 1:
            raise RuntimeError(f"root schematic: invalid {sheet.filename} sheet count")
        if text.count(sheet.uuid) != 2:
            raise RuntimeError(f"root schematic: {sheet.filename} UUID/path count is not two")

    ROOT.write_text(text, encoding="utf-8")


def main() -> int:
    for sheet in SHEETS:
        globalize_interface_labels(sheet)
    connect_reference_clock()
    integrate_root()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
