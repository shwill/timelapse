import pytest
from datetime import date
from pathlib import Path
from models import GrowConfig, Phase, Note
from encoder import encode, build_note_frame_map


def test_build_note_frame_map(sample_dir):
    from scheduler import build_frame_schedule, parse_frame_timestamp
    paths = sorted(sample_dir.glob("*.jpg"))
    cfg = GrowConfig(normal_fps=24, phases=[
        Phase(name="Seedling", abbr="SEED", start=date(2026, 5, 1)),
    ], notes=[
        Note(text="Test note", start=date(2026, 5, 1), duration_s=2.0),
    ])
    schedule = build_frame_schedule(paths, cfg)
    note_map = build_note_frame_map(cfg, schedule)
    assert "Test note" in note_map
    start_f, end_f = note_map["Test note"]
    assert start_f == 0
    assert end_f == pytest.approx(48, abs=2)  # 2s × 24fps


def test_encode_produces_output_file(sample_dir, tmp_path):
    cfg = GrowConfig(normal_fps=24, phases=[
        Phase(name="Seedling", abbr="SEED", start=date(2026, 5, 1)),
    ])
    output = tmp_path / "out.mp4"
    paths = sorted(sample_dir.glob("*.jpg"))
    encode(paths, cfg, str(output), deflicker_window=3, denoise=False, preset="ultrafast")
    assert output.exists()
    assert output.stat().st_size > 1000
