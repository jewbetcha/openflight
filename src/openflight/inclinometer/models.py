"""Value objects shared by inclinometer drivers and consumers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AccelerationSample:
    """One timestamped LIS3DH acceleration reading in units of gravity."""

    timestamp: float
    x_g: float
    y_g: float
    z_g: float


@dataclass(frozen=True)
class OrientationSnapshot:
    """Filtered enclosure orientation produced from a stationary sample window."""

    timestamp: float
    x_g: float
    y_g: float
    z_g: float
    gravity_g: float
    raw_pitch_deg: float
    calibrated_pitch_deg: float
    pitch_std_deg: float
    sample_count: int

    def to_dict(self) -> dict:
        """Return JSON-safe rounded diagnostic fields."""
        data = asdict(self)
        for key in ("x_g", "y_g", "z_g", "gravity_g"):
            data[key] = round(data[key], 4)
        for key in ("raw_pitch_deg", "calibrated_pitch_deg", "pitch_std_deg"):
            data[key] = round(data[key], 3)
        data["stable"] = True
        return data


@dataclass(frozen=True)
class SnapshotSelection:
    """Result of selecting a stable orientation for one impact."""

    snapshot: OrientationSnapshot | None
    status: str
    age_s: float | None = None

    def to_dict(self) -> dict:
        """Return selection diagnostics suitable for shot/session logging."""
        data = {
            "applied": self.snapshot is not None,
            "status": self.status,
            "age_s": round(self.age_s, 3) if self.age_s is not None else None,
        }
        if self.snapshot is not None:
            data.update(self.snapshot.to_dict())
        return data
