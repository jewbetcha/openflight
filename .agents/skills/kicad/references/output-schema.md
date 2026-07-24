# Analyzer JSON Output Schema

Quick reference for the JSON output of the three analysis scripts. Use `--schema` on any script for the authoritative, always-in-sync version. This document provides additional context and common extraction patterns.

## analyze_schematic.py

| Key | Type | Description |
|-----|------|-------------|
| `analyzer_type` | string | Always `"schematic"` |
| `schema_version` | string | Semver (currently `"1.3.0"`) |
| `summary` | object | `{total_findings: int, by_severity: {error, warning, info}}` |
| `trust_summary` | object | Trust posture (see below) |
| `findings` | array | All findings — subcircuit detections, validation checks, design observations (see below) |
| `file` | string | Input file path |
| `kicad_version` | string | Generator version |
| `file_version` | string | KiCad file format version |
| `title_block` | object | `{title, date, rev, company, comments: {n: string}}` |
| `statistics` | object | Counts and summaries (see below) |
| `bom` | array | Deduplicated BOM with quantities |
| `components` | array | Every component with full properties |
| `nets` | object | Net connectivity map keyed by net name |
| `subcircuits` | array | Hierarchical sub-sheets |
| `ic_pin_analysis` | array | Per-IC pin mapping (list of IC records) |
| `rail_voltages` | object | `{net_name: voltage_float}` — auto-detected from regulator outputs and power symbol names |
| `net_classifications` | object | Per-net class (power/data/analog/output_drive/etc.) |
| `design_analysis` | object | Buses, power domains, ERC warnings |
| `connectivity_issues` | object | Single-pin nets, multi-driver nets, floating nets |

### trust_summary

```
total_findings: int,
trust_level: "high" | "mixed" | "low",
by_confidence: {deterministic: int, heuristic: int, "datasheet-backed": int},
by_evidence_source: {datasheet|topology|heuristic_rule|symbol_footprint|bom|geometry|api_lookup: int},
provenance_coverage_pct: float,
bom_coverage: {mpn_pct: float, datasheet_pct: float}  // schematic only
```

Emitted by all 6 analyzers (schematic, PCB, gerber, thermal, EMC, cross_analysis).

### statistics

```
total_components: int, unique_parts: int, dnp_parts: int,
total_nets: int, total_wires: int, total_no_connects: int,
component_types: {type_name: count},
power_rails: [string],
missing_mpn: [reference], missing_footprint: [reference]
```

### bom entries

```
{value, footprint, mpn, manufacturer, digikey, mouser, lcsc, element14,
 datasheet, description, references: [string], quantity: int, dnp: bool, type}
```

### components entries

```
{reference, value, lib_id, footprint, datasheet, description,
 mpn, manufacturer, digikey, mouser, lcsc, element14,
 x: float, y: float, angle: float, mirror_x: bool, mirror_y: bool,
 unit: int|null, uuid, in_bom: bool, dnp: bool, on_board: bool,
 type, keywords, pins: [{number, name, type}],
 parsed_value: {value: float, unit: string}}
```

### nets entries

Keyed by net name:
```
{name, pins: [{component, pin_number, pin_name, pin_type}], point_count: int}
```

### findings entries

All subcircuit detections, validation checks, and design observations are in the flat `findings[]` array. Each finding has a common envelope:

```
{detector, rule_id, category, severity, confidence, summary, recommendation,
 evidence_source, fix_params, report_context, ...detector-specific fields}
```

Use `detector` to filter by type. The `finding_schema.py` module provides `get_findings(data, detector)` and `group_findings(data)` helpers, plus `Det` constants for all detector names. `group_findings_legacy(data)` reconstructs the old dict-of-lists layout — it remains for backward compatibility but is scheduled for removal in v1.4 alongside the consumer rewrite of `what_if.py` and `diff_analysis.py`.

**Detector types and their key fields:**

| Detector | Key Fields |
|----------|------------|
| `voltage_dividers` | `top_ref, bottom_ref, ratio, estimated_vout, input_net, output_net` |
| `rc_filters` | `resistor, capacitor, cutoff_frequency_hz, type: lowpass\|highpass` |
| `lc_filters` | `inductor, capacitors, resonant_formatted` |
| `power_regulators` | `ref, value, lib_id, topology, input_rail, output_rail, estimated_vout, vref_source` |
| `crystal_circuits` | `reference, value, frequency, type: passive\|active_oscillator, load_caps` |
| `opamp_circuits` | `reference, configuration, gain` |
| `transistor_circuits` | `reference, type, load_classification` |
| `bridge_circuits` | `topology, fet_refs` |
| `protection_devices` | `type, reference, protected_net` |
| `current_sense` | `shunt: {ref, value, ohms}, sense_ic: {ref, value, type}, high_net, low_net, max_current_50mV_A, max_current_100mV_A` |
| `decoupling` | `capacitor_ref, ic_ref, distance` |
| `rf_matching` | `antenna, topology: pi_match\|L_match\|T_match, components: [{ref, type, value}], target_ic` |
| `key_matrices` | `rows, cols, diodes` |
| `isolation_barriers` | `isolator_ref, side_a_nets, side_b_nets` |
| `ethernet_interfaces` | `phy_ref, magnetics_ref, connector_ref` |
| `memory_interfaces` | `type, bus_signals` |
| `rf_chains` | `components_in_chain` |
| `bms_systems` | `ic_ref, cell_count` |
| `battery_chargers` | `ref, value, charger_type, charge_current` |
| `motor_drivers` | `ref, value, driver_type: stepper\|dc_brushed_h_bridge` |
| `esd_coverage_audit` | `connector_ref, interface_type, risk_level, coverage: full\|partial\|none, unprotected_nets` |
| `debug_interfaces` | `connector_ref, interface_type: swd\|jtag, pins_found, target_ic, status` |
| `power_path` | `ref, type: load_switch\|ideal_diode\|power_mux\|usb_pd_controller, input_rail, output_rail, enable_net` |
| `adc_circuits` | `ref, type: external_adc\|voltage_reference, resolution_bits, interface, input_channels, vref_source` |
| `reset_supervisors` | `ref, type: voltage_supervisor\|watchdog\|rc_reset, monitored_rail, threshold_voltage, target_ic` |
| `clock_distribution` | `ref, type: clock_generator\|pll\|oscillator_output, outputs, consumers, series_termination` |
| `display_interfaces` | `ref, type: display\|touch_controller, display_type, interface, backlight` |
| `sensor_interfaces` | `ref, type: motion\|environmental\|magnetic, interface, interrupt_pins, bus_peers` |
| `level_shifters` | `ref, type: level_shifter_ic\|discrete_level_shifter, side_a, side_b, shifted_nets` |
| `audio_circuits` | `ref, type: audio_amplifier\|audio_codec, amplifier_class, interface, output_nets` |
| `led_driver_ics` | `ref, type: pwm_led_driver\|matrix_led_driver\|constant_current_led_driver, channels, current_set` |
| `rtc_circuits` | `ref, type: rtc, interface, has_internal_oscillator, external_crystal, battery_backup` |
| `led_audit` | `ref, drive_method: resistor_limited\|direct_drive\|ic_direct, series_resistor, estimated_current_mA` |
| `thermocouple_rtd` | `ref, type: thermocouple_amplifier\|rtd_interface, interface, reference_resistor` |
| `power_sequencing_validation` | `power_tree, enable_chains, issues` |

### design_analysis

```
net_classification: {net: {type: 'power'|'ground'|'data'|...}}
power_domains: {ic_power_rails: {ref: {voltage, rail_net}}, ...}
cross_domain_signals: [signals crossing voltage domains]
bus_analysis: {i2c|spi|uart|can|sdio|usb: [bus_instances]}
differential_pairs: [{positive, negative, type, shared_ics, has_esd, ...}]
erc_warnings: [string]
passive_warnings: [string]
```

### Optional sections (included when applicable)

`power_budget`, `power_sequencing`, `pdn_impedance`, `sleep_current_audit`, `usb_compliance`, `inrush_analysis`, `bom_optimization`, `test_coverage`, `assembly_complexity`, `sheets` (multi-sheet only)

---

## analyze_pcb.py

| Key | Type | Description |
|-----|------|-------------|
| `analyzer_type` | string | Always `"pcb"` |
| `schema_version` | string | Semver (currently `"1.3.0"`) |
| `summary` | object | `{total_findings: int, by_severity: {error, warning, info}}` |
| `trust_summary` | object | Trust posture (see schematic section) |
| `findings` | array | All PCB findings — DFM, thermal, placement, assembly checks |
| `file` | string | Input file path |
| `kicad_version` | string | Generator version |
| `file_version` | string | Format version |
| `statistics` | object | Board-level counts and metrics |
| `layers` | array | `[{name, type, index}]` |
| `setup` | object | Design rules, clearances |
| `nets` | object | `{str(net_id): net_name}` (net-ID-keyed; use `net_name_to_id` for reverse) |
| `net_name_to_id` | object | `{net_name: int}` — reverse of `nets` |
| `board_outline` | object | Bounding box, outline type, edge segments |
| `component_groups` | object | `{prefix: {count, type, examples}}` |
| `footprints` | array | Component placements with pad-net mapping |
| `tracks` | object | Segment/arc counts, width/layer distribution |
| `vias` | object | Count, size distribution, analysis |
| `zones` | array | Copper zone definitions |
| `connectivity` | object | Routing completeness, unconnected pads |
| `net_lengths` | object | Per-net trace length, via count, layer transitions |

### statistics

```
footprint_count: int, front_side: int, back_side: int,
smd_count: int, tht_count: int, copper_layers_used: int,
copper_layer_names: [string], track_segments: int, via_count: int,
zone_count: int, total_track_length_mm: float,
board_width_mm: float|null, board_height_mm: float|null,
net_count: int, routing_complete: bool, unrouted_net_count: int
```

### footprints entries

```
{reference, value, lib_id, layer, x: float, y: float, angle: float,
 type: smd|through_hole|mixed, mpn, manufacturer, description,
 exclude_from_bom: bool, exclude_from_pos: bool, dnp: bool,
 pad_nets: {pad_number: {net, pin}}, connected_nets: [string]}
```

### tracks (--full adds segments/arcs arrays)

```
segment_count: int, arc_count: int,
width_distribution: {width_mm: count}, layer_distribution: {layer: count}
```

### vias (--full adds vias array)

```
count: int, size_distribution: {size: count}
vias (--full): [{x, y: float, layers: [string], size, drill: float,
                  net: int|null, type: 'through|blind|buried|micro'}]
via_in_pad: [{component, pad, via_x, via_y, via_drill, same_net,
              via_type: 'through|blind|buried|micro'}]
via_fanout: {ref: {via_count, fanout_traces}}
```

### Optional sections

`power_net_routing`, `decoupling_placement`, `ground_domains`, `trace_proximity` (with `--proximity`), `layer_transitions`, `silkscreen`, `board_metadata`, `dfm_summary`, `placement_density`, `copper_presence_summary`, `board_thickness_mm`. Sections previously at top level (`thermal_analysis`, `thermal_pad_vias`, `tombstoning_risk`, `placement_analysis`, `current_capacity`, `copper_presence`, `dfm`) are now flattened into `findings[]`.

---

## analyze_gerbers.py

| Key | Type | Description |
|-----|------|-------------|
| `analyzer_type` | string | Always `"gerber"` |
| `schema_version` | string | Semver (currently `"1.3.0"`) |
| `summary` | object | `{total_findings: int, by_severity: {error, warning, info}}` |
| `trust_summary` | object | Trust posture (see schematic section) |
| `findings` | array | All Gerber findings — missing layers, alignment, drill, paste, board outline |
| `directory` | string | Scan directory path |
| `generator` | string | KiCad/other/unknown |
| `layer_count` | int | Detected copper layer count |
| `board_dimensions` | object | `{x_min, x_max, y_min, y_max, width_mm, height_mm}` |
| `statistics` | object | `{gerber_files, drill_files, total_holes, total_flashes, total_draws}` |
| `completeness` | object | Expected vs found layers, coverage percent |
| `alignment` | object | Per-layer coordinate ranges for alignment check |
| `drill_classification` | object | Via/component/mounting hole breakdown |
| `pad_summary` | object | `{smd_apertures, via_apertures, component_holes, tht}` |
| `gerbers` | array | Parsed Gerber files with apertures and attributes |
| `drills` | array | Parsed drill files with tools and hole counts |

### gerbers entries

```
{file, filename, layer_type, format: {zero_omit, notation, x/y_integer, x/y_decimal},
 units: mm|inch, flash_count: int, draw_count: int, region_count: int,
 apertures: {d_code: {type, params, function}}, x2_attributes: {FileFunction, ...}}
```

### drills entries

```
{file, filename, units: mm|inch|null, type: PTH|NPTH|unknown,
 hole_count: int, coordinate_range, tools: {tool_id: {diameter_mm, hole_count}},
 x2_attributes}
```

### Optional sections

`component_analysis`, `net_analysis`, `trace_widths`, `job_file`, `zip_archives`, `connectivity` (with `--full`)

---

## Common extraction patterns

```python
import json
data = json.load(open('analysis.json'))

# Component references
[c['reference'] for c in data['components']]

# BOM summary
for b in data['bom']:
    print(f"{b['quantity']}x {b['value']} ({b['references']})")

# Power regulators with output voltage
for r in data['findings']:
    if r.get('detector') == 'power_regulators':
        print(f"{r['ref']}: {r.get('estimated_vout', '?')}V ({r['topology']})")

# Net pin list
for p in data['nets']['NET_NAME']['pins']:
    print(f"  {p['component']}.{p['pin_number']} ({p['pin_name']})")

# Footprint pad-to-net mapping
for f in data['footprints']:
    print(f"{f['reference']}: {f['pad_nets']}")

# Statistics
print(json.dumps(data['statistics'], indent=2))

# All ICs with their pin counts
for ic in data['ic_pin_analysis']:
    print(f"{ic['reference']} ({ic['value']}): {len(ic['pin_summary'])} pins — {ic['function']}")
```

**Formatting tip**: Use f-strings or `json.dumps()` for output — never `%s` or `format()` with lists or dicts, as these raise `TypeError`.
