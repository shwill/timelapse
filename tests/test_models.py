import pytest
from datetime import date
from models import GrowConfig, Phase, SlowZone, Note, PHASE_PRESETS


def test_grow_config_start_date_from_first_phase():
    cfg = GrowConfig(normal_fps=24, phases=[
        Phase(name="Seedling", abbr="SEED", start=date(2026, 5, 1)),
        Phase(name="Vegetative", abbr="VEG", start=date(2026, 5, 13)),
    ])
    assert cfg.start_date == date(2026, 5, 1)


def test_phase_end_is_next_phase_start(sample_config):
    ends = [p.end_date(sample_config.phases) for p in sample_config.phases]
    assert ends[0] == date(2026, 5, 13)
    assert ends[1] == date(2026, 6, 12)
    assert ends[2] is None  # last phase has no end


def test_week_number_day_0_is_week_1(sample_config):
    p = sample_config.phases[1]  # Vegetative starts 2026-05-13
    assert p.week_number(date(2026, 5, 13)) == 1
    assert p.week_number(date(2026, 5, 19)) == 1
    assert p.week_number(date(2026, 5, 20)) == 2


def test_slow_zone_requires_end_after_start():
    with pytest.raises(Exception):
        SlowZone(label="x", start=date(2026, 5, 10), end=date(2026, 5, 9), fps=3,
                 ramp_in_s=4, ramp_out_s=4)


def test_grow_config_roundtrip_json(sample_config):
    j = sample_config.model_dump_json()
    cfg2 = GrowConfig.model_validate_json(j)
    assert cfg2.start_date == sample_config.start_date


def test_phase_presets_contains_required():
    names = [p["name"] for p in PHASE_PRESETS]
    assert "Seedling" in names
    assert "Vegetative" in names
    assert "Bloom" in names


@pytest.fixture
def sample_config():
    return GrowConfig(normal_fps=24, phases=[
        Phase(name="Seedling",   abbr="SEED",  start=date(2026, 5, 1)),
        Phase(name="Vegetative", abbr="VEG",   start=date(2026, 5, 13)),
        Phase(name="Bloom",      abbr="BLOOM", start=date(2026, 6, 12)),
    ], slow_zones=[
        SlowZone(label="Intro", start=date(2026, 5, 10), end=date(2026, 5, 12),
                 fps=3, ramp_in_s=4.0, ramp_out_s=4.0),
    ], notes=[
        Note(text="Autopot switched on", start=date(2026, 5, 18), duration_s=4),
    ])
