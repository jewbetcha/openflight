# Rev C RF Board Social Post Design

## Goal

Create a five-slide social carousel that introduces the OpenFlight Rev C 24 GHz
FMCW RF board in plain language. The post should explain what the board does,
how send-and-listen radar works, why four receive antennas matter, which major
components are involved, and the board's current design-review status.

## Audience And Tone

- Audience: general social followers with little or no RF background.
- Tone: direct, build-in-public, and technically honest.
- Technical depth: one concept per slide, with part numbers used only as
  secondary labels.
- The post must not imply that the board is approved for production or ready to
  order.

## Deliverables

Create `hardware/24ghz-adf590x-fmcw-rev-c/social/rf-post-a/` containing:

- Five 1080x1350 SVG master slides.
- Five matching PNG exports.
- One PNG contact sheet showing the complete carousel.
- A README containing the storyboard, post bullet script, caption draft, source
  provenance, and regeneration commands.
- A ZIP archive containing the shareable PNG files and README.
- A deterministic generator script and focused validation tests.

## Visual Direction

Use the approved **real board plus clean diagrams** direction:

- Dark technical background related to the earlier ADC carousel.
- Cyan, orange, green, and yellow accents to distinguish signal roles.
- The actual Rev C board dominates slides 1 and 5.
- Slides 2 and 3 use simple diagrams instead of dense engineering imagery.
- Slide 4 annotates the actual board with plain-language component roles.
- Typography must remain readable at mobile social-feed size.

Do not use the older Rev B2 receive-only board. The authoritative board image is:

`rf-board/review-package/openflight-24ghz-fmcw-rf-rev-c-review-top-3d.png`

That image is byte-for-byte paired with the Gerber ZIP inside the Rev C PCBWay
design-review package.

## Slide Content

### Slide 1: The RF Board

- Headline: **The RF board**
- Copy: **The custom 24 GHz radio inside our golf launch monitor.**
- Visual: large Rev C board render.

### Slide 2: Send And Listen

- Headline: **Send a chirp. Listen for the echo.**
- Copy: **It sends a fast frequency sweep at 24 GHz. Motion changes the signal
  that comes back.**
- Visual: RF board, outbound chirp, golf ball, and returning echo.

### Slide 3: Four Receive Channels

- Headline: **Four antennas work like four ears.**
- Copy: **Each hears the echo at a slightly different phase. Comparing them
  helps reveal direction.**
- Visual: four receive-array symbols and offset phase traces.

### Slide 4: Main Components

- Headline: **Three main chips do the radio work.**
- Copy: **One sends, one listens on four channels, and one keeps the sweep on
  time.**
- Labels:
  - Copper antennas: send and receive.
  - ADF5901: transmitter.
  - ADF5904: four-channel receiver.
  - ADF4159: sweep timing.
  - Bottom connector: control plus four analog echo channels to the ADC board.

### Slide 5: Current Status

- Headline: **Rev C is at design review.**
- Done: fully routed, DRC has 0 violations and 0 unconnected items, review
  Gerbers generated.
- PCBWay: Gerbers passed the portal's automatic upload/fabrication check.
- Still awaiting: explicit confirmation of the hybrid stackup and 50-ohm RF
  geometry. Automatic acceptance is not treated as RF engineering review.
- Still validating: TX antenna, receive gain model, array coupling, and final
  BOM.
- The slide must clearly communicate that this is a design-review package, not
  a production release.

## Post Script

The README should include these plain-language talking points:

- This is the custom 24 GHz radio board for OpenFlight.
- It sends a fast frequency sweep and listens for reflections from the ball and
  club.
- The ADF5901 transmits the chirp.
- Four receive antennas feed the ADF5904, which converts the echoes into four
  slower analog channels.
- The ADF4159 keeps the frequency sweep precise and repeatable.
- A separate ADC board captures the four analog channels for processing.
- Rev C is fully routed and DRC-clean, with review Gerbers generated.
- PCBWay accepted the upload automatically, but stackup confirmation and
  antenna-model validation remain before ordering.

## Implementation

Use a Python generator following the existing `social/adc-post-a` pattern. The
generator writes deterministic SVG, embeds the authoritative board PNG in the
SVG as a data URI for portability, and writes the README. ImageMagick converts
the SVG masters to PNG and builds the contact sheet.

Validation must check:

- All five SVG and PNG files exist.
- Every PNG is exactly 1080x1350.
- The contact sheet is nonblank and contains all five slides.
- The board image source hash matches the approved Rev C review-package render.
- Generated SVG contains no references to Rev B2.
- Required review-status wording is present.
- Visual inspection confirms no clipped, overlapping, or unreadable text.

## Out Of Scope

- Changing the PCB design or Gerber package.
- Claiming completed RF validation.
- Creating posts B and C from the original three-post social series.
- Publishing or uploading the assets to a social platform.
