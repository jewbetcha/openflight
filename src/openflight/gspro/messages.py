"""OpenConnectV1 JSON schema (https://gsprogolf.com/GSProConnectV1.html)."""

import json
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class BallData:
    Speed: float = 0.0
    SpinAxis: float = 0.0
    TotalSpin: float = 0.0
    BackSpin: float = 0.0
    SideSpin: float = 0.0
    HLA: float = 0.0
    VLA: float = 0.0
    CarryDistance: float = 0.0


@dataclass
class ClubData:
    Speed: float = 0.0
    AngleOfAttack: float = 0.0
    FaceToTarget: float = 0.0
    Lie: float = 0.0
    Loft: float = 0.0
    Path: float = 0.0
    SpeedAtImpact: float = 0.0
    VerticalFaceImpact: float = 0.0
    HorizontalFaceImpact: float = 0.0
    ClosureRate: float = 0.0


@dataclass
class ShotDataOptions:
    ContainsBallData: bool = True
    ContainsClubData: bool = False
    LaunchMonitorIsReady: bool = True
    LaunchMonitorBallDetected: bool = True
    IsHeartBeat: bool = False


@dataclass
class ShotPayload:
    DeviceID: str
    Units: str
    ShotNumber: int
    APIversion: str  # string "1", not int (per spec)
    BallData: BallData = field(default_factory=BallData)
    ClubData: ClubData = field(default_factory=ClubData)
    ShotDataOptions: ShotDataOptions = field(default_factory=ShotDataOptions)


@dataclass
class GSProResponse:
    Code: int
    Message: str = ""
    Player: Optional[dict] = None


def serialize_payload(payload: ShotPayload) -> bytes:
    return json.dumps(asdict(payload), separators=(",", ":")).encode("utf-8")


def build_heartbeat(device_id: str, units: str, shot_number: int) -> bytes:
    payload = ShotPayload(
        DeviceID=device_id,
        Units=units,
        ShotNumber=shot_number,
        APIversion="1",
        ShotDataOptions=ShotDataOptions(
            ContainsBallData=False,
            ContainsClubData=False,
            LaunchMonitorIsReady=True,
            LaunchMonitorBallDetected=False,
            IsHeartBeat=True,
        ),
    )
    return serialize_payload(payload)


def parse_response(raw: bytes) -> GSProResponse:
    """Parse a GSPro reply. Raises ValueError on malformed JSON."""
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Malformed GSPro response: {e}") from e
    return GSProResponse(
        Code=int(obj.get("Code", 0)),
        Message=str(obj.get("Message", "")),
        Player=obj.get("Player"),
    )
