#!/usr/bin/env python3
"""Local speech-to-text helpers (ffmpeg + whisper.cpp)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path


def run_ffmpeg_convert(input_path: Path, output_path: Path) -> None:
    """Convert audio to 16 kHz mono WAV for whisper.cpp.

    Args:
        input_path: Source audio path (e.g. OGG).
        output_path: Destination WAV path.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def transcribe_local_whisper(
    ogg_path: Path,
    wav_path: Path,
    whisper_cli_path: str,
    whisper_model_path: str,
    stt_language: str,
) -> str:
    """Transcribe an OGG voice note with whisper-cli.

    Args:
        ogg_path: Downloaded Telegram voice file.
        wav_path: Temporary WAV path.
        whisper_cli_path: Path to whisper-cli binary.
        whisper_model_path: Path to GGML model.
        stt_language: Language code (e.g. ``it``).

    Returns:
        Transcript text, or empty string if no output file was produced.

    Raises:
        subprocess.CalledProcessError: If conversion or transcription fails.
    """
    run_ffmpeg_convert(ogg_path, wav_path)
    output_base = wav_path.with_suffix("")
    output_txt = output_base.with_suffix(".txt")
    if output_txt.exists():
        output_txt.unlink()
    command = [
        whisper_cli_path,
        "-m",
        whisper_model_path,
        "-f",
        str(wav_path),
        "-l",
        stt_language,
        "-otxt",
        "-of",
        str(output_base),
        "-np",
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        logging.error("whisper-cli failed (exit=%s): %s", exc.returncode, " ".join(command))
        if exc.stderr:
            logging.error("whisper-cli stderr: %s", exc.stderr.strip())
        raise
    if output_txt.exists():
        transcription = output_txt.read_text(encoding="utf-8").strip()
        output_txt.unlink(missing_ok=True)
        return transcription
    return ""
