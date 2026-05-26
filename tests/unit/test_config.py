"""Unit tests for guardrails.config."""

import os
import tempfile

import yaml

from guardrails.config import load_config


def test_load_config_returns_dict(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("validators:\n  toxicity:\n    enabled: true\n")
    cfg = load_config(path=str(cfg_file))
    assert isinstance(cfg, dict)
    assert "validators" in cfg


def test_env_var_expansion():
    os.environ["TEST_SCRUM7_KEY"] = "my-secret-value"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {"key": "${TEST_SCRUM7_KEY}", "nested": {"val": "${TEST_SCRUM7_KEY}"}},
                f,
            )
            path = f.name
        cfg = load_config(path=path)
        assert cfg["key"] == "my-secret-value"
        assert cfg["nested"]["val"] == "my-secret-value"
    finally:
        del os.environ["TEST_SCRUM7_KEY"]
        os.unlink(path)


def test_missing_file_returns_empty():
    cfg = load_config(path="/nonexistent/path/config.yaml")
    assert cfg == {}


def test_default_path_is_config_yaml(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("foo: bar\n")
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.get("foo") == "bar"


def test_env_var_unexpanded_when_not_set():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"key": "${DEFINITELY_NOT_SET_SCRUM7}"}, f)
        path = f.name
    try:
        cfg = load_config(path=path)
        # Unexpanded env var stays as-is
        assert cfg["key"] == "${DEFINITELY_NOT_SET_SCRUM7}"
    finally:
        os.unlink(path)
