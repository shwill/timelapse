import json
import pytest
from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def cam_dir(tmp_path):
    cam = tmp_path / "growcam"
    cam.mkdir()
    from tests.conftest import make_frame
    make_frame(cam, "2026-05-01_06-00-00.jpg")
    make_frame(cam, "2026-05-01_06-05-00.jpg")
    return tmp_path


@pytest.fixture
def client(cam_dir, monkeypatch):
    monkeypatch.setenv("TIMELAPSE_DATA_DIR", str(cam_dir))
    monkeypatch.setenv("TIMELAPSE_OUTPUT_DIR", str(cam_dir / "timelapses"))
    from app import build_app
    app = build_app()
    return TestClient(app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_list_cameras(client):
    r = client.get("/api/cameras")
    assert r.status_code == 200
    cams = r.json()["cameras"]
    assert any(c["name"] == "growcam" for c in cams)


def test_get_config_default(client):
    r = client.get("/api/cameras/growcam/config")
    assert r.status_code == 200
    body = r.json()
    assert "phases" in body
    assert "normal_fps" in body


def test_put_config_roundtrip(client):
    cfg = {
        "normal_fps": 24,
        "phases": [{"name": "Seedling", "abbr": "SEED", "start": "2026-05-01"}],
        "slow_zones": [],
        "notes": [],
    }
    r = client.put("/api/cameras/growcam/config", json=cfg)
    assert r.status_code == 200
    r2 = client.get("/api/cameras/growcam/config")
    assert r2.json()["phases"][0]["name"] == "Seedling"


def test_list_frames(client):
    r = client.get("/api/cameras/growcam/frames")
    assert r.status_code == 200
    frames = r.json()["frames"]
    assert len(frames) == 2
    assert frames[0].endswith(".jpg")


def test_unknown_camera_404(client):
    r = client.get("/api/cameras/nope/config")
    assert r.status_code == 404
