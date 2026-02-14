"""Local wrapper for whisper.cpp transcription."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Iterable

TMP_DIR = pathlib.Path(os.getenv("BLACKROAD_TRANSCRIBE_TMP", "/tmp/blackroad_whisper"))
TMP_DIR.mkdir(parents=True, exist_ok=True)


def save_upload(data: bytes, suffix: str = ".wav") -> str:
    """Persist uploaded ``data`` to a temporary file and return its path."""
    with tempfile.NamedTemporaryFile(delete=False, dir=TMP_DIR, suffix=suffix) as handle:
        handle.write(data)
        return handle.name


def run_whisper_stream(
    audio_path: str,
    *,
    model_path: str | None = None,
    lang: str = "en",
) -> Iterable[str]:
    """Invoke ``whisper.cpp`` and yield decoded lines as they stream."""
    exe = shutil.which("whisper") or shutil.which("main")
    if not exe:
        yield "[error] whisper.cpp binary not found"
        return

    resolved_model = model_path or "/var/lib/blackroad/models/ggml-base.en.bin"
    cmd = [exe, "-m", resolved_model, "-l", lang, audio_path]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        if proc.stdout is None:
            yield "[error] failed to capture whisper output"
            return

        for line in proc.stdout:
            yield line.rstrip("\n")
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()


def run_whisper(audio_path: str, model_path: str | None = None, lang: str = "en") -> str:
    """Run whisper.cpp binary against the provided audio file."""
    exe = shutil.which("whisper") or shutil.which("main")
    if not exe:
        return "[error] whisper.cpp binary not found"

    audio_file = pathlib.Path(audio_path).expanduser()
    if not audio_file.exists():
        return "[error] audio file not found"

    model_path = model_path or "/var/lib/blackroad/models/ggml-base.en.bin"
    cmd = [exe, "-m", model_path, "-l", lang, str(audio_file)]

    try:
        out = subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.STDOUT,
            cwd=tempfile.gettempdir(),
        )
        return out
    except subprocess.CalledProcessError as exc:
        return f"[error] {exc.output}"


__all__ = ["TMP_DIR", "save_upload", "run_whisper_stream", "run_whisper"]
