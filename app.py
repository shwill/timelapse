from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from models import GrowConfig

STATIC_DIR = Path(__file__).parent / "static"


def build_app() -> FastAPI:
    data_dir = Path(os.environ.get("TIMELAPSE_DATA_DIR", "/data"))
    output_dir = Path(os.environ.get("TIMELAPSE_OUTPUT_DIR", "/data/timelapses"))

    app = FastAPI(title="Timelapse Editor")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    def _cam_dir(cam: str) -> Path:
        p = (data_dir / cam).resolve()
        if not p.is_dir() or not p.is_relative_to(data_dir.resolve()):
            raise HTTPException(404, f"Camera '{cam}' not found")
        return p

    @app.get("/api/cameras")
    def list_cameras():
        cams = [
            {
                "name": d.name,
                "frame_count": len(list(d.glob("*.jpg"))) + len(list(d.glob("*.webp"))),
            }
            for d in sorted(data_dir.iterdir())
            if d.is_dir() and d.name != "timelapses"
        ]
        return {"cameras": cams}

    @app.get("/api/cameras/{cam}/config")
    def get_config(cam: str):
        cam_dir = _cam_dir(cam)
        cfg_file = cam_dir / "grow.json"
        if cfg_file.exists():
            return GrowConfig.model_validate_json(cfg_file.read_text()).model_dump(mode="json")
        return GrowConfig().model_dump(mode="json")

    @app.put("/api/cameras/{cam}/config")
    def put_config(cam: str, body: GrowConfig):
        cam_dir = _cam_dir(cam)
        (cam_dir / "grow.json").write_text(body.model_dump_json(indent=2))
        return {"ok": True}

    @app.get("/api/cameras/{cam}/frames")
    def list_frames(cam: str):
        cam_dir = _cam_dir(cam)
        frames = sorted(
            p.name for p in cam_dir.iterdir()
            if p.suffix.lower() in (".jpg", ".jpeg", ".webp")
        )
        return {"frames": frames}

    @app.get("/api/cameras/{cam}/frames/{filename}")
    def serve_frame(cam: str, filename: str):
        cam_dir = _cam_dir(cam)
        p = (cam_dir / filename).resolve()
        if not p.exists() or not p.is_relative_to(cam_dir):
            raise HTTPException(404)
        return FileResponse(str(p))

    @app.get("/api/cameras/{cam}/encode")
    def trigger_encode(cam: str, date: str | None = None, preset: str = "medium"):
        cam_dir = _cam_dir(cam)
        cfg_file = cam_dir / "grow.json"
        if not cfg_file.exists():
            raise HTTPException(400, "No grow.json configured for this camera")
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{cam}_{date or 'full'}.mp4"

        def stream():
            import encoder

            cfg = GrowConfig.model_validate_json(cfg_file.read_text())
            paths = sorted(
                p for p in cam_dir.iterdir()
                if p.suffix.lower() in (".jpg", ".jpeg", ".webp")
                and (not date or p.name.startswith(date))
            )
            total = len(paths)
            yield f"data: {json.dumps({'status': 'starting', 'total': total})}\n\n"

            try:
                encoder.encode(paths, cfg, str(out), denoise=True, preset=preset)
                yield f"data: {json.dumps({'status': 'done', 'output': out.name})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--editor", action="store_true")
    ap.add_argument("--encode", action="store_true")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--date")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--no-denoise", action="store_true")
    args = ap.parse_args()

    data_dir = Path(os.environ.get("TIMELAPSE_DATA_DIR", "/data"))
    output_dir = Path(os.environ.get("TIMELAPSE_OUTPUT_DIR", "/data/timelapses"))

    if args.editor:
        import uvicorn
        app = build_app()
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.encode:
        import encoder

        output_dir.mkdir(parents=True, exist_ok=True)
        for cam_dir in sorted(data_dir.iterdir()):
            if not cam_dir.is_dir() or cam_dir.name == "timelapses":
                continue
            cam = cam_dir.name
            cfg_file = cam_dir / "grow.json"
            cfg = GrowConfig.model_validate_json(cfg_file.read_text()) if cfg_file.exists() else GrowConfig(phases=[])

            paths = sorted(
                p for p in cam_dir.iterdir()
                if p.suffix.lower() in (".jpg", ".jpeg", ".webp")
                and (not args.date or p.name.startswith(args.date))
            )
            if not paths:
                print(f"[{cam}] No frames found, skipping")
                continue

            out = output_dir / f"{cam}_{args.date or 'full'}.mp4"
            print(f"[{cam}] Encoding {len(paths)} frames → {out}")
            encoder.encode(paths, cfg, str(out), denoise=not args.no_denoise, preset=args.preset)
            print(f"[{cam}] Done")

    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
