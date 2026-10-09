import os

# Guardrails AI exports telemetry by default; this app keeps everything local.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
