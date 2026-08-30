# Phase F1 club-mesh sources and licenses

No third-party mesh is committed in this directory. Acquisition uses the
publisher's authenticated download endpoint, records the returned archive hash,
and leaves downloaded files ignored by Git.

## Selected and retired sources

| Club | Source | Model ID | License | Published geometry |
|---|---|---|---|---:|
| Driver (RETIRED) | [Callaway Maverik Golf Driver](https://sketchfab.com/3d-models/callaway-maverik-golf-driver-978d0740dc514c8695bbb02f4083f0e3), Paul Ekins | `978d0740dc514c8695bbb02f4083f0e3` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 41,855 triangles |
| 7-iron | [Titleist 7-iron golf club](https://grabcad.com/library/titleist-7-iron-golf-club-1), GrabCAD Community contributor; maintainer-downloaded 690CB right-handed STL | `grabcad:titleist-7-iron-golf-club-1:690cb-right-handed` | Local research use only; no redistribution | 26,238 triangles |

The Sketchfab v3 metadata reports the driver as downloadable and labels its
license `CC Attribution`, with author credit required and commercial use allowed.
CC BY 4.0 permits sharing and adaptation with attribution. We still use a local
cache rather than vendoring the archive: it preserves source provenance, does not
add a third-party binary payload to OpenFlight, and follows the design
specification's existing no-redistribution boundary.

The right-handed Titleist 690CB source is a maintainer-supplied, millimetre-scaled
binary STL from the named GrabCAD model. Its source SHA-256 is
`f35936799295e6ce344279e557f0265ccbb8acef69c4508daff80d219d03cb85`.
It is **local use only**: neither the STL nor its normalized NPZ may be committed.
Only its provenance, hash, attribution, and aggregate evaluation results enter
the repository. The local importer checks this hash before parsing the STL.

The downloaded models are used only as synthetic truth. Their names or geometry
do not imply endorsement by Callaway Golf or Titleist.

### Post-F1 source-quality correction

The Maverik is retired and excluded from active manifests and evaluations. It is
a posed art scene containing grass, a ball, and tens of thousands of disconnected
shell components. Its face/sole geometry is ambiguous, and the former PCA
extent-order normalizer assigned its face normal to the height axis and then
anisotropically distorted the head using an incorrect 55 mm driver depth. It is
not salvageable as canonical driver truth. Driver arms are `HOLD_CAD_MESH` until
the maintainer supplies a locally admitted CAD driver; the corrected driver
category references are 118 mm width, 60 mm height, and 112 mm depth.

The 690CB was re-imported from the same pinned STL using geometric face anchoring
and trusted source millimetres. Corrected normalized asset SHA-256 is
`d63bf7cf1224eb9ce0c7480967057201a4843f3cc2612e4f779ec48fd0839c8a`;
geometry hash is
`87cfacdf639f8c7203ffdfb7da2c9e7ba60a63ed302fc6dbb5db2aed2b9047e3`.
It has one welded component and 23 boundary edges out of approximately 39,357
edges (0.058%, retained as a provenance diagnostic). Before normalization, the
detected coherent face patch is 79.739 x 42.497 mm, 863.296 mm2, with source
normal `(0.112969, -0.253749, -0.960650)`. After the rigid axis transform the
normal is `(1, 0, 0)` to numerical precision; no dimension scaling is applied.

### Pre-outcome iron-source substitution

The originally selected Sketchfab iron (`dc748ddd268c4acab25c54c4048b3912`)
failed the deliberately strict identity validator before any F1 outcome ran. Its
uploader display name changed from the pinned ASCII `real_slimshady` to
`ℜ𝔢𝔞𝔩 𝔖𝔩𝔦𝔪 𝔖𝔥𝔞𝔡𝔶`. The validator was not relaxed or Unicode-normalized. The
maintainer substituted the higher-resolution local 690CB source above. This is
an acquisition/provenance amendment, not a grid, solver, criterion, or gate
change.

## Rejected candidates

- GrabCAD's [library-use guidance](https://help.grabcad.com/article/246-how-can-models-be-used-and-shared)
  permits public non-commercial rendering with attribution but does not clearly
  grant redistribution of a raw CAD file in an AGPL repository. The maintainer's
  Titleist 7-iron is therefore accepted only as an uncommitted local input.
- CGTrader's [Terms and Conditions](https://www.cgtrader.com/pages/terms-and-conditions)
  prohibit making a purchased product available as a separate file. Its
  Royalty Free License permits an incorporated product, not raw-mesh
  redistribution. The candidate `Golf Club 7 Iron` therefore was not purchased,
  downloaded, or committed.

## Required attribution in generated results

Every F1 result bundle records the model page, attribution, model ID, license or
use boundary, source SHA-256, and normalized mesh SHA-256. Any redistributed
driver render or derived dataset must retain the CC BY credit and indicate that
the geometry was normalized into OpenFlight's calibrated club-local coordinate
frame. The local-use-only iron mesh and normalized asset must never be
redistributed.
