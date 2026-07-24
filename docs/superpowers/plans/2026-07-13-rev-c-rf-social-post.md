# Rev C RF Social Post Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a verified five-slide social carousel and post script for the OpenFlight Rev C RF board.

**Architecture:** A self-contained Python generator writes deterministic 1080x1350 SVG masters and embeds the approved Rev C board render as a PNG data URI. ImageMagick rasterizes the SVG files and creates a contact sheet; focused tests verify source provenance, dimensions, required wording, and absence of Rev B2 references.

**Tech Stack:** Python standard library via `uv`, SVG, ImageMagick CLI, pytest, ZIP.

---

## File Structure

- Create `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/generate_rf_post_a.py`: SVG and README generator.
- Create `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/test_generate_rf_post_a.py`: source and output contract tests.
- Generate five SVG masters and five PNG exports in the same directory.
- Generate `contact-sheet.png`, `README.md`, and `rf-post-a-social-assets.zip` in the same directory.

### Task 1: Lock The Output Contract With Tests

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/test_generate_rf_post_a.py`

- [ ] **Step 1: Write the source-provenance and slide-contract tests**

The tests load `generate_rf_post_a.py`, assert the approved board SHA-256 is
`ce9c3cd593b33a25cf4dd3fee94eba4b2d38e841869227ecfe81fef59edd97f1`,
render into a temporary directory, and verify five SVG files with a 1080x1350
viewBox. They also assert that every SVG excludes `rev b2`, slide 5 includes
`automatic upload`, and the README includes `design-review package`.

- [ ] **Step 2: Run the tests and verify they fail before implementation**

Run:

```bash
uv run pytest hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/test_generate_rf_post_a.py -v
```

Expected: failure because `generate_rf_post_a.py` does not exist.

### Task 2: Implement The SVG And Copy Generator

**Files:**
- Create: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/generate_rf_post_a.py`
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/01-rf-board.svg`
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/02-send-and-listen.svg`
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/03-four-ears.svg`
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/04-main-components.svg`
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/05-design-review.svg`
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/README.md`

- [ ] **Step 1: Implement deterministic source loading**

Use `Path`, `hashlib.sha256`, and `base64.b64encode`. Abort with a clear error
if the authoritative render hash differs from the approved value. Embed the
image as `data:image/png;base64,...` so the SVG files remain portable.

- [ ] **Step 2: Implement shared SVG helpers**

Implement `text_block()`, `shell()`, `footer()`, `board_image()`, primitive
diagram helpers, and `render_all(out_dir)`. Keep each slide renderer focused on
one approved storyboard item.

- [ ] **Step 3: Implement the five approved slides**

Render the exact content from
`docs/superpowers/specs/2026-07-13-rev-c-rf-social-post-design.md`. Slide 5 must
say the upload passed PCBWay's automatic fabrication check while explicitly
keeping stackup confirmation and RF validation open.

- [ ] **Step 4: Generate the README and post script**

Include the storyboard, plain-language bullet script, caption draft, source
path/hash, current limitations, and exact regeneration commands.

- [ ] **Step 5: Run generator and tests**

Run:

```bash
uv run python hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/generate_rf_post_a.py
uv run pytest hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/test_generate_rf_post_a.py -v
```

Expected: five SVG files generated and all tests pass.

### Task 3: Rasterize, Package, And Visually Verify

**Files:**
- Generate: five corresponding PNG files.
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/contact-sheet.png`
- Generate: `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/rf-post-a-social-assets.zip`

- [ ] **Step 1: Rasterize every SVG at native dimensions**

Run ImageMagick once per slide using `magick <slide>.svg <slide>.png`.

- [ ] **Step 2: Build the five-up contact sheet**

Run:

```bash
magick montage hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/0*.png -thumbnail 270x337 -tile 5x1 -geometry +12+12 -background '#0b1017' hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/contact-sheet.png
```

- [ ] **Step 3: Verify image dimensions and nonblank output**

Use `magick identify` to confirm every slide is 1080x1350 and inspect image
statistics to ensure the board and diagram regions are nonblank.

- [ ] **Step 4: Inspect all slides visually**

Open the contact sheet and individual slides. Confirm the board is the Rev C
layout, labels point to the correct regions, text is readable, and nothing is
clipped or overlapping.

- [ ] **Step 5: Package shareable files**

Create `rf-post-a-social-assets.zip` containing the five PNG files and README.
Do not include generated caches or the test file.

- [ ] **Step 6: Run final verification**

Re-run the focused pytest file and `magick identify`. Report exact output paths
and any remaining visual limitations.

## Repository Note

The project preference is no agent-created commits, so this plan intentionally
omits commit steps even though the generic planning workflow recommends them.
