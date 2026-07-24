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
    / "rf-board"
    / "kicad"
    / "scratchpad"
    / "generate_pcbway_bom.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("revc_pcbway_bom", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parts_override_fills_missing_mpn_without_replacing_explicit_rf_part(tmp_path):
    analysis = {
        "bom": [
            {
                "value": "100nF",
                "footprint": "Capacitor_SMD:C_0402_1005Metric",
                "references": ["C1"],
                "quantity": 1,
                "mpn": "550L104KTT",
                "manufacturer": "KYOCERA AVX",
                "description": "RF block",
            },
            {
                "value": "100nF",
                "footprint": "Capacitor_SMD:C_0402_1005Metric",
                "references": ["C2"],
                "quantity": 1,
                "mpn": "",
                "manufacturer": "",
                "description": "Bypass",
            },
        ]
    }
    overrides = {
        "100nF|Capacitor_SMD:C_0402_1005Metric": {
            "mpn": "GRM155R71C104KA88D",
            "manufacturer": "Murata Electronics",
        }
    }
    analysis_path = tmp_path / "analysis.json"
    override_path = tmp_path / "parts.json"
    output_path = tmp_path / "bom.csv"
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    override_path.write_text(json.dumps(overrides), encoding="utf-8")

    rows, populated, _ = load_module().generate_bom(
        analysis_path,
        output_path,
        parts_override_path=override_path,
    )
    with output_path.open(encoding="utf-8", newline="") as source:
        output = list(csv.DictReader(source))

    assert rows == 2
    assert populated == 2
    assert output[0]["MPN"] == "550L104KTT"
    assert output[1]["MPN"] == "GRM155R71C104KA88D"
