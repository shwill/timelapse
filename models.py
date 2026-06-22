from __future__ import annotations
from datetime import date
from typing import Optional
import math
from pydantic import BaseModel, model_validator

PHASE_PRESETS = [
    {"name": "Seedling",    "abbr": "SEED"},
    {"name": "Vegetative",  "abbr": "VEG"},
    {"name": "Bloom",       "abbr": "BLOOM"},
]


class Phase(BaseModel):
    name: str
    abbr: str
    start: date

    def end_date(self, all_phases: list[Phase]) -> Optional[date]:
        idx = next(i for i, p in enumerate(all_phases) if p.start == self.start)
        return all_phases[idx + 1].start if idx + 1 < len(all_phases) else None

    def week_number(self, frame_date: date) -> int:
        return math.floor((frame_date - self.start).days / 7) + 1


class SlowZone(BaseModel):
    label: str
    start: date
    end: date
    fps: float
    ramp_in_s: float
    ramp_out_s: float

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end <= self.start:
            raise ValueError("slow zone end must be after start")
        return self


class Note(BaseModel):
    text: str
    start: date
    duration_s: float


class GrowConfig(BaseModel):
    start_date: Optional[date] = None
    normal_fps: int = 24
    phases: list[Phase] = []
    slow_zones: list[SlowZone] = []
    notes: list[Note] = []

    @model_validator(mode="after")
    def derive_start_date(self):
        if self.phases:
            self.start_date = self.phases[0].start
        return self

    def phase_for_date(self, d: date) -> Optional[Phase]:
        active = None
        for p in self.phases:
            if p.start <= d:
                active = p
        return active
