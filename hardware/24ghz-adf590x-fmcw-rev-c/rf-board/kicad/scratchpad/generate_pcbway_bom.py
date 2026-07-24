#!/usr/bin/env python3
"""Generate a PCBWay review BOM from the KiCad schematic analysis JSON."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = (
    "Line#",
    "Qty",
    "Designator",
    "MPN",
    "Manufacturer",
    "Description",
    "Package",
    "Type",
)


def assembly_type(footprint: str) -> str:
    package = footprint.rsplit(":", 1)[-1].upper()
    through_hole_markers = ("THT", "THROUGHHOLE", "THROUGH_HOLE")
    return "THT" if any(marker in package for marker in through_hole_markers) else "SMD"


def generate_bom(
    analysis_path: Path,
    output_path: Path,
    *,
    parts_override_path: Path | None = None,
) -> tuple[int, int, set[str]]:
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    bom = analysis.get("bom", [])
    overrides = (
        json.loads(parts_override_path.read_text(encoding="utf-8"))
        if parts_override_path
        else {}
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    populated_mpn_rows = 0
    assembly_references: set[str] = set()
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for line_number, part in enumerate(bom, start=1):
            footprint = part.get("footprint", "")
            override = overrides.get(f"{part.get('value', '')}|{footprint}", {})
            mpn = part.get("mpn", "") or override.get("mpn", "")
            manufacturer = part.get("manufacturer", "") or override.get(
                "manufacturer", ""
            )
            references = part.get("references", [])
            assembly_references.update(references)
            if mpn:
                populated_mpn_rows += 1
            writer.writerow(
                {
                    "Line#": line_number,
                    "Qty": part.get("quantity", 0),
                    "Designator": ",".join(references),
                    "MPN": mpn,
                    "Manufacturer": manufacturer,
                    "Description": part.get("description") or part.get("value", ""),
                    "Package": footprint.rsplit(":", 1)[-1],
                    "Type": assembly_type(footprint),
                }
            )

    return len(bom), populated_mpn_rows, assembly_references


def filter_cpl(input_path: Path, output_path: Path, references: set[str]) -> int:
    with input_path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = [row for row in reader if row.get("Ref") in references]
        fieldnames = reader.fieldnames

    if not fieldnames:
        raise ValueError(f"CPL has no header: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cpl-input", type=Path)
    parser.add_argument("--cpl-output", type=Path)
    parser.add_argument("--parts-override", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    row_count, populated_mpn_rows, references = generate_bom(
        args.analysis,
        args.output,
        parts_override_path=args.parts_override,
    )
    print(
        f"Wrote {row_count} BOM rows to {args.output}; "
        f"{populated_mpn_rows}/{row_count} rows have MPNs"
    )
    if args.require_complete and populated_mpn_rows != row_count:
        raise RuntimeError(
            f"BOM MPN coverage incomplete: {populated_mpn_rows}/{row_count} rows"
        )
    if bool(args.cpl_input) != bool(args.cpl_output):
        parser.error("--cpl-input and --cpl-output must be provided together")
    if args.cpl_input and args.cpl_output:
        placement_count = filter_cpl(args.cpl_input, args.cpl_output, references)
        print(f"Wrote {placement_count} placements to {args.cpl_output}")


if __name__ == "__main__":
    main()
