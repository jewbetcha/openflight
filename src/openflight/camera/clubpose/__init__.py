"""Clubhead pose from the behind-ball camera and the radars.

This package lands in stages. This stage carries the geometry: the club mesh
(mesh), the camera model and silhouette projection (projection), and sub-pixel
location of the teed ball (teed_ball), which anchors the world frame. The pose
fit that consumes them follows, and nothing here is wired into the shot
pipeline yet. See docs/clubface-impact-location-report.md for what is
validated and what is not.
"""
