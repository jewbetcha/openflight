#!/usr/bin/env python3
"""Cross-run finding summary.

Reads every analyzer output JSON in the current run (resolved from the
analysis/manifest.json), groups findings by rule_id, and prints the top
N lines sorted by (severity rank, count).

Usage:
    summarize_findings.py <analysis-dir>
    summarize_findings.py <analysis-dir> --top 10
    summarize_findings.py <analysis-dir> --severity high
    summarize_findings.py <analysis-dir> --run 2026-04-14_1939

Works cross-platform: no symlinks, paths are resolved via the manifest
and os.path.join. Python 3.8+ stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

_SEV_RANK = {"high": 0, "error": 0, "critical": 0,
             "warning": 1, "medium": 1,
             "info": 2}


def _resolve_run_dir(
        analysis_dir: str, run_override: str | None,
) -> "tuple[str, str, int]":
    """Return (run_dir_path, run_id, manifest_version)."""
    manifest_path = os.path.join(analysis_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise SystemExit(
            f"error: no manifest.json in {analysis_dir!r} — "
            "run an analyzer with --analysis-dir first")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    run_id = run_override or manifest.get("current")
    if not run_id or run_id not in manifest.get("runs", {}):
        raise SystemExit(
            f"error: manifest has no run {run_id!r}")
    path = os.path.join(analysis_dir, run_id)
    if not os.path.isdir(path):
        raise SystemExit(
            f"error: run directory missing on disk: {path!r}")
    manifest_version = int(manifest.get("version", 1))
    return path, run_id, manifest_version


def _collect_findings(run_dir: str) -> list[dict]:
    out: list[dict] = []
    for name in sorted(os.listdir(run_dir)):
        if not name.endswith(".json"):
            continue
        full = os.path.join(run_dir, name)
        try:
            with open(full, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for finding in data.get("findings", []) or []:
            if isinstance(finding, dict):
                finding.setdefault("_source_file", name)
                out.append(finding)
    return out


def _norm(s: str) -> str:
    """Normalise a severity string to one of: high, warning, info."""
    s = (s or "").lower()
    if s in ("critical", "high", "error"):
        return "high"
    if s in ("medium", "warning", "warn"):
        return "warning"
    return "info"


_KNOWN_SEVERITIES = frozenset(
    ("critical", "high", "error", "warning", "medium", "warn", "info"))


def _filter_severity(findings: list[dict], severity: str | None) -> list[dict]:
    if not severity:
        return findings
    if severity.lower() not in _KNOWN_SEVERITIES:
        raise SystemExit(
            f"error: unknown --severity {severity!r} — "
            "accepted: high/critical/error, warning/medium/warn, info")
    want = _norm(severity)
    return [f for f in findings if _norm(f.get("severity", "info")) == want]


def _aggregate(findings: list[dict]) -> list[dict]:
    groups: dict[tuple, dict] = defaultdict(
        lambda: {"rule_id": "", "severity": "info", "count": 0,
                 "examples": [], "detectors": set(), "source_files": set(),
                 "by_confidence": {"deterministic": 0, "heuristic": 0, "datasheet-backed": 0}})
    for f in findings:
        rid = f.get("rule_id") or "(unknown)"
        sev_norm = (f.get("severity") or "info").lower()
        if sev_norm in ("critical", "error"):
            sev_norm = "high"
        elif sev_norm in ("medium", "warn"):
            sev_norm = "warning"
        key = (rid, sev_norm)
        g = groups[key]
        g["rule_id"] = rid
        g["severity"] = sev_norm
        g["count"] += 1
        if len(g["examples"]) < 3:
            g["examples"].append(f.get("summary") or "")
        g["detectors"].add(f.get("detector") or "")
        g["source_files"].add(f.get("_source_file") or "")
        conf = f.get("confidence", "")
        if conf in g["by_confidence"]:
            g["by_confidence"][conf] += 1

    rows = []
    for (rid, sev), g in groups.items():
        rows.append({
            "rule_id": rid,
            "severity": sev,
            "count": g["count"],
            "detectors": sorted(x for x in g["detectors"] if x),
            "sources": sorted(x for x in g["source_files"] if x),
            "examples": g["examples"],
            "by_confidence": dict(g["by_confidence"]),
        })
    rows.sort(key=lambda r: (_SEV_RANK.get(r["severity"], 99), -r["count"], r["rule_id"]))
    return rows


def _print_table(rows: list[dict], top: int | None) -> None:
    if not rows:
        print("# No findings.")
        return
    print(f"# {len(rows)} rule groups across "
          f"{sum(r['count'] for r in rows)} findings")
    print(f"{'rule_id':<14} {'severity':<9} {'count':>5}  {'det':>4} {'heu':>4} {'ds':>3}  example")
    print("-" * 90)
    shown = rows[:top] if top else rows
    for r in shown:
        bc = r.get("by_confidence", {})
        det = bc.get("deterministic", 0)
        heu = bc.get("heuristic", 0)
        ds = bc.get("datasheet-backed", 0)
        ex = r["examples"][0][:50] if r["examples"] else ""
        print(f"{r['rule_id']:<14} {r['severity']:<9} {r['count']:>5}  {det:>4} {heu:>4} {ds:>3}  {ex}")
    if top and len(rows) > top:
        print(f"# …({len(rows) - top} more groups omitted — use --top 0 to show all)")


def _aggregate_by_confidence(findings: list[dict]) -> list[dict]:
    """Group findings by confidence level."""
    buckets: dict[str, dict] = {}
    for f in findings:
        conf = f.get("confidence", "(unknown)")
        if conf not in buckets:
            buckets[conf] = {"confidence": conf, "count": 0,
                             "top_rules": defaultdict(int),
                             "severities": {"high": 0, "warning": 0, "info": 0}}
        b = buckets[conf]
        b["count"] += 1
        rid = f.get("rule_id") or "(unknown)"
        b["top_rules"][rid] += 1
        sev_norm = _norm(f.get("severity", "info"))
        b["severities"][sev_norm] = b["severities"].get(sev_norm, 0) + 1

    rows = []
    for conf, b in sorted(buckets.items(), key=lambda x: -x[1]["count"]):
        top_rules = sorted(b["top_rules"].items(), key=lambda x: -x[1])[:3]
        rows.append({
            "confidence": conf,
            "count": b["count"],
            "severities": b["severities"],
            "top_rules": [{"rule_id": r, "count": c} for r, c in top_rules],
        })
    return rows


def _print_confidence_table(rows: list[dict]) -> None:
    if not rows:
        print("# No findings.")
        return
    total = sum(r["count"] for r in rows)
    print(f"# {total} findings by confidence level")
    print(f"{'confidence':<18} {'count':>5} {'pct':>5}  {'high':>4} {'warn':>4} {'info':>4}  top rules")
    print("-" * 90)
    for r in rows:
        pct = round(100 * r["count"] / total) if total else 0
        s = r["severities"]
        top = ", ".join(f"{t['rule_id']}({t['count']})" for t in r["top_rules"])
        print(f"{r['confidence']:<18} {r['count']:>5} {pct:>4}%  "
              f"{s.get('high',0):>4} {s.get('warning',0):>4} {s.get('info',0):>4}  {top}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("analysis_dir", help="Path to the analysis/ directory")
    ap.add_argument("--top", type=int, default=20,
                    help="Show only the top N rule groups (0 = all). "
                         "Default 20.")
    ap.add_argument("--severity",
                    help=("Filter to a single severity bucket. Accepts any "
                          "of: high/critical/error (all → high), "
                          "warning/medium/warn (→ warning), info. "
                          "Raises if the value is unrecognised."))
    ap.add_argument("--run",
                    help="Run ID override (defaults to manifest.current).")
    ap.add_argument("--json", action="store_true",
                    help="Emit the aggregated table as JSON instead of text.")
    ap.add_argument("--by-confidence", action="store_true",
                    help="Group findings by confidence level instead of rule_id.")
    args = ap.parse_args(argv)

    run_dir, run_id, manifest_version = _resolve_run_dir(args.analysis_dir, args.run)
    findings = _collect_findings(run_dir)
    findings = _filter_severity(findings, args.severity)
    if args.by_confidence:
        conf_rows = _aggregate_by_confidence(findings)
        if args.json:
            payload = {
                "schema": "summarize_findings/1",
                "run_dir": run_dir,
                "run_id": run_id,
                "manifest_version": manifest_version,
                "mode": "by_confidence",
                "rows": conf_rows,
            }
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"# Run: {run_dir}")
            _print_confidence_table(conf_rows)
        return 0

    rows = _aggregate(findings)

    if args.json:
        severity_totals: dict[str, int] = {"high": 0, "warning": 0, "info": 0}
        for r in rows:
            severity_totals[r["severity"]] = (
                severity_totals.get(r["severity"], 0) + r["count"])
        confidence_totals: dict[str, int] = {}
        for r in rows:
            for k, v in r.get("by_confidence", {}).items():
                confidence_totals[k] = confidence_totals.get(k, 0) + v
        payload = {
            "schema": "summarize_findings/1",
            "run_dir": run_dir,
            "run_id": run_id,
            "manifest_version": manifest_version,
            "totals": {
                "findings": sum(r["count"] for r in rows),
                "rule_groups": len(rows),
                "by_severity": severity_totals,
                "by_confidence": confidence_totals,
            },
            "rows": rows,
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"# Run: {run_dir}")
        top = None if args.top == 0 else args.top
        _print_table(rows, top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
