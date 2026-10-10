"""The Hugging Face deploy helper: README header and what gets uploaded (no network)."""

from scripts import deploy_hf


def test_space_readme_gets_the_required_header():
    text = deploy_hf.build_readme("<div>hello</div>")
    assert text.startswith("---\n") and "sdk: docker" in text and "app_port: 8501" in text
    assert text.rstrip().endswith("<div>hello</div>")
    assert len(deploy_hf.FRONT_MATTER.split("short_description: ")[1].split("\n")[0]) <= 60
    assert deploy_hf.build_readme("---\ntitle: x\n---\nbody").count("sdk: docker") == 0  # kept as is


def test_only_runtime_files_are_published():
    files = deploy_hf.files_to_upload()
    assert {"streamlit_app.py", "requirements.txt", "Dockerfile", "analyst/config.py"} <= set(files)
    for forbidden in (".env", "CLAUDE.md"):
        assert forbidden not in files
    assert not any(
        f.startswith(("tests/", ".claude/", "graphify-out/", ".sessions/", ".data/", ".venv/")) for f in files
    )
    assert not any("__pycache__" in f for f in files)


def test_public_demo_never_gets_the_host_key_or_shared_sessions():
    v = deploy_hf.SPACE_VARIABLES
    assert v["ALLOW_SERVER_KEY"] == "false" and v["ENABLE_SESSION_SAVE"] == "false"
    assert not any("KEY" in k and "ALLOW" not in k for k in v)


def test_dry_run_lists_files_without_touching_the_network(capsys):
    assert deploy_hf.main(["someone/demo", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "someone/demo" in out and "streamlit_app.py" in out
