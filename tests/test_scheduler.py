import pytest
from datetime import date, datetime
from pathlib import Path
from models import GrowConfig, Phase, SlowZone
from scheduler import build_frame_schedule, FrameEntry, parse_frame_timestamp


def test_parse_frame_timestamp():
    dt = parse_frame_timestamp("2026-05-01_06-00-00.jpg")
    assert dt.year == 2026 and dt.month == 5 and dt.day == 1
    assert dt.hour == 6 and dt.minute == 0


def test_normal_speed_hold_is_one(tmp_path):
    # 3 frames, no slow zones → each held for 1 output frame
    paths = [tmp_path / f"2026-05-01_06-{m:02d}-00.jpg" for m in [0, 5, 10]]
    for p in paths:
        p.touch()
    cfg = GrowConfig(normal_fps=24, phases=[Phase(name="Seedling", abbr="SEED", start=date(2026, 5, 1))])
    schedule = build_frame_schedule(paths, cfg)
    assert all(e.hold_frames == 1 for e in schedule)


def test_slow_zone_increases_hold(tmp_path):
    # Frame inside slow zone (fps=6 vs normal 24) → hold = round(24/6) = 4
    paths = [tmp_path / "2026-05-10_12-00-00.jpg"]
    paths[0].touch()
    cfg = GrowConfig(
        normal_fps=24,
        phases=[Phase(name="Seedling", abbr="SEED", start=date(2026, 5, 1))],
        slow_zones=[SlowZone(label="x", start=date(2026, 5, 9), end=date(2026, 5, 11),
                             fps=6, ramp_in_s=0, ramp_out_s=0)],
    )
    schedule = build_frame_schedule(paths, cfg)
    assert schedule[0].hold_frames == 4


def test_output_t_accumulates_correctly(tmp_path):
    paths = [tmp_path / f"2026-05-01_06-{m:02d}-00.jpg" for m in [0, 5, 10]]
    for p in paths:
        p.touch()
    cfg = GrowConfig(normal_fps=24, phases=[Phase(name="Seedling", abbr="SEED", start=date(2026, 5, 1))])
    schedule = build_frame_schedule(paths, cfg)
    assert schedule[0].output_t == pytest.approx(0.0)
    assert schedule[1].output_t == pytest.approx(1 / 24)
    assert schedule[2].output_t == pytest.approx(2 / 24)


def test_ramp_interpolates_between_speeds(tmp_path):
    # 5 frames spanning the slow zone entry — hold values should not all be equal
    paths = [tmp_path / f"2026-05-{d:02d}_12-00-00.jpg" for d in [8, 9, 10, 11, 12]]
    for p in paths:
        p.touch()
    cfg = GrowConfig(
        normal_fps=24,
        phases=[Phase(name="Seedling", abbr="SEED", start=date(2026, 5, 1))],
        slow_zones=[SlowZone(label="x", start=date(2026, 5, 10), end=date(2026, 5, 11),
                             fps=6, ramp_in_s=1.0, ramp_out_s=1.0)],
    )
    schedule = build_frame_schedule(paths, cfg)
    holds = [e.hold_frames for e in schedule]
    # Should have varying hold counts due to ramp
    assert len(set(holds)) > 1
