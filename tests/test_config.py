import pytest

from collector.config import load_api_key, load_config


def test_load_config_loads_niches_and_bands():
    cfg = load_config("config.yaml")
    assert cfg.min_subs == 100000
    assert cfg.min_prior == 5
    assert cfg.max_videos == 200
    assert list(cfg.niches) == ["tech", "cooking", "gaming", "education"]
    assert cfg.bands[0] == (100000, 500000)


def test_load_api_key_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("YOUTUBE_API_KEY=abc123\n")
    assert load_api_key(str(env)) == "abc123"


def test_load_api_key_missing_raises(tmp_path):
    with pytest.raises(RuntimeError):
        load_api_key(str(tmp_path / "nope.env"))
