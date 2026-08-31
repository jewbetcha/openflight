<!-- Generated from the published report by the report generator on the fork. Do not edit by hand. -->

# Markerless clubface impact location

> This is the markdown rendering of the [technical report](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75). The web version carries 11 figures — real frames with the model's own projections overlaid — which are not reproduced here.


*OpenFlight · technical report · session 20260825_181734, 21 shots*

An assessment of whether clubface impact location and face angle can be measured from a single behind-ball camera under ambient light, with no markers on the ball or club. This report states what has been measured, what has not, and what would resolve the remaining questions.

## 01. Summary

Ball flight measurement is working and validated against the radar. Club measurement is not, and the reason is now understood well enough to act on.

> **✅ Established**  
> **Ball detection** succeeds on 21 of 22 captures with no false detections. **Impact timing** from camera and radar agree to **0.66 frames**. **Camera attitude** is measured rather than assumed: boresight pitch **−0.185° ± 0.111°**, with the ball centre **163 mm** below the lens. The **7-iron/9-iron launch angle difference is real** — an independent reconstruction gives +2.91° against the radar estimator's +2.59°, and it survives a 13° change in assumed camera pitch. Camera and radar independently agree on the tee position to **1632 ± 53 mm** against a taped **1581 mm**.  

> **⚠️ Not established**  
> **Face angle, dynamic loft and impact location** are model-dependent inferences, not measurements. **No accuracy figure exists for any of them**, because the comparison harness does not yet cover club metrics. Radar club path and attack angle are **rejected on 21 of 21 shots**. Camera and radar disagree by approximately **5° in both axes**, and no current data arbitrates between them.  

> **⚡ Three findings that determine what to do next**  
> **1. The pose fit is noise-limited, not model-limited.** One pixel of segmentation error is worth approximately **ten degrees** of face angle. The first 5° of face angle change the projected silhouette by **zero pixels**.  
> **2. The clubhead range is modelled incorrectly.** Every fit renders the club at the range of the *ball*. The radar shows the club traversing **529 mm** of range during the frames being fitted. Constant range is rejected at **p ≈ 0.04**.  
> **3. Changing the fit metric does not help.** Two objectives with independent failure modes recover poses differing by a median of **12.7°** — the same magnitude as the segmentation noise.  

> **⚠️ Correction affecting several figures in this report**  
> The acoustic trigger lag was previously stated as **6.0 frames**. It is **2.11 frames** on this rig — the sound's travel time over 1.575 m — and it varies with how far the unit sits from the ball. The wrong constant put contact at frame 68 on every shot instead of a per-shot value near 71.9, and it anchored the clubhead range model and every pose fit below. Those results are **superseded**; see §03. Production measurement paths are unaffected.  

The highest-value next step is not another estimator. The club-metric comparison harness has now been **built and shipped**; the step is a **session alongside a Trackman** to give it truth to compare against. Full priorities, including what was completed on 2026-08-27 and what each completion showed, in [Recommendations](#recommendations).

## 02. Measurement setup

A single monochrome global-shutter camera behind the ball, with two radars. All figures in this report come from one session of 21 correctly exposed shots (7-iron and 9-iron), captured 2026-08-25.

| Parameter | Value | Source |
|---|---|---|
| Sensor / mode | OV9281, 320×200 | 2× subsampled readout |
| Frame rate | 467.6 fps | measured, 0 dropped frames |
| Exposure | 247–298 µs | measured |
| Lens / focal length | 2.8 mm, fx = 466.7 px | datasheet optics, not a calibrated matrix |
| Plate scale at the ball | 0.2952 px/mm | derived; 1 px = 3.39 mm |
| Camera height | 203.2 mm | tape |
| Camera-to-ball range | 1581 mm | tape chain; radar agrees to 1632 ± 53 mm |
| Boresight pitch | −0.185° ± 0.111° | recovered from footage, 21 shots |
| Radars | OPS243-A + IWR6843 | 24 GHz Doppler; 62 GHz FMCW |

**Two properties of this configuration constrain everything that follows.** The plate scale means the clubhead spans roughly 32 pixels. And there is no distortion model, no independently estimated principal point, and no separate fx/fy — the intrinsics are nominal, derived from the datasheet lens over the effective pixel pitch.

> **Known gap in the setup record**  
> The enclosure used for this session is not dimensioned in any drawing. Camera pitch was recovered from the footage rather than specified, so it is not reproducible on a second unit. Establishing the mounting geometry, and ideally deriving camera attitude from the existing LIS3DH inclinometer as the radar already does, would remove that dependency.  

## 03. Validated measurements

These measurements are supported by cross-sensor agreement or by an independent reconstruction, and are the parts of the system suitable to build on.

### Ball detection

Detection succeeds on 21 of 22 captures with no false positives. The one failure is a capture taken at 495 µs and gain 15, which saturated 99.8 % of the frame; it is excluded from all analysis in this report.

Detection cannot rely on brightness alone. At address the ball sits against a mat driven past the sensor's ceiling and registers as a *dark* object; in flight it is the brightest thing in frame. The detector must accommodate both polarities.

> **Figure 1** — The same ball, 120 ms apart, at 9×. At address it sits on a mat driven past the sensor's ceiling, so it registers as a **dark** object — 192 DN against 255. Once airborne against the dark backdrop it is a **bright** object at +141 DN. The contrast **inverts sign within a single shot**.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

### Ball geometry at the tee

The teed ball's image is not circular. It is measurably flattened across the top, which biased an earlier radius estimate and, through it, the assumed camera-to-ball range. Fitting the boundary rather than thresholding the bright region removes the bias.

> **Figure 2** — The teed ball at 24×, four different shots. **Olive** is the detected mask, **violet** the fitted circle. The bright ball region is visibly flattened across the top, and the circle's upper arc passes through grey mat rather than white ball. The blob is wider than it is tall — which a sphere cannot be.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

### Impact timing

Contact precedes the acoustic trigger by the time the sound takes to reach the unit:

```
impact_time = trigger_time  -  distance_to_microphone / speed_of_sound(T)
```

On this rig the ball sits **1.575 m** from the unit, giving **4.59 ms** or **2.11 frames** at 468 fps. Two independent routes agree:

| Method | Impact frame |
|---|---|
| Acoustic model — distance ÷ speed of sound | 71.85 |
| Ball departure, measured per shot (n=20) | 71.89 ± 0.77 |

They agree to **0.04 frames**. The SEN-14262 hardware path is about 10 µs and is negligible; there is no unexplained detector latency.

> **⚠️ This corrects a figure published earlier in this report**  
> Earlier versions stated a **6.0-frame** lag and warned readers off the ball-track estimate. **Both were wrong.** The 6.0 constant put contact at frame 68 on every shot — off by **3.89 frames**, about 8 ms — and the ball track, which was dismissed, was correct.  
> The error came from misreading a render. The clubhead is **27 px wide** and sits adjacent to the ball for two or three frames before it strikes, so "the head reaches the ball" is not contact. Contact is when the **ball starts moving**. Per-shot values run **70.65 to 73.64**, not a constant.  
> **Everything anchored on that constant is superseded** — the clubhead range model in §04, the pose fits, and a claimed "post-impact frames were fitted" defect that was an artefact of the wrong anchor.  

> **⚡ The lag belongs to the installation, not to the software**  
> It scales with how far the unit sits from the ball, so a fixed frame offset is only ever right for the rig it was measured on. At 468 fps, with the trigger at frame 74:  
>
> | Ball to unit | Lag | Impact frame |
> |---|---|---|
> | 1.0 m | 2.91 ms | 72.64 |
> | **1.575 m — this rig** | 4.59 ms | 71.85 |
> | 2.5 m | 7.28 ms | 70.59 |
> | 3.5 m | 10.20 ms | 69.23 |

Distance dominates: doubling it doubles the lag, while the whole 0–40 °C range moves the speed of sound about 7 %. Shipped as `src/openflight/acoustic.py` with 21 tests. `tee_range_m` in `iwr6843/calibration.py` is the distance source.

> **✅ Production already solved this; the research code did not use it**  
> `iwr6843/shot.py:impact_time_s` back-extrapolates the *ball's own range walk* to the tee rather than trusting the trigger, and its docstring records why: assuming the trigger's ring position "is why the club-path estimator was fitting the follow-through". `camera/club_delivery.py` likewise *detects* the impact frame and uses the trigger only as a ±8/+10 frame plausibility gate.  
> **So the production measurement paths are not affected.** The defect was confined to the research scripts, which reinvented a solved problem and got it wrong. An earlier draft of this panel claimed a production-wide 4.6 ms bias; that claim was itself incorrect and is withdrawn.  

### Launch angle

The 7-iron/9-iron launch angle difference is real and not an artefact of the estimator. An independent reconstruction from camera rays plus radar range walk gives **+2.91°** and **+4.22°** against the shipped estimator's +2.59° and +3.60°, and the result is invariant to a 13° change in assumed camera pitch. A separate hypothesis, that the estimator carries a club-dependent bias, was tested and refuted (−0.003°).

## 04. Clubhead pose estimation

The clubhead is located reliably. Its orientation is not, and the limiting factor is not the fitting method.

### The club model and its reference frame

The model is a triangle mesh of a Titleist 690CB 7-iron. Pose is solved as a 3D centre plus orientation, projected through the camera model and rasterised; every overlay in this report is the model's own projection, unpadded.

> **Figure 3** — **Left** renders the surfaces facing `+x` — the cavity back, with its recessed oval and perimeter rim. **Right** renders `−x` — the striking face, flat with fine parallel grooves. Both are z-buffered per pixel. A plain silhouette render cannot tell front from back at all: it is the same outline, mirrored.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

> **⚠️ Defect: the model's reference frame is anchored to the back of the club**  
> `detect_face_plane` selects the plane by an extremity criterion. On a cavity-back iron the hosel protrudes past the striking face, so the criterion selects the **cavity rim on the reverse side**. Measured loft was reported as 17.5°; the true values are **33.10° loft and 61.19° lie**.  
> **Every dynamic-loft figure derived from the mesh inherits this.** The two images below are the two candidate surfaces; the scorelines identify the correct one unambiguously.  

> **Figure 4** — The surface the code anchors the model’s frame to, seen face-on. It is the **back** of a cavity-back iron — a perimeter rim (orange) around a recessed cavity floor (blue), with the sole in green. Every pixel here is the model’s own geometry, coloured by which candidate surface each triangle belongs to.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

> **Figure 5** — The other side, which both earlier passes had dismissed as “the recessed cavity floor”. The scorelines settle it. **This is the striking face.**  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

### Fitting the model to real frames

Position and scale behave. Orientation does not. The fit locates a clubhead-shaped object in approximately the right place on every pre-impact frame, and the printed angles are the part that should not yet be relied on.

> **Figure 6** — Every second frame from F58 to F80 of shot 014, raw sensor pixels at 3× nearest-neighbour. The clubhead now has a readable outline — sole, topline, hosel, face — for the whole pass, and the shaft is a bright unbroken line. On the old capture the impact zone was 83–94 % clipped and none of this existed.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

> **Figure 7** — Shot 014, F63–F77. **Olive** is the observed silhouette the fit consumes. **Pink** is the projected 3D mesh at its fitted pose — the model’s own output, unpadded. The olive outline hugs the head in all 15 frames. The pink one wanders: on adjacent frames the fit reports pitch −40° then +70°, roll 0° then 135°, range 1340 mm then 1645 mm. Teal marks the teed ball until it departs.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

> **Figure 8** — Left: real pixels with the observed silhouette (olive) and the projected mesh (violet). Middle: the same fitted pose **shaded, from the camera's own viewpoint**. Right: the same pose from a **fixed** viewpoint with world axes, so frames can be compared against each other. Both renders are the model's output — they show what the fit believes, which is the point.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

### Information available in the silhouette

The silhouette carries much less orientation information than it appears to. Measured directly on the mesh, projected width against face angle:

| Face angle | 0° | 5° | 10° | 15° | 20° | 30° |
|---|---|---|---|---|---|---|
| Projected width | 32 px | 32 px | 30 px | 30 px | 28 px | 26 px |

**The first five degrees of face angle change the silhouette by no pixels at all.** Ten degrees changes it by two. This is a property of the projection, not of the fitting method — a clubhead rotating about the vertical axis presents an almost stationary width, because the thickness rotating into view compensates for the face length rotating out of it.

Sweeping each axis around a fitted pose on real frames and measuring how far it can move before either metric registers a change:

| Axis | IoU (0.01 threshold) | Chamfer (0.1 px threshold) |
|---|---|---|
| Yaw — face angle | ±7° | ±10° |
| Pitch — dynamic loft | ±8.5° | ±14° |
| Roll — lie | ±7° | ±9.5° |

### Segmentation as the binding constraint

Perturbing the observed mask by **one pixel** — a dilation or erosion, which is what a change in segmentation threshold produces — moves the fit score by **0.40 to 1.45 times** as much as a **±30° pose error**. On four of six shots, the boundary metric moved further for one pixel of mask than across the entire 60° sweep.

**One pixel of segmentation error is worth approximately ten degrees of face angle.**

This also explains why silhouette overlap ran inversely to pose correctness in earlier work. Mask area changes by about **3 %** for 10° of face angle, but by roughly **25 %** for a one-pixel dilation — so an area-based metric is around eight times more responsive to segmentation quality than to twenty degrees of pose. It was measuring mask quality, and the arms with cleaner masks scored better while recovering worse poses.

Consequence: the effective levers are sub-pixel edge extraction and plate scale, not the fitting algorithm.

### The clubhead range model

The fitter places the mesh at a fixed 1581 mm, the camera-to-ball distance. The clubhead is not at that range during the frames being fitted — it arrives from behind the ball and passes through it.

Running the production club tracker over the raw radar cube places the clubhead at **1.042 m** five frames before impact and **1.571 m** at contact, a **529 mm** traverse, extrapolating to the tee with 29 mm of error. Across all 21 shots the radar's summary fields agree and independently confirm the taped ball position:

```
track start          1238 +- 24 mm
+ range_rate x span
= track end          1632 +- 53 mm     tee ball, by tape: 1581 mm
```

> **✅ Test independent of orientation**  
> If the club recedes, its projected area must fall as 1/r². Observed clubhead mask area, last pre-impact frame divided by first, n=10 shots:  
> **Observed 0.829 ± 0.222** · radar-derived range model predicts **0.813** · constant range predicts **1.000**.  
> Constant range is **rejected at p ≈ 0.04**; the radar-derived model is consistent at p ≈ 0.8. This test uses no orientation parameter, so refitting angles cannot account for it.  

This is also a mechanism for the metric behaviour above rather than a separate symptom. With the model systematically under-scaled on the early frames, the pose that projects largest matches best regardless of its orientation — and the orientation angles were the only free parameters available to absorb a scale error.

> **Figure 9** — **The mismatch, at the range the tape says.** The model covers only **43–55 %** of the observed pixels. A shorter range makes the projection larger, so the fit was pulling the club nearer to close that gap. Note the thin cyan tail running up and left out of each silhouette: that is the shaft, and **the model has none** — its 62 mm protrusion measures out as hosel and ferrule (§11h). The model cannot cover that tail at any range.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

**Correcting the render alone is not sufficient** (IoU −0.0035, chamfer +0.021 px). Orientation was fitted under the constant-range assumption and must be re-solved with the corrected range model. That work is outstanding.

### Objective function selection

Because overlap was suspect, a boundary-distance metric was implemented and evaluated as a replacement. It fails in a different way from overlap — area versus shape — so agreement between the two is informative.

Refitting from identical seeds under each metric, the recovered poses differ by a **median of 12.7°** (n=18, range 5.8–28.0°).

> **Figure 10** — **One shot, three frames before impact, fitted three ways.** Cyan is the observed silhouette the fit consumed; orange is the model’s own projection at the fitted pose. Rows: the shipped depth grid, the corrected grid, and range pinned at the measured 1581 mm. Reading across a row shows how coherent the pose sequence is; reading down a column shows what the depth treatment changed. The ball is the pale disc at bottom centre.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

**When the choice of objective function moves the recovered orientation by more than ten degrees, the data is not determining the pose.** Two metrics with independent failure modes reaching the same limit is a stronger result than either alone: the fit is noise-limited, not objective-limited.

Recommendation: no further effort on the objective function until segmentation quality or plate scale improves.

## 05. Radar contribution

The radar already measures quantities the pose fit does not use, and its own club-angle output is rejected on every shot for a reason worth diagnosing.

### What the radar measures today

Impact timing is available to approximately 33 µs from the OPS243 30 kHz I/Q buffer. The IWR6843 tracks the clubhead's range and range rate through the approach. The range–time map separates the clubhead, the ball and static clutter cleanly:

> **Figure 11** — Range–time map for shot 014, static returns removed. Three things separate cleanly. A **diagonal from 1.05 to 1.35 m in the 12 ms before impact** — the clubhead approaching. A **bright vertical band at 1.85–1.95 m that never walks in range** for the entire 72 ms — the golfer’s body and arms, which move but do not translate. And a second diagonal departing outward after impact — the ball. Time runs down; each block of twelve rows is one 3 ms frame.  
> *(image in the [web version](https://claude.ai/code/artifact/c8817c34-c3ea-4455-9700-cf5a4e238b75))*

Per shot, the radar currently reports and the pose fit currently discards: clubhead range at track start (**1238 ± 24 mm**), range rate (approximately **33 m/s**), azimuth rate, and track span. The clubhead travels within about **25°** of the radar boresight, so 91 % of its speed is measured directly.

The 22 raw capture files are included in the session export and are decoded by `src/openflight/iwr6843/dump.py`, which is production code. Prior to this report the silhouette work had never read them.

### Club path and attack angle

Club path and attack angle are rejected on **21 of 21 shots**, always with status `rejected_phase_span`. Two observations narrow the cause:

| Observation | Value | Expected |
|---|---|---|
| Azimuth phase span | 2.18–3.91 rad | ≈1.3 rad; ceiling π/2 |
| Attack angle, all shots | −25.3° to −37.3° (sd 2.8°) | ≈−4° for a 7-iron |
| Club path, all shots | −8.6° to +37.1° | a few degrees |

Attack angle returning a tightly clustered value near −31° on every shot regardless of the swing is a systematic artefact, not a measurement. The apparent azimuth swing is **three to ten times larger than the clubhead can physically produce**.

A plausible mechanism is scatterer migration across an extended, rotating target: the clubhead subtends about 4° at 1.25 m while rotating at roughly 1300°/s, so the dominant scattering point moves between frames. **This is a hypothesis and has not been confirmed.** Note that the phase-span check deliberately does not unwrap, for documented reasons — unwrapping fabricated angles in earlier work.

### Cross-range resolution and Doppler

The radar cannot image the clubhead directly. Angular resolution is set by aperture, and the array is 19.3 mm wide:

| Quantity | Value |
|---|---|
| Wavelength (62 GHz) | 4.835 mm |
| Range resolution | 46.9 mm |
| Aperture (8 virtual elements at λ/2) | 19.3 mm |
| Beamwidth | 12.7° |
| **Cross-range cell at 1.25 m** | **277 mm** |
| Clubhead, for comparison | 90 mm — 0.33 cells |

Clubhead, shaft and hands fall within a single angular cell. Additional pulses improve signal-to-noise and velocity resolution; they do not improve angular resolution.

**A rotating target does synthesise an effective aperture** (inverse synthetic aperture radar). At 1300°/s the head rotates 15.1° across the 11.7 ms tracked, giving `λ/(2Δθ)` = **9.2 mm** of cross-range resolution — a 30-fold improvement, approximately ten cells across the head. Micro-Doppler analysis gives the same cell count, as it must.

Measured on the raw cube with range walk corrected, across **21 shots and 112 frames**:

| Measurement | Doppler bins |
|---|---|
| Point-target floor, same estimator and window | 1.27 |
| Predicted from rotation alone (838 Hz) | 1.36 |
| Expected in quadrature | 1.86 |
| **Measured clubhead median** | **1.95** |

The implied toe-to-heel spread is **893 Hz** against **838 Hz** predicted. The clubhead return is measurably broader than a point target, by close to the amount its rotation should produce.

> **⚠️ This is not yet evidence of rotation**  
> The discriminating test is whether the spread scales with club speed. It returned a negative correlation, but the test has **no statistical power on this data**: the predicted effect across the full speed range is **0.154 bins** against an observed scatter of **0.490 bins**, and club type is perfectly confounded with speed (7-iron 37.4–38.8 m/s, 9-iron 34.6–36.4 m/s, no overlap). Additionally, **23 % of frames return a width below the point-target floor**, which is unphysical and indicates a noisy estimator at 12 samples.  
> Two measurements would resolve it: a session spanning a wide club-speed range, and a positive control on the ball, whose spin predicts roughly 8 bins of spread. Neither has been run.  

If the rotation signal is real, the useful output is not an image. **Focusing an ISAR image requires estimating the target's rotation rate and axis** — the two parameters the pose fit currently leaves free.

## 06. Comparison with commercial systems

Two commercial systems solve this problem behind the ball, both with less capable cameras than ours.

| System | Camera | Illumination | Markerless impact location |
|---|---|---|---|
| **Trackman 4** | 720p @ 60 fps | ambient, 700–800 lux | yes |
| **Mevo Gen 2** | single phone-class module | ambient, 300 lux minimum | yes |
| **OpenFlight** | 468 fps | ambient | not yet |

The relevant difference is architectural rather than optical. Trackman's approach fuses the camera with radar that supplies kinematics and timing at 40 kHz; at 60 fps the clubhead travels roughly 0.7 m between frames, so the camera cannot track impact independently and is not required to. Impact location is a product of the fusion, not of frame rate.

OpenFlight has the ingredients: **8× Trackman 4's frame rate**, impact timing to approximately 33 µs, and radar kinematics from two devices. What is missing is the fusion model — and, as §04 shows, a camera term whose noise floor is currently around ten degrees per pixel.

Comparator set is Trackman 4, Full Swing KIT and Mevo Gen 2. Trackman iO is excluded: it is ceiling-mounted, and its frame rate is the price of markerless spin from overhead rather than a behind-ball figure.

## 07. Recommendations

Ordered by dependency. Each item carries the measurement that justifies it. Items completed since this report was first issued are kept, with their outcomes, because several outcomes changed what the remaining items are worth.

### Completed, 2026-08-27 — and what each one showed

| Item | Outcome |
|---|---|
| **Extend the Trackman comparison to club metrics** | Written; in a separate PR. |
| `compare_trackman.py` pairs OpenFlight and Trackman shots but compares ball data only, so no club-side figure can be scored against truth. An extension covering twelve club-delivery metrics is written and tested, but OpenFlight can currently supply only two of them (attack angle and club path) and there is no Trackman session to run it against, so it is offered as its own change rather than bundled here. |
| **Impact timing from the installation** | Model validated; module on the fork. |
| Contact = trigger − distance ÷ speed of sound: the model and measured ball departure agree to **0.04 frames**, correcting a 3.89-frame error that had anchored earlier fits (§03). The module ships when the capture path consumes it; nothing in the runtime calls it yet. |
| **Surface computed trajectory metrics** | Open; not in this branch. |
| The ballistics simulator computes apex, lateral deviation, flight time, landing speed and landing angle on every shot, and `server.py` reads only `carry_yards`. Five Trackman-parity outputs are discarded at no extra cost. Wiring them through is unrelated to camera vision, so it is left for a separate change. |
| **Radar range model + rotation-axis constraint** | Implemented; orientation still fails. |
| Range now comes from the radar's own range rate and the rotation axis from the fused velocity, dropping the fit from five free parameters to four. The velocity half **validates**: fused \|v\| matches the OPS243's independent club speed with a mean ratio of **0.970** (sd 0.029, spread 0.941–1.015 across 6 shots; worst shot 5.9% off). The OPS243 takes no part in the fit, so this is a genuine cross-sensor check. The orientation half does not: **0 of 6** shots land inside the physical envelope, and refitting with the corrected impact anchor moved the recovered angles substantially — a fit that sensitive to its time anchor is not extracting orientation from the pixels. **This is why the remaining items are ordered as they are.** |
| **Analyse the raw radar captures** | Opened; rotation unconfirmed. |
| All 22 `.l3dump` files decoded. The clubhead's Doppler width (1.95 bins median) exceeds the point-target floor (1.27) by close to the rotation-predicted amount, but the discriminating test has no statistical power on a 7-iron/9-iron-only session. Needs the wide-speed-range capture below. |

### Tier 1 — prerequisite for any accuracy claim

| Item | Justification | Cost |
|---|---|---|
| **A session alongside a Trackman, using the new club-metric comparison** | The harness exists; no club figure can be validated until it has truth to compare against. | 1 session |
| **Target at a taped position, visible to both sensors** | Resolves the **5°** camera/radar disagreement, which nothing in the current data can arbitrate. | 1 session |

### Tier 2 — actionable with existing data

| Item | Justification | Cost |
|---|---|---|
| **Extract more of the frames the club already appears in** | The club is visible for roughly **ten frames** before contact (about f62–f72 at this framing); the current extractor keeps **3–5**, losing the early frames against the dark netting. A better segmenter therefore roughly **doubles** the observations per shot — a bounded gain, not an open-ended one, since nothing recovers more frames than the club is in view for. Against four fit parameters, 5→10 observations changes the conditioning materially. | days |
| **Correct `detect_face_plane`** | Still anchors the model frame to the cavity rim on the reverse of the club (true loft **33.10°**, reported 17.5°). Interim workaround exists: `replay/club_angles.py` carries the measured axes, and its `square_pose()` is now the required seed for any fit — the mesh frame's origin is a *backwards* club. | hours |

### Tier 3 — requires a new capture or hardware change

| Item | Justification | Cost |
|---|---|---|
| **Capture at 1280×800, 1:1** | Plate scale doubles to **0.655 px/mm**, so 10° of face angle becomes 4 px rather than 2, at the same frame rate and field of view. Multiplies with the segmentation item above — same frames, more pixels each. The optical half is certain; whether segmentation error stays near 1 px is not — earlier testing on real segmented edges gave a 0.78× improvement, not 2×. | 1 session |
| **Capture across a wide club-speed range** | Every shot here is a 7-iron or 9-iron with no speed overlap, which left the radar-rotation test unable to discriminate. A driver and a wedge in one session removes the confound and would settle whether the Doppler broadening is rotation. | 1 session |
| **Lux and exposure ladder in the bay** | Determines whether the optical route is a one-degree or four-degree instrument. Comparator anchors: Trackman 4 at 700–800 lux, Mevo Gen 2 at 300 lux, both continuous. | 1 session |
| **Dimension the enclosure; self-level the camera** | Camera pitch is currently recovered from footage rather than specified, so it is not reproducible on a second unit. `inclinometer.py` already tilt-compensates the radar. The acoustic timing fix also depends on a per-installation ball-to-unit distance, which belongs in the same calibration record. | days |

### Candidate approaches, not yet evaluated

| Approach | Rationale | Principal risk |
|---|---|---|
| **Sub-pixel edge extraction** | Masks come from a hard threshold. Given that one pixel is worth ~10° of face angle, boundary precision is worth more than any change to the fit. | Motion blur may already exceed sub-pixel scale — the club moves about 3 px during exposure. |
| **Mark the club on the measuring rig only** | The shipped product must be markerless; a calibration rig need not be. Provides per-frame truth to score the markerless estimator against. | None technical. Requires the rig to be built. |
| **Second camera** | Stereo resolves depth directly and would settle the range question outright. | Cost and synchronisation; does not address the segmentation limit, which is currently binding. |

## 08. Reproducing this work

Every figure here was produced by a script. Those scripts and their recorded results are kept on the fork ([`falsification/`](https://github.com/HarjotDhanota/openflight/tree/feat/silhouette-poc/research/silhouette_poc/falsification)) rather than in this repository: each answered one question once, and the answers are stated above. The library they exercise is `src/openflight/camera/clubpose/`, with its tests in `tests/`.

| Result | Script |
|---|---|
| Silhouette information limits, per-axis | `pose_landscape.py` |
| Metric comparison and refit | `test_fusion_chamfer.py` |
| Range model test | `test_radar_range_ramp.py` |
| Doppler width / ISAR assessment | `test_isar_doppler_width.py` |
| Acoustic trigger timing | `src/openflight/acoustic.py`, `tests/test_acoustic.py` |
| Delivered loft / face angle / lie | `src/openflight/camera/clubpose/angles.py`, `tests/test_clubpose_club_angles.py` |
| Scoring primitives and their unit tests | `src/openflight/camera/clubpose/scores.py`, `tests/test_clubpose_pose_scores.py` |

Scripts resolve the capture export via `OPENFLIGHT_SESSION`, a `--session` argument, or conventional paths, and fail with an actionable message if none is found. The club mesh is not redistributed; it is available from GrabCAD and is used for research only.

**Contributing a capture is the most useful help.** A session with a driver and a wedge alongside the irons, at 1280×800 1:1, with a lux reading at the ball, would unblock three separate items in Tier 3 at once.

## 09. Appendix: corrections to earlier claims

Figures published in earlier versions of this work that were subsequently found to be wrong. They are listed because some were circulated, and because the failure modes recur.

| Claim as published | Correction |
|---|---|
| Measured loft 17.5° | **33.10°.** The detector anchored to the cavity rim on the reverse of the club. |
| The mesh has a 62 mm shaft stub | It has **no shaft**. The feature measures 63.8 mm × 12.9–17.5 mm and is the hosel and ferrule. |
| Free-depth fits at 1180–1336 mm are errors of −245 to −401 mm against the tape | Those ranges lie **inside** the clubhead's physical range during the fitted frames. The fit was tracking the club; pinning it to 1581 mm moved it onto the ball. See §04. |
| Representative fit quality, IoU 0.636 | **Not reproducible** by any code in the repository — the committed tracker returns 0.292 on that shot, a careful rebuild 0.452. |
| The trigger lags impact by 2.11 frames — then retracted in favour of 6.0 frames | **The retraction was the error.** 2.11 frames is correct and equals the acoustic time of flight over 1.575 m. Confirmed by the ball track (71.89 ± 0.77, n=20) and by the physics, agreeing to 0.04 frames. The 6.0 figure came from misreading a render. |
| Production carries a ~4.6 ms impact-timing bias | **Withdrawn.** Both production measurement paths derive impact from the data, not the trigger. |
| Field of view 2.17 m in the current mode | **1.08 m.** The calculation used the full sensor width where the capture reads half. |
| A 6 mm lens yields about one degree of face angle | Did not survive testing on real segmented edges, which improved by **0.78×** rather than the projected 2×. |
| `iwr_club_path_club_range_m` is the clubhead's range | It is the range at the **start of the radar track**, roughly 5.5 frames before impact. |
| Radar club path and attack angle are exactly equal and opposite — a degeneracy | True on one shot only. Across 22 shots the sum ranges +7.8° to −42.1°. |

> **Common cause**  
> All but one of the above came from generalising a single shot, a single measurement, or a geometric assumption that was never checked against the mesh or the data. The corrections came from cross-set checks and from rendering the thing in question and looking at it. Both are cheap; neither was applied first.
