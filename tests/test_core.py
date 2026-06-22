import numpy as np
import pytest
from core import load_rgb, frame_stats, sg_smooth, find_segments, correction_factors


def test_load_rgb_returns_float32(sample_dir):
    paths = sorted(sample_dir.glob("*.jpg"))
    rgb = load_rgb(str(paths[0]))
    assert rgb.dtype == np.float32
    assert rgb.ndim == 3 and rgb.shape[2] == 3


def test_frame_stats_returns_three_values(sample_dir):
    paths = sorted(sample_dir.glob("*.jpg"))
    rgb = load_rgb(str(paths[0]))
    lum, sat, ch = frame_stats(rgb)
    assert isinstance(lum, float)
    assert 0.0 <= sat <= 1.0
    assert ch.shape == (3,)


def test_sg_smooth_returns_same_length():
    vals = np.array([1.0, 2.0, 1.5, 2.5, 1.0, 2.0, 1.8])
    result = sg_smooth(vals, window=5)
    assert len(result) == len(vals)


def test_sg_smooth_too_short_returns_copy():
    vals = np.array([1.0, 2.0])
    result = sg_smooth(vals, window=11)
    np.testing.assert_array_equal(result, vals)


def test_find_segments_single():
    modes = ["color", "color", "ir", "ir", "color"]
    segs = find_segments(modes)
    assert segs == [(0, 2, "color"), (2, 4, "ir"), (4, 5, "color")]


def test_correction_factors_shape():
    vals = np.array([200.0, 210.0, 190.0, 205.0, 195.0])
    cf = correction_factors(vals, window=5)
    assert cf.shape == vals.shape
    assert np.all(cf > 0)
