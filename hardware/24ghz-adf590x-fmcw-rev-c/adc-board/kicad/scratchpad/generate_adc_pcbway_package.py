"""Generate the populated ADC BOM and filtered PCBWay CPL."""

from __future__ import annotations

import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


BOM_FIELDS = (
    "Line#",
    "Qty",
    "Designator",
    "MPN",
    "Manufacturer",
    "Description",
    "Package",
    "Type",
)


def natural_reference(reference: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([A-Za-z]+)(\d+)(.*)", reference)
    if not match:
        return reference, 0, ""
    return match.group(1), int(match.group(2)), match.group(3)


def fields(component: ET.Element) -> dict[str, str]:
    return {
        field.get("name", ""): field.text or ""
        for field in component.findall("./fields/field")
    }


def is_dnp(component: ET.Element) -> bool:
    return any(prop.get("name") == "dnp" for prop in component.findall("property"))


def assembly_type(footprint: str) -> str:
    name = footprint.rsplit(":", 1)[-1].upper()
    return "THT" if "PINSOCKET" in name else "SMD"


def populated_parts(
    netlist_path: Path,
    overrides_path: Path,
) -> tuple[list[dict[str, object]], set[str]]:
    root = ET.parse(netlist_path).getroot()
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)

    for component in root.findall("./components/comp"):
        reference = component.get("ref", "")
        if not reference or reference.startswith("TP") or is_dnp(component):
            continue
        value = component.findtext("value", "")
        footprint = component.findtext("footprint", "")
        component_fields = fields(component)
        override = overrides.get(f"{value}|{footprint}", {})
        mpn = component_fields.get("MPN") or override.get("mpn", "")
        manufacturer = component_fields.get("Manufacturer") or override.get(
            "manufacturer", ""
        )
        description = (
            component_fields.get("Description")
            or component.findtext("description", "")
            or value
        )
        package = footprint.rsplit(":", 1)[-1]
        key = (
            value,
            footprint,
            mpn,
            manufacturer,
            description,
            package,
            assembly_type(footprint),
        )
        groups[key].append(reference)

    rows: list[dict[str, object]] = []
    references: set[str] = set()
    for line_number, (key, refs) in enumerate(
        sorted(groups.items(), key=lambda item: natural_reference(min(item[1], key=natural_reference))),
        start=1,
    ):
        value, footprint, mpn, manufacturer, description, package, part_type = key
        del value, footprint
        refs.sort(key=natural_reference)
        references.update(refs)
        rows.append(
            {
                "Line#": line_number,
                "Qty": len(refs),
                "Designator": ",".join(refs),
                "MPN": mpn,
                "Manufacturer": manufacturer,
                "Description": description,
                "Package": package,
                "Type": part_type,
            }
        )
    return rows, references


def write_bom(rows: list[dict[str, object]], output_path: Path) -> None:
    missing = [row["Designator"] for row in rows if not row["MPN"]]
    if missing:
        raise RuntimeError(f"missing MPNs for populated rows: {missing}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=BOM_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def filter_cpl(input_path: Path, output_path: Path, references: set[str]) -> int:
    with input_path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = [row for row in reader if row.get("Ref") in references]
        fieldnames = reader.fieldnames
    if not fieldnames:
        raise RuntimeError(f"missing CPL header: {input_path}")
    found = {row["Ref"] for row in rows}
    if found != references:
        raise RuntimeError(
            f"CPL/BOM reference mismatch: missing={sorted(references - found)} "
            f"extra={sorted(found - references)}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("netlist", type=Path)
    parser.add_argument("overrides", type=Path)
    parser.add_argument("bom_output", type=Path)
    parser.add_argument("cpl_input", type=Path)
    parser.add_argument("cpl_output", type=Path)
    args = parser.parse_args()

    rows, references = populated_parts(args.netlist, args.overrides)
    write_bom(rows, args.bom_output)
    placements = filter_cpl(args.cpl_input, args.cpl_output, references)
    print(
        f"Wrote {len(rows)} fully specified BOM lines and "
        f"{placements} populated placements"
    )


if __name__ == "__main__":
    main()
