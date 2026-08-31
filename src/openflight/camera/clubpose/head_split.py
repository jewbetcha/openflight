"""Separate the clubhead from the shaft inside one moving component.

MEASURED basis (session 20260825_181734, shots 002/005/014/021/029,
frames 58-88, 205 components):

    isolated shaft   max inscribed radius 2.0 - 3.0 px,  0.0% of pixels >= 4 px
    isolated head    max inscribed radius 5.0 - 11.6 px, 12 - 49% of pixels >= 4 px

The two never overlap, so "thicker than any shaft" is a measured discriminator,
not a tuned one. The shaft is a thin line; the head is a compact body.

The head core (distance transform >= HEAD_CORE_PX) is used only as a SEED. The
returned mask is the original component's own pixels, partitioned by a watershed
on the distance transform, so the head's outline is the observed silhouette
boundary - never eroded, never padded. Only the cut across the hosel neck is
synthetic, and that is where the head genuinely ends.
"""

from __future__ import annotations

import cv2
import numpy as np

HEAD_CORE_PX = 4.0  # exceeds every measured shaft inscribed radius (max 3.0)
SHAFT_MAX_PX = 3.5  # below every measured head inscribed radius (min 5.0)
# Measured over 205 components: head alone reaches 4-41 px, head+shaft
# 145-187 px. 60 sits inside the empty gap.
SHAFT_REACH_PX = 60.0


def split_head(component: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """(head_mask, shaft_mask) for one connected moving component.

    Returns None when the component contains no body thick enough to be a
    clubhead - fail closed rather than hand back a piece of shaft.
    """
    c = (component > 0).astype(np.uint8)
    dt = cv2.distanceTransform(c, cv2.DIST_L2, 5)
    core = (dt >= HEAD_CORE_PX).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(core, 8)
    if n <= 1:
        return None
    head_label = 1 + int(np.argmax(st[1:, 4]))
    head_core = (lab == head_label).astype(np.uint8)

    reach = cv2.distanceTransform(1 - head_core, cv2.DIST_L2, 5)
    far = c.copy()
    far[reach <= SHAFT_REACH_PX] = 0  # farther than any head extends
    far[dt >= SHAFT_MAX_PX] = 0  # and genuinely thin

    markers = np.zeros(c.shape, np.int32)
    markers[c == 0] = 1  # background
    markers[head_core > 0] = 2
    markers[far > 0] = 3
    if not (markers == 3).any():
        return c, np.zeros_like(c)  # nothing thin and remote: all head

    relief = (255.0 * (1.0 - dt / max(dt.max(), 1e-6))).astype(np.uint8)
    cv2.watershed(cv2.cvtColor(relief, cv2.COLOR_GRAY2BGR), markers)
    head = ((markers == 2) & (c > 0)).astype(np.uint8)
    shaft = ((markers == 3) & (c > 0)).astype(np.uint8)
    # watershed marks its ridge -1; award those pixels to whichever side is nearer
    ridge = (markers == -1) & (c > 0)
    if ridge.any():
        dh = cv2.distanceTransform(1 - head, cv2.DIST_L2, 5)
        ds = cv2.distanceTransform(1 - np.clip(shaft, 0, 1), cv2.DIST_L2, 5)
        head[ridge & (dh <= ds)] = 1
        shaft[ridge & (dh > ds)] = 1
    if int(head.sum()) < 60:
        return None
    return head, shaft
