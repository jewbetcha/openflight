from __future__ import annotations

import numpy as np

from openflight.camera.clubpose import fit


def test_fit_sequence_can_keep_a_singleton_range_hard_pinned(monkeypatch):
    monkeypatch.setattr(fit, "CAMERA_CENTER_WORLD", np.zeros(3))
    monkeypatch.setattr(fit, "_ray_world", lambda _uv, _camera: np.asarray([1.0, 0.0, 0.0]))
    monkeypatch.setattr(
        fit,
        "render_mask_6dof",
        lambda _mesh, centre, _yaw, _pitch, _roll, _camera: np.asarray([[centre[0]]]),
    )
    monkeypatch.setattr(
        fit,
        "iou",
        lambda rendered, _observed: 1.0 - abs(float(rendered[0, 0]) - 1531.0) / 1000.0,
    )

    result = fit.fit_sequence(
        object(),
        {0: np.ones((10, 10), dtype=np.uint8)},
        object(),
        range_grid_mm=(1581.0,),
        yaw_grid=(0.0,),
        pitch_grid=(0.0,),
        roll_grid=(0.0,),
        refine_range=False,
    )

    assert result[0]["range_mm"] == 1581.0
