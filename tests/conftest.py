import numpy as np
import pytest
from pathlib import Path
from PIL import Image


def make_frame(tmp_path: Path, name: str, color=(100, 120, 80)) -> Path:
    """Write a small solid-color JPEG with a grow-cam-style timestamp name."""
    img = Image.fromarray(np.full((270, 480, 3), color, dtype=np.uint8))
    p = tmp_path / name
    img.save(p, "JPEG")
    return p


@pytest.fixture
def sample_dir(tmp_path):
    """Three frames spanning 2026-05-01 in 5-min intervals."""
    make_frame(tmp_path, "2026-05-01_06-00-00.jpg", color=(100, 130, 80))
    make_frame(tmp_path, "2026-05-01_06-05-00.jpg", color=(105, 135, 82))
    make_frame(tmp_path, "2026-05-01_06-10-00.jpg", color=(110, 140, 85))
    return tmp_path


@pytest.fixture
def ir_dir(tmp_path):
    """Three grayscale (IR-like) frames."""
    for t in ["2026-05-01_00-00-00.jpg", "2026-05-01_00-05-00.jpg", "2026-05-01_00-10-00.jpg"]:
        make_frame(tmp_path, t, color=(118, 118, 118))
    return tmp_path
