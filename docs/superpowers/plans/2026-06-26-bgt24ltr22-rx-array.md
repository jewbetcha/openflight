# BGT24LTR22 RX Array Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable Rev B1 Gerber package for a two-chip Infineon BGT24LTR22 24 GHz RX array prototype.

**Architecture:** Generate Gerber/Excellon files from a checked-in Node.js generator instead of hand-editing fabrication outputs. The generated package is labeled for PCB fab and assembly review, with clear caveats around WLCSP footprint validation, RF simulation, and ADC selection.

**Tech Stack:** Node.js ESM generator, RS-274X Gerber output, Excellon drill output, Markdown documentation.

---

### Task 1: Design Documentation

**Files:**
- Create: `docs/superpowers/specs/2026-06-26-bgt24ltr22-rx-array-design.md`
- Create: `docs/superpowers/plans/2026-06-26-bgt24ltr22-rx-array.md`

- [x] **Step 1: Record Rev B1 scope**

Document that Rev B1 contains four RX patches, two BGT24LTR22 footprints, two TX/sync patches, RF routing, control breakouts, and differential IF breakouts.

- [x] **Step 2: Record Rev B1 exclusions**

Document that Rev B1 does not include a selected ADC, Pi data interface, verified regulator design, EM simulation, or VNA validation.

### Task 2: Gerber Generator

**Files:**
- Create: `hardware/24ghz-bgt24ltr22-rx-array-rev-b1/generate_gerbers.mjs`
- Create: `hardware/24ghz-bgt24ltr22-rx-array-rev-b1/README.md`
- Create: `hardware/24ghz-bgt24ltr22-rx-array-rev-b1/fabrication-notes.md`

- [x] **Step 1: Create generator**

Create a Node.js generator that emits top copper, inner ground, inner support,
bottom copper, soldermask, paste, silkscreen, edge cuts, drill files, and a
manifest.

- [x] **Step 2: Create package docs**

Create README and fabrication notes that explain the prototype status, stackup
assumptions, assembly risks, and review requirements.

### Task 3: Generation And Checks

**Files:**
- Generate: `hardware/24ghz-bgt24ltr22-rx-array-rev-b1/gerbers/*`
- Generate: `hardware/24ghz-bgt24ltr22-rx-array-rev-b1/openflight-24ghz-bgt24ltr22-rx-array-rev-b1-gerbers.zip`

- [x] **Step 1: Generate files**

Run:

```bash
node hardware/24ghz-bgt24ltr22-rx-array-rev-b1/generate_gerbers.mjs
```

Expected: generator writes Gerber, drill, and manifest files into the Rev B1
`gerbers/` directory.

- [x] **Step 2: Create zip**

Run:

```bash
zip -j -q hardware/24ghz-bgt24ltr22-rx-array-rev-b1/openflight-24ghz-bgt24ltr22-rx-array-rev-b1-gerbers.zip hardware/24ghz-bgt24ltr22-rx-array-rev-b1/gerbers/*
```

Expected: zip file contains every generated fabrication artifact.

- [x] **Step 3: Sanity-check generated output**

Run a local Node.js check that confirms Gerber files end in `M02*`, drill files
end in `M30`, the manifest is valid JSON, and the zip contains the generated
files.
