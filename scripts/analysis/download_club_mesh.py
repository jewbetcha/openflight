"""Acquire and normalize the club meshes without vendoring them.

The 7-iron used by this research is a GrabCAD community model. It is not
redistributed, so you fetch your own copy under GrabCAD's terms and point this
script at it; see SOURCES.md for the link, the expected SHA-256 and the licence
position. Run from the repository root:

    uv run python scripts/analysis/download_club_mesh.py \n        --local-iron "/path/to/690CB 7-iron.STL"

"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from openflight.camera.clubpose.mesh import (  # noqa: E402
    ACTIVE_MESH_SOURCES,
    CATEGORY_DIMENSIONS_MM,
    MESH_SOURCES,
    MeshSource,
    admit_mesh,
    default_mesh_asset_root,
    detect_face_plane,
    face_detection_record,
    load_binary_stl,
    load_normalized_mesh,
    normalize_clubhead,
    save_normalized_mesh,
)

_NORMALIZATION_VERSION = "geometric-face-anchor-v2"


def validate_source_metadata(source: MeshSource, metadata: dict[str, Any]) -> None:
    """Fail closed if identity, author, download status, or license drifted."""
    if str(metadata.get("uid")) != source.uid or str(metadata.get("name")) != source.name:
        raise ValueError(f"source identity changed for {source.club}")
    if not bool(metadata.get("isDownloadable")):
        raise ValueError(f"source is no longer downloadable for {source.club}")
    author = str(metadata.get("user", {}).get("displayName", ""))
    if author != source.author:
        raise ValueError(f"source author changed for {source.club}: {author!r}")
    license_payload = metadata.get("license", {})
    license_url = str(license_payload.get("url", "")).replace("http://", "https://")
    if str(license_payload.get("label")) != "CC Attribution" or license_url.rstrip(
        "/"
    ) != source.license_url.rstrip("/"):
        raise ValueError(f"source license changed for {source.club}")


def import_local_stl(
    source_path: Path | str,
    output_root: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Import the registered maintainer-local 7-iron without copying its STL."""
    source = MESH_SOURCES["poc_7iron"]
    registered_hash = source.expected_source_sha256
    if expected_sha256 is not None and registered_hash is not None:
        if expected_sha256.lower() != registered_hash.lower():
            raise ValueError("caller SHA-256 does not match the frozen local-source registration")
    required_hash = expected_sha256 or registered_hash
    loaded = load_binary_stl(source_path, source_uid=source.uid, expected_sha256=required_hash)
    admission = admit_mesh(
        loaded,
        category_dimensions_mm=CATEGORY_DIMENSIONS_MM[source.club],
        source_units_mm=True,
    )
    if not admission.accepted:
        raise ValueError(f"mesh admission failed for {source.club}: {admission.reasons}")
    assert admission.face is not None
    normalized = normalize_clubhead(
        loaded,
        CATEGORY_DIMENSIONS_MM[source.club],
        source_units_mm=True,
    )
    normalized_face = detect_face_plane(normalized)
    asset_metadata = {
        "source_uid": source.uid,
        "source_name": source.name,
        "author": source.author,
        "page_url": source.page_url,
        "license_spdx": source.license_spdx,
        "license_url": source.license_url,
        "source_file_sha256": loaded.source_sha256,
        "download_format": "binary_stl_maintainer_local",
        "redistribution": "prohibited; local research use only",
        "normalization": _NORMALIZATION_VERSION,
        "source_units_mm": True,
        "category_dimensions_mm": CATEGORY_DIMENSIONS_MM[source.club],
        "geometry_sha256": admission.geometry_sha256,
        "component_count_after_weld": admission.component_count,
        "boundary_edge_count_after_weld": admission.boundary_edge_count,
        "boundary_edge_fraction_after_weld": admission.boundary_edge_fraction,
        "dimensions_before_normalization_mm": admission.dimensions_mm,
        "face_detection_source": face_detection_record(admission.face),
        "face_detection_normalized": face_detection_record(normalized_face),
        "source_vertex_count": int(len(loaded.vertices_local_mm)),
        "source_triangle_count": int(len(loaded.faces)),
        "clubhead_vertex_count": int(len(normalized.vertices_local_mm)),
        "clubhead_triangle_count": int(len(normalized.faces)),
        "trademark_note": "synthetic truth only; no Titleist endorsement implied",
    }
    asset_path = output_root / f"{source.club}.npz"
    asset_sha256 = save_normalized_mesh(asset_path, normalized, asset_metadata)
    record = {**asset_metadata, "asset_path": asset_path.name, "asset_sha256": asset_sha256}
    print(json.dumps(record, indent=2, sort_keys=True))
    return record


def _existing_record(source: MeshSource, output_root: Path) -> dict[str, Any] | None:
    asset_path = output_root / f"{source.club}.npz"
    if not asset_path.is_file():
        return None
    mesh, metadata, asset_sha256 = load_normalized_mesh(str(asset_path.resolve()))
    if mesh.source_uid != source.uid:
        raise ValueError(f"cached source identity mismatch for {source.club}")
    if source.expected_source_sha256 is not None and (
        mesh.source_sha256 != source.expected_source_sha256
    ):
        raise ValueError(f"cached source SHA-256 mismatch for {source.club}")
    if source.expected_asset_sha256 is not None and (asset_sha256 != source.expected_asset_sha256):
        raise ValueError(f"cached asset SHA-256 mismatch for {source.club}")
    if metadata.get("normalization") != _NORMALIZATION_VERSION:
        return None
    return {**metadata, "asset_path": asset_path.name, "asset_sha256": asset_sha256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_mesh_asset_root())
    parser.add_argument("--local-iron", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    iron = ACTIVE_MESH_SOURCES["poc_7iron"]
    iron_record = _existing_record(iron, args.output)
    if iron_record is None:
        if args.local_iron is None:
            parser.error("--local-iron is required to import the missing maintainer-local 690CB")
        stl = Path(args.local_iron).expanduser()
        if not stl.is_file():
            parser.error(
                f"no STL at {stl}. Fetch the 690CB 7-iron from the GrabCAD page in "
                "src/openflight/camera/clubpose/meshes/SOURCES.md (free account, "
                "their terms) and point --local-iron at the downloaded file."
            )
        iron_record = import_local_stl(stl, args.output)
    records = [iron_record]
    (args.output / "manifest.json").write_text(
        json.dumps(
            {
                "sources": records,
                "retired_sources": [
                    {
                        "club": source.club,
                        "source_uid": source.uid,
                        "status": source.status,
                        "reason": source.status_reason,
                    }
                    for source in MESH_SOURCES.values()
                    if source.status != "active"
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    (admit_mesh,)
    (detect_face_plane,)
    (face_detection_record,)
