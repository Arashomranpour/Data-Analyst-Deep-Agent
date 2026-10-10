"""Publish this app to a Hugging Face Space (Docker SDK).

    hf auth login                                   # once, with a *write* token
    python scripts/deploy_hf.py <your-username>/data-analyst-deep-agent
    python scripts/deploy_hf.py <you>/<space> --dry-run     # show what would be uploaded

Only what the app needs to run is uploaded (no tests, .env, user data, graph or Claude config). The Space is
configured as a public demo where every visitor brings their own Groq key: the host key is never set,
saved sessions are off (they would be shared between visitors) and sign-in is off.
"""

import argparse
import os
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# fnmatch-style, exactly as huggingface_hub applies them (so `*` also crosses `/`).
INCLUDE = [
    "analyst/*",
    "streamlit_app.py",
    "requirements.txt",
    "Dockerfile",
    ".streamlit/*",
    "docs/screenshot.png",
]
EXCLUDE = ["*__pycache__*", "*.pyc"]
_SKIP_DIRS = {".venv", ".git", "__pycache__", "node_modules", ".sessions", ".data", "graphify-out", "tests"}

# Streamlit inside the Spaces iframe: XSRF protection would block CSV uploads (403).
SPACE_VARIABLES = {
    "LLM_BACKEND": "groq",
    "ALLOW_SERVER_KEY": "false",
    "ENABLE_SESSION_SAVE": "false",
    "AUTH_ENABLED": "false",
    "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION": "false",
    "STREAMLIT_SERVER_ENABLE_CORS": "false",
}

FRONT_MATTER = """---
title: Data Analyst Deep Agent
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 8501
pinned: false
short_description: Multi-agent data analyst with Guardrails AI
---

"""


def build_readme(readme_text: str) -> str:
    """The Space README is the project README with the YAML header Spaces require."""
    body = readme_text.lstrip("﻿")
    if body.startswith("---"):  # already has a header
        return body
    return FRONT_MATTER + body


def files_to_upload(root: Path = ROOT) -> list[str]:
    """Relative POSIX paths that would be uploaded (README is added separately)."""
    found = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in names:
            relative = (Path(folder) / name).relative_to(root).as_posix()
            if any(fnmatch(relative, pattern) for pattern in INCLUDE) and not relative.endswith(".pyc"):
                found.append(relative)
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("space", help="<username>/<space-name>")
    parser.add_argument("--dry-run", action="store_true", help="list the files and stop")
    parser.add_argument("--private", action="store_true", help="create the Space as private")
    args = parser.parse_args(argv)

    files = files_to_upload()
    if args.dry_run:
        print(f"Would publish https://huggingface.co/spaces/{args.space} with {len(files) + 1} files:")
        print("\n".join(f"  {f}" for f in ["README.md (with Spaces header)", *files]))
        print("Space variables:", ", ".join(f"{k}={v}" for k, v in SPACE_VARIABLES.items()))
        return 0

    from huggingface_hub import HfApi
    from huggingface_hub.errors import HfHubHTTPError

    api = HfApi()
    try:
        who = api.whoami()["name"]
    except Exception:
        print("Not logged in to Hugging Face. Run `hf auth login` with a WRITE token first.", file=sys.stderr)
        return 1
    print(f"Signed in as {who}.")

    try:
        api.create_repo(
            args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True
        )
        for key, value in SPACE_VARIABLES.items():
            api.add_space_variable(args.space, key, value)
        api.upload_file(
            path_or_fileobj=build_readme((ROOT / "README.md").read_text(encoding="utf-8")).encode("utf-8"),
            path_in_repo="README.md",
            repo_id=args.space,
            repo_type="space",
            commit_message="Update README",
        )
        api.upload_folder(
            folder_path=str(ROOT),
            repo_id=args.space,
            repo_type="space",
            allow_patterns=INCLUDE,
            ignore_patterns=EXCLUDE,
            commit_message="Deploy Data Analyst Deep Agent",
        )
    except HfHubHTTPError as exc:
        print(f"Hugging Face refused the request: {exc}", file=sys.stderr)
        return 1

    print(f"Done. The Space builds now: https://huggingface.co/spaces/{args.space}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
