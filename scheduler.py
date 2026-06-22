from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from models import GrowConfig, SlowZone


@dataclass
class FrameEntry:
    path: Path
    frame_dt: datetime
    hold_frames: int  # number of output frames to emit this source frame for
    output_t: float   # output-video time (seconds) when this entry starts


def parse_frame_timestamp(filename: str) -> datetime:
    stem = Path(filename).stem
    return datetime.strptime(stem, "%Y-%m-%d_%H-%M-%S")


def _cosine_ease(t: float) -> float:
    """t in [0,1] → smooth 0..1 via cosine."""
    return (1 - math.cos(math.pi * t)) / 2


def build_frame_schedule(paths: list[Path], config: GrowConfig) -> list[FrameEntry]:
    """
    Two-pass algorithm:
    Pass 1: classify each frame as normal/slow (no ramps), accumulate output_t.
            Record zone_start_output_t and zone_end_output_t for each slow zone.
    Pass 2: rebuild, applying cosine ramps around zone boundaries.
    """
    if not paths:
        return []

    frame_dts = [parse_frame_timestamp(p.name) for p in paths]

    def zone_for_dt(dt: datetime) -> SlowZone | None:
        d = dt.date()
        for z in config.slow_zones:
            if z.start <= d <= z.end:
                return z
        return None

    # Pass 1: find zone boundary output times
    zone_boundary_output_t: dict[int, dict] = {}  # zone_idx → {start_t, end_t}
    output_t = 0.0
    in_zone_idx: int | None = None

    for path, dt in zip(paths, frame_dts):
        z = zone_for_dt(dt)
        z_idx = config.slow_zones.index(z) if z else None

        if z_idx != in_zone_idx:
            if in_zone_idx is not None and in_zone_idx in zone_boundary_output_t:
                zone_boundary_output_t[in_zone_idx]["end_t"] = output_t
            if z_idx is not None:
                zone_boundary_output_t.setdefault(z_idx, {})["start_t"] = output_t
            in_zone_idx = z_idx

        fps = config.slow_zones[z_idx].fps if z_idx is not None else config.normal_fps
        hold = max(1, round(config.normal_fps / fps))
        output_t += hold / config.normal_fps

    if in_zone_idx is not None:
        zone_boundary_output_t.setdefault(in_zone_idx, {})["end_t"] = output_t

    # Pass 2: build schedule with ramps
    entries: list[FrameEntry] = []
    output_t = 0.0

    for path, dt in zip(paths, frame_dts):
        z = zone_for_dt(dt)
        z_idx = config.slow_zones.index(z) if z else None

        # Determine effective fps considering ramps from any zone
        eff_fps = float(config.normal_fps)
        for zi, z_info in zone_boundary_output_t.items():
            sz: SlowZone = config.slow_zones[zi]
            start_t = z_info.get("start_t", float("inf"))
            end_t = z_info.get("end_t", float("inf"))

            ramp_in_start = max(0.0, start_t - sz.ramp_in_s)
            ramp_out_end = end_t + sz.ramp_out_s

            if ramp_in_start <= output_t < start_t and sz.ramp_in_s > 0:
                t = (output_t - ramp_in_start) / sz.ramp_in_s
                eff_fps = config.normal_fps + (sz.fps - config.normal_fps) * _cosine_ease(t)
            elif start_t <= output_t <= end_t:
                eff_fps = sz.fps
            elif end_t < output_t <= ramp_out_end and sz.ramp_out_s > 0:
                t = (output_t - end_t) / sz.ramp_out_s
                eff_fps = sz.fps + (config.normal_fps - sz.fps) * _cosine_ease(t)

        hold = max(1, round(config.normal_fps / eff_fps))
        entries.append(FrameEntry(path=path, frame_dt=dt, hold_frames=hold, output_t=output_t))
        output_t += hold / config.normal_fps

    return entries
