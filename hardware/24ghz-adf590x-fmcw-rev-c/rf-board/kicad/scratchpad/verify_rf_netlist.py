from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

EXPECTED_COMPONENT_COUNT = 98

EXPECTED_COMPONENT_FIELDS = {
    "C1": {"value": "4.7uF", "footprint": "Capacitor_SMD:C_0603_1608Metric"},
    **{
        f"C{index}": {"value": "1uF", "footprint": "Capacitor_SMD:C_0603_1608Metric"}
        for index in range(2, 8)
    },
    "C31": {"value": "22uF", "footprint": "Capacitor_SMD:C_0805_2012Metric"},
    "C33": {"value": "220pF", "footprint": "Capacitor_SMD:C_0402_1005Metric"},
    "C34": {"value": "3.3nF", "footprint": "Capacitor_SMD:C_0402_1005Metric"},
    "C35": {"value": "47pF", "footprint": "Capacitor_SMD:C_0402_1005Metric"},
    "C50": {
        "value": "100nF",
        "MPN": "550L104KTT",
        "Manufacturer": "KYOCERA AVX",
    },
    "C52": {
        "value": "100nF",
        "MPN": "550L104KTT",
        "Manufacturer": "KYOCERA AVX",
    },
    "C53": {
        "value": "10pF",
        "MPN": "0201ZK100FBSTR",
        "Manufacturer": "KYOCERA AVX",
    },
    **{
        f"C{index}": {
            "value": "100nF",
            "MPN": "550L104KTT",
            "Manufacturer": "KYOCERA AVX",
        }
        for index in range(70, 75)
    },
    "D1": {"value": "MBR0520LT1G", "footprint": "Diode_SMD:D_SOD-123"},
    "FB1": {"value": "470R@100MHz", "footprint": "Inductor_SMD:L_0603_1608Metric"},
    "J1": {"MPN": "FTSH-115-01-L-DV-K", "Manufacturer": "Samtec"},
    "R21": {"value": "510", "footprint": "Resistor_SMD:R_0402_1005Metric"},
    "R22": {"value": "620", "footprint": "Resistor_SMD:R_0402_1005Metric"},
}

EXPECTED_NETS = {
    "+5V": {"FB1.1", "J1.1", "J1.2"},
    "BB1_P": {"C75.2", "J1.5", "R60.1"},
    "BB1_N": {"C76.2", "J1.6", "R61.1"},
    "BB2_P": {"C77.2", "J1.9", "R62.1"},
    "BB2_N": {"C78.2", "J1.10", "R63.1"},
    "BB3_P": {"C79.2", "J1.13", "R64.1"},
    "BB3_N": {"C80.2", "J1.14", "R65.1"},
    "BB4_P": {"C81.2", "J1.17", "R66.1"},
    "BB4_N": {"C82.2", "J1.18", "R67.1"},
    "CE_RX": {"J1.28", "U6.13", "U7.7"},
    "LE_4159": {"J1.27", "U7.6"},
    "LE_5901": {"J1.25", "U5.23"},
    "LE_5904": {"J1.26", "U6.10"},
    "LO_OUT": {"C52.1", "C74.1"},
    "Net-(U4-CE)": {"U4.13", "U7.10"},
    "Net-(U4-CLK)": {"U4.14", "U7.13"},
    "Net-(U4-DATA)": {"U4.15", "U7.12"},
    "Net-(U4-LE)": {"U4.16", "U7.11"},
    "Net-(U4-MUXOUT)": {"U4.17", "U8.5"},
    "Net-(U5-VREG)": {"C58.2", "U5.18"},
    "RAMP_SYNC": {"J1.30", "U8.8"},
    "REFIN": {"C30.1", "U4.9", "U5.15"},
    "RFIN_DIV": {"C37.1", "C53.1"},
    "RX1": {"C70.1"},
    "RX2": {"C71.1"},
    "RX3": {"C72.1"},
    "RX4": {"C73.1"},
    "SPI_SCLK": {"J1.21", "U5.21", "U6.11", "U7.4"},
    "SPI_SDATA": {"J1.22", "U5.22", "U6.12", "U7.5"},
    "SPI_SDO": {"J1.23", "U6.14"},
    "TX_ANT": {"C50.1"},
    "TX_EN": {"J1.29", "U5.20"},
    "VTUNE": {"R23.1", "U5.29"},
}

EXPECTED_PIN_NETS = {
    "J1.1": "+5V",
    "J1.2": "+5V",
    "J1.3": "GND",
    "J1.4": "GND",
    "J1.5": "BB1_P",
    "J1.6": "BB1_N",
    "J1.7": "GND",
    "J1.8": "GND",
    "J1.9": "BB2_P",
    "J1.10": "BB2_N",
    "J1.11": "GND",
    "J1.12": "GND",
    "J1.13": "BB3_P",
    "J1.14": "BB3_N",
    "J1.15": "GND",
    "J1.16": "GND",
    "J1.17": "BB4_P",
    "J1.18": "BB4_N",
    "J1.19": "GND",
    "J1.20": "GND",
    "J1.21": "SPI_SCLK",
    "J1.22": "SPI_SDATA",
    "J1.23": "SPI_SDO",
    "J1.24": "GND",
    "J1.25": "LE_5901",
    "J1.26": "LE_5904",
    "J1.27": "LE_4159",
    "J1.28": "CE_RX",
    "J1.29": "TX_EN",
    "J1.30": "RAMP_SYNC",
    "U4.1": "GND",
    "U4.2": "GND",
    "U4.3": "GND",
    "U4.4": "Net-(U4-RFinB)",
    "U4.5": "Net-(U4-RFinA)",
    "U4.6": "+3V3_RX",
    "U4.7": "+3V3_RX",
    "U4.8": "+3V3_RX",
    "U4.9": "REFIN",
    "U4.10": "GND",
    "U4.11": "GND",
    "U4.12": "GND",
    "U4.13": "Net-(U4-CE)",
    "U4.14": "Net-(U4-CLK)",
    "U4.15": "Net-(U4-DATA)",
    "U4.16": "Net-(U4-LE)",
    "U4.17": "Net-(U4-MUXOUT)",
    "U4.18": "+1V8_DIG",
    "U4.19": "+1V8_DIG",
    "U4.20": "unconnected-(U4-SW1-Pad20)",
    "U4.21": "unconnected-(U4-SW2-Pad21)",
    "U4.22": "+3V3_RX",
    "U4.23": "Net-(U4-RSET)",
    "U4.24": "Net-(U4-CP)",
    "U4.25": "GND",
    "U7.1": "+3V3_RX",
    "U7.2": "+3V3_RX",
    "U7.3": "+3V3_RX",
    "U7.4": "SPI_SCLK",
    "U7.5": "SPI_SDATA",
    "U7.6": "LE_4159",
    "U7.7": "CE_RX",
    "U7.8": "GND",
    "U7.9": "GND",
    "U7.10": "Net-(U4-CE)",
    "U7.11": "Net-(U4-LE)",
    "U7.12": "Net-(U4-DATA)",
    "U7.13": "Net-(U4-CLK)",
    "U7.14": "GND",
    "U7.15": "GND",
    "U7.16": "+1V8_DIG",
    "U8.1": "GND",
    "U8.2": "GND",
    "U8.3": "GND",
    "U8.4": "GND",
    "U8.5": "Net-(U4-MUXOUT)",
    "U8.6": "+1V8_DIG",
    "U8.7": "+3V3_RX",
    "U8.8": "RAMP_SYNC",
    "U8.9": "unconnected-(U8-A2-Pad9)",
    "U8.10": "GND",
}

EXPECTED_POWER_SUBSETS = {
    "+1V8_DIG": {"U3.5", "U4.18", "U4.19", "U7.16", "U8.6"},
    "+3V3_RX": {
        "U2.1",
        "U2.2",
        "U4.6",
        "U4.7",
        "U4.8",
        "U4.22",
        "U6.4",
        "U6.21",
        "U6.27",
        "U7.1",
        "U8.7",
    },
    "+3V3_TX": {"U1.1", "U1.2", "U5.4", "U5.5", "U5.14", "U5.16", "U5.17", "U5.30"},
    "GND": {
        "C58.1",
        "U1.3",
        "U1.6",
        "U1.9",
        "U2.3",
        "U2.6",
        "U2.9",
        "U3.2",
        "U4.25",
        "U5.33",
        "U6.33",
    },
}


def node_name(node: ET.Element) -> str:
    return f"{node.get('ref')}.{node.get('pin')}"


def require_same_net(pin_to_net: dict[str, str], *pins: str) -> None:
    net_names = {pin_to_net.get(pin) for pin in pins}
    if len(net_names) != 1 or None in net_names:
        assignments = {pin: pin_to_net.get(pin) for pin in pins}
        raise RuntimeError(f"pins must share one net: {assignments}")


def main() -> int:
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent / "openflight-24ghz-fmcw-rf-rev-c.xml"
    )
    root = ET.parse(path).getroot()
    components = root.findall("./components/comp")
    references = [component.get("ref", "") for component in components]

    if len(components) != EXPECTED_COMPONENT_COUNT:
        raise RuntimeError(
            f"expected {EXPECTED_COMPONENT_COUNT} components, found {len(components)}"
        )
    duplicates = sorted(reference for reference, count in Counter(references).items() if count > 1)
    if duplicates:
        raise RuntimeError(f"duplicate component references: {duplicates}")
    missing_footprints = sorted(
        component.get("ref", "")
        for component in components
        if not (component.findtext("footprint") or "").strip()
    )
    if missing_footprints:
        raise RuntimeError(f"components missing footprints: {missing_footprints}")

    components_by_ref = {component.get("ref", ""): component for component in components}
    for reference, expected_fields in EXPECTED_COMPONENT_FIELDS.items():
        component = components_by_ref[reference]
        fields = {
            "value": component.findtext("value", ""),
            "footprint": component.findtext("footprint", ""),
            **{
                field.get("name", ""): field.text or ""
                for field in component.findall("./fields/field")
            },
        }
        for name, expected in expected_fields.items():
            if fields.get(name) != expected:
                raise RuntimeError(
                    f"{reference} {name}: expected {expected}, found {fields.get(name)}"
                )

    nets: dict[str, set[str]] = {}
    pin_to_net: dict[str, str] = {}
    for net in root.findall("./nets/net"):
        name = net.get("name", "")
        nodes = {node_name(node) for node in net.findall("node")}
        nets[name] = nodes
        for node in nodes:
            if node in pin_to_net:
                raise RuntimeError(f"pin {node} appears on both {pin_to_net[node]} and {name}")
            pin_to_net[node] = name

    for name, expected in EXPECTED_NETS.items():
        actual = nets.get(name)
        if actual != expected:
            raise RuntimeError(
                f"net {name}: expected {sorted(expected)}, found {sorted(actual or set())}"
            )

    for name, expected in EXPECTED_POWER_SUBSETS.items():
        actual = nets.get(name, set())
        missing = expected - actual
        if missing:
            raise RuntimeError(f"net {name}: missing critical nodes {sorted(missing)}")

    for pin, expected_net in EXPECTED_PIN_NETS.items():
        actual_net = pin_to_net.get(pin)
        if actual_net != expected_net:
            raise RuntimeError(f"pin {pin}: expected {expected_net}, found {actual_net}")

    # ADI UG-866 Figure 12 passive loop filter. The previous ladder topology
    # used the right values but connected them in the wrong circuit.
    require_same_net(pin_to_net, "U4.24", "C33.1", "C34.1", "R21.2")
    require_same_net(pin_to_net, "C34.2", "R22.1")
    require_same_net(pin_to_net, "R21.1", "C35.1", "R23.2")
    require_same_net(pin_to_net, "C33.2", "R22.2", "C35.2", "U4.25")

    print(
        f"PASS: {len(components)} components, {len(nets)} nets, connector and critical RF/power nets verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
