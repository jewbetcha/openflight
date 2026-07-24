import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "hardware"
    / "24ghz-adf590x-fmcw-rev-c"
    / "adc-board"
    / "kicad"
    / "scratchpad"
    / "generate_adc_pcbway_package.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("revc_adc_pcbway", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bom_excludes_dnp_and_testpads_and_fills_passive_mpn(tmp_path):
    netlist = tmp_path / "netlist.xml"
    overrides = tmp_path / "parts.json"
    netlist.write_text(
        """<export><components>
        <comp ref="C1"><value>100nF</value><footprint>Capacitor_SMD:C_0402_1005Metric</footprint><fields><field name="Description">Bypass</field></fields></comp>
        <comp ref="C2"><value>82pF</value><footprint>Capacitor_SMD:C_0402_1005Metric</footprint><property name="dnp"/><fields/></comp>
        <comp ref="TP1"><value>TP</value><footprint>TestPoint:Pad</footprint><fields/></comp>
        </components></export>""",
        encoding="utf-8",
    )
    overrides.write_text(
        json.dumps(
            {
                "100nF|Capacitor_SMD:C_0402_1005Metric": {
                    "mpn": "CAP-100N",
                    "manufacturer": "Parts Inc",
                }
            }
        ),
        encoding="utf-8",
    )

    rows, references = load_module().populated_parts(netlist, overrides)

    assert references == {"C1"}
    assert rows[0]["MPN"] == "CAP-100N"


def test_cpl_requires_exact_populated_reference_set(tmp_path):
    source = tmp_path / "all.csv"
    output = tmp_path / "filtered.csv"
    source.write_text(
        "Ref,Val,Package,PosX,PosY,Rot,Side\nC1,1u,C,1,2,0,top\nTP1,TP,TP,3,4,0,top\n",
        encoding="utf-8",
    )

    count = load_module().filter_cpl(source, output, {"C1"})
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert count == 1
    assert [row["Ref"] for row in rows] == ["C1"]
