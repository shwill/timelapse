import numpy as np
import pytest
from datetime import date, datetime
from models import GrowConfig, Phase, Note
from overlay import bake_overlay, FADE_FRAMES


def make_rgb(h=270, w=480):
    return np.full((h, w, 3), 100, dtype=np.float32)


@pytest.fixture
def cfg():
    return GrowConfig(normal_fps=24, phases=[
        Phase(name="Seedling",   abbr="SEED",  start=date(2026, 5, 1)),
        Phase(name="Vegetative", abbr="VEG",   start=date(2026, 5, 13)),
        Phase(name="Bloom",      abbr="BLOOM", start=date(2026, 6, 12)),
    ], notes=[
        Note(text="Autopot switched on", start=date(2026, 5, 18), duration_s=4.0),
    ])


def test_bake_returns_same_shape(cfg):
    rgb = make_rgb()
    frame_dt = datetime(2026, 5, 20, 12, 0)
    result = bake_overlay(rgb, frame_dt, cfg, output_frame_idx=0, schedule_note_frames={})
    assert result.shape == rgb.shape
    assert result.dtype == np.uint8


def test_bake_modifies_bottom_bar_region(cfg):
    rgb = make_rgb()
    frame_dt = datetime(2026, 5, 20, 12, 0)
    result = bake_overlay(rgb, frame_dt, cfg, output_frame_idx=0, schedule_note_frames={})
    # Bottom area should differ from solid grey input
    bottom = result[int(0.85 * 270):, :, :]
    assert not np.all(bottom == 100)


def test_note_visible_at_start(cfg):
    rgb = make_rgb()
    frame_dt = datetime(2026, 5, 18, 12, 0)
    # note starts at frame 0, fully visible at frame FADE_FRAMES (past fade-in)
    note_frames = {"Autopot switched on": (0, 96)}  # start_frame, end_frame
    result = bake_overlay(rgb, frame_dt, cfg,
                          output_frame_idx=FADE_FRAMES + 1,
                          schedule_note_frames=note_frames)
    # Top area (note region) should differ from input
    top = result[:int(0.25 * 270), :, :]
    assert not np.all(top == 100)


def test_note_absent_outside_window(cfg):
    rgb = make_rgb()
    frame_dt = datetime(2026, 5, 18, 12, 0)
    note_frames = {"Autopot switched on": (0, 96)}
    result = bake_overlay(rgb, frame_dt, cfg,
                          output_frame_idx=200,  # well after note ends at 96
                          schedule_note_frames=note_frames)
    top = result[:int(0.25 * 270), :, :]
    # Top area should remain close to input (no note rendered)
    assert np.mean(np.abs(top.astype(float) - 100)) < 10
