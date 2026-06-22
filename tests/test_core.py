import numpy as np
import pytest
from pathlib import Path
from core import (
    load_rgb,
    frame_stats,
    sg_smooth,
    find_segments,
    correction_factors,
    compute_corrections,
    desaturation_ramp,
    load_cache,
    save_cache,
)


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


def test_compute_corrections_identity():
    """When all luminance values are equal, correction factors should be ~1.0."""
    n = 10
    lums = np.full(n, 150.0)
    ch_means = np.ones((n, 3)) * 0.5
    modes = ["color"] * n
    segs = [(0, n, "color")]
    lum_corr, wb_corr = compute_corrections(lums, ch_means, modes, segs, window=5, use_wb=True)
    np.testing.assert_allclose(lum_corr, 1.0, atol=0.01)
    np.testing.assert_allclose(wb_corr, 1.0, atol=0.01)


def test_desaturation_ramp_all_color_no_ir():
    """All-color modes (no IR) → desat array should be all zeros."""
    modes = ["color"] * 5
    segs = [(0, 5, "color")]
    result = desaturation_ramp(modes, segs, blend=2)
    assert result.shape == (5,)
    np.testing.assert_array_equal(result, 0.0)


def test_desaturation_ramp_ir_to_color_ramps_in():
    """Transition from IR → color should ramp desat from 1.0 → 0.0 at segment start."""
    modes = ["ir", "ir", "color", "color", "color"]
    segs = [(0, 2, "ir"), (2, 5, "color")]
    result = desaturation_ramp(modes, segs, blend=3)
    # At the start of the color segment (frame 2), desat should be ~1.0 (fully desaturated)
    assert result[2] == pytest.approx(1.0, abs=0.01)
    # At the end of the color segment (frame 4), desat should be ~0.0 (fully saturated)
    assert result[4] == pytest.approx(0.0, abs=0.01)


def test_cache_roundtrip(tmp_path):
    """save_cache then load_cache should return the same data."""
    d = Path(tmp_path)
    cache = {
        "frame1.jpg": (150.5, 0.35, np.array([0.6, 0.55, 0.4])),
        "frame2.jpg": (200.0, 0.10, np.array([0.45, 0.45, 0.45])),
    }
    save_cache(d, cache)
    loaded = load_cache(d)
    assert set(loaded.keys()) == set(cache.keys())
    for name in cache:
        lum0, sat0, ch0 = cache[name]
        lum1, sat1, ch1 = loaded[name]
        assert lum1 == pytest.approx(lum0, abs=0.01)
        assert sat1 == pytest.approx(sat0, abs=0.0001)
        np.testing.assert_allclose(ch1, ch0, atol=0.0001)
