"""Do the pose scores rank a KNOWN-correct pose first?

Every fit quality number this project has published came from silhouette IoU,
and section 11f measured IoU running *inversely* to pose correctness on real
segmented masks. Before replacing it we have to establish that the replacement
is implemented correctly, and the only place correctness is knowable is
synthetic data: render the mesh at a pose we chose, then ask each score to
recover it.

Passing here does NOT mean a score works on real pixels. It means the score is
not broken. Those are different claims and this file only supports the second.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from openflight.camera.clubpose.fit import measured_camera, render_mask_6dof
from openflight.camera.clubpose.mesh import TriangleMesh
from openflight.camera.clubpose.projection import CAMERA_CENTER_WORLD, _ray_world
from openflight.camera.clubpose.scores import (
    Pose,
    chamfer_px,
    load_annotations,
    mask_edge,
    observed_omega_deg_s,
    omega_residual_deg_s,
    save_annotation,
    score_pose,
)

# World X is DOWNRANGE, Z is up -- so a centre must be built from a camera ray,
# exactly as fit_frame_6dof does, not written down as a bare triple.
_CAM = measured_camera(320, 200)
CENTER = tuple(CAMERA_CENTER_WORLD + _ray_world(np.array([_CAM.cx, _CAM.cy]), _CAM) * 1581.0)


def box_mesh() -> TriangleMesh:
    """A clubhead-proportioned box: thin along the face normal, wide, medium tall.

    Deliberately not square in u/v so that yaw and pitch produce DIFFERENT
    silhouette changes. A symmetric shape would hide a score that cannot tell
    the two axes apart.

    Deliberately 4x a real clubhead. At true scale this box spans ~27 px, where
    a 24 deg yaw changes its width by about one pixel -- which is the actual
    measurement problem, and makes a poor unit test of arithmetic. Whether the
    scores work at 27 px is what the landscape sweep measures; this file only
    establishes that they are not broken.
    """
    half = np.array([20.0, 180.0, 90.0])
    corners = np.array([[i, j, k] for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)], float)
    verts = corners * half
    faces = np.array(
        [
            [0, 1, 3],
            [0, 3, 2],
            [4, 6, 7],
            [4, 7, 5],
            [0, 4, 5],
            [0, 5, 1],
            [2, 3, 7],
            [2, 7, 6],
            [0, 2, 6],
            [0, 6, 4],
            [1, 5, 7],
            [1, 7, 3],
        ],
        dtype=np.int32,
    )
    return TriangleMesh(verts, faces, "unit_box", "b" * 64)


@pytest.fixture(name="cam")
def _cam():
    return measured_camera(320, 200)


@pytest.fixture(name="mesh")
def _mesh():
    return box_mesh()


def render(mesh, cam, yaw=0.0, pitch=0.0, roll=0.0):
    m = render_mask_6dof(mesh, np.asarray(CENTER), yaw, pitch, roll, cam)
    assert m is not None and m.sum() > 0, "fixture pose must project on-sensor"
    return m


class TestChamfer:
    def test_zero_for_identical_masks(self, mesh, cam):
        m = render(mesh, cam)
        assert chamfer_px(m, m) == pytest.approx(0.0, abs=1e-9)

    def test_symmetric_in_its_arguments(self, mesh, cam):
        a, b = render(mesh, cam), render(mesh, cam, yaw=12.0)
        assert chamfer_px(a, b) == pytest.approx(chamfer_px(b, a), abs=1e-9)

    def test_edge_is_a_boundary_not_the_body(self, mesh, cam):
        m = render(mesh, cam)
        e = mask_edge(m)
        assert e.sum() < m.sum(), "an edge that is the whole mask is not an edge"
        assert np.all(m[e]), "edge pixels must lie inside the mask"

    def test_empty_mask_is_reported_not_silently_zero(self, mesh, cam):
        m = render(mesh, cam)
        blank = np.zeros_like(m)
        assert math.isinf(chamfer_px(m, blank)), "no overlap must fail closed, not score 0"


class TestRanksTruthOnSyntheticData:
    """The mask IS the mesh at a known pose, so the true pose is recoverable."""

    @pytest.mark.parametrize("err", [4.0, 8.0, 16.0])
    def test_chamfer_penalises_yaw_error(self, mesh, cam, err):
        truth = render(mesh, cam)
        assert chamfer_px(render(mesh, cam, yaw=err), truth) > chamfer_px(truth, truth)

    def test_chamfer_increases_monotonically_with_yaw_error(self, mesh, cam):
        truth = render(mesh, cam)
        d = [chamfer_px(render(mesh, cam, yaw=e), truth) for e in (0.0, 4.0, 8.0, 16.0, 24.0)]
        assert d == sorted(d), f"chamfer must worsen as pose worsens, got {d}"

    def test_iou_also_ranks_truth_first_when_the_mask_is_exact(self, mesh, cam):
        """IoU is not broken -- it is misleading on REAL masks (section 11f).

        Pinning that down here matters: it stops anyone reading the anti-
        correlation result as 'IoU is buggy'. On an exact mask it behaves.
        """
        truth = render(mesh, cam)
        best = score_pose(mesh, Pose(CENTER, 0.0, 0.0, 0.0), truth, cam).iou
        for err in (4.0, 8.0, 16.0):
            assert score_pose(mesh, Pose(CENTER, err, 0.0, 0.0), truth, cam).iou < best

    def test_yaw_and_pitch_are_distinguishable(self, mesh, cam):
        truth = render(mesh, cam)
        assert chamfer_px(render(mesh, cam, yaw=10.0), truth) != pytest.approx(
            chamfer_px(render(mesh, cam, pitch=10.0), truth), abs=1e-6
        )


class TestOmegaResidual:
    def test_observed_omega_recovers_a_known_rate(self):
        dt, rate = 0.001, 2000.0
        a = Pose(CENTER, 0.0, 0.0, 0.0)
        b = Pose(CENTER, rate * dt, 0.0, 0.0)
        assert observed_omega_deg_s(a, b, dt) == pytest.approx(rate, rel=1e-6)

    def test_residual_is_zero_when_motion_matches_v_over_r(self):
        speed, radius = 35.0, 1.6
        expected = math.degrees(speed / radius)
        dt = 0.001
        a = Pose(CENTER, 0.0, 0.0, 0.0)
        b = Pose(CENTER, expected * dt, 0.0, 0.0)
        assert omega_residual_deg_s(a, b, dt, speed, radius) == pytest.approx(0.0, abs=1e-6)

    def test_residual_grows_when_the_pose_pair_rotates_too_fast(self):
        speed, radius, dt = 35.0, 1.6, 0.001
        expected = math.degrees(speed / radius)
        a = Pose(CENTER, 0.0, 0.0, 0.0)
        slow = Pose(CENTER, expected * dt, 0.0, 0.0)
        fast = Pose(CENTER, expected * dt * 3.0, 0.0, 0.0)
        assert omega_residual_deg_s(a, fast, dt, speed, radius) > omega_residual_deg_s(
            a, slow, dt, speed, radius
        )

    def test_rejects_nonphysical_inputs(self):
        a = Pose(CENTER, 0.0, 0.0, 0.0)
        b = Pose(CENTER, 1.0, 0.0, 0.0)
        with pytest.raises(ValueError):
            omega_residual_deg_s(a, b, 0.0, 35.0, 1.6)
        with pytest.raises(ValueError):
            omega_residual_deg_s(a, b, 0.001, -1.0, 1.6)


class TestAnnotationStorage:
    def test_roundtrips_a_labelled_pose(self, tmp_path):
        path = tmp_path / "labels.jsonl"
        pose = Pose(CENTER, 3.0, -7.5, 12.0)
        save_annotation(path, shot=2, frame=64, pose=pose, annotator="reviewer", pass_index=1)
        got = load_annotations(path)
        assert len(got) == 1
        assert got[0]["shot"] == 2 and got[0]["frame"] == 64
        assert got[0]["pose"]["yaw_deg"] == pytest.approx(3.0)
        assert Pose.from_dict(got[0]["pose"]).roll_deg == pytest.approx(12.0)

    def test_appends_rather_than_overwrites(self, tmp_path):
        """A second labelling pass must never destroy the first -- the whole
        experiment is the COMPARISON between passes."""
        path = tmp_path / "labels.jsonl"
        p = Pose(CENTER, 0.0, 0.0, 0.0)
        save_annotation(path, shot=2, frame=64, pose=p, annotator="a", pass_index=1)
        save_annotation(path, shot=2, frame=64, pose=p, annotator="a", pass_index=2)
        assert len(load_annotations(path)) == 2
