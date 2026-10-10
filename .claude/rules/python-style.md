---
paths:
  - "**/*.py"
---
# Python style
- Python 3.12; ruff rules E,F,I,B,UP, line length 110 (E501 ignored). Run `ruff check .` before finishing.
- Use modern typing (`list[str]`, `X | None`), dataclasses for small records, pydantic-settings for config.
- Module docstring explains the module's role; comments explain the why, not the what.
- Config comes only from `analyst/config.py` `Settings`; don't read `os.environ` elsewhere.
