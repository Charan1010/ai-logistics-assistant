"""
Multimodal AI helpers for Feature 10.

Three modalities, all local:
  - Vision  → Ollama VLM (llava / phi3:vision / llava-phi3)
  - STT     → faster-whisper (local CPU, no network)
  - TTS     → gTTS (Google's public TTS endpoint, no API key)

detect_modality() mirrors the Feature 6 Anti-RAG pattern: inspect the request,
decide which pipeline to invoke, delegate. Same principle applied to input type.
"""
import asyncio
import base64
import io
import logging
import tempfile
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded singleton so we don't reload the ~150 MB base model on every request.
_whisper_model = None


# =============================================================================
# Modality detection (Feature 10 extension of the Anti-RAG router pattern)
# =============================================================================

def detect_modality(
    has_audio: bool = False,
    has_image: bool = False,
    text: str | None = None,
) -> str:
    """Return 'voice' | 'vision' | 'text' based on which inputs are present."""
    if has_audio:
        return "voice"
    if has_image:
        return "vision"
    return "text"


# =============================================================================
# Vision — Ollama VLM
# =============================================================================

async def analyze_image(
    image_bytes: bytes,
    prompt: str,
    detail: str = "auto",
) -> dict:
    """
    Send an image + prompt to an Ollama VLM. Returns {'answer', 'model'}.

    detail is accepted for API parity with cloud VLMs — Ollama ignores it.
    """
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": settings.vlm_model,
        "messages": [
            {"role": "user", "content": prompt, "images": [b64_image]},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=payload,
            )
            if response.status_code == 404:
                raise RuntimeError(
                    f"VLM model '{settings.vlm_model}' not pulled. "
                    f"Run: ollama pull {settings.vlm_model}"
                )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama VLM request failed: {exc}")

    answer = (data.get("message") or {}).get("content") or ""
    return {"answer": answer, "model": settings.vlm_model, "detail": detail}


# =============================================================================
# Voice — local Whisper via faster-whisper (no network)
# =============================================================================

def _get_whisper_model():
    """Lazy-load and cache the Whisper model.

    Accepts either a Hugging Face model ID (e.g. 'base') OR a local filesystem
    path. Behind corporate proxies that block Hugging Face Hub, pre-download the
    model with ModelScope:
        pip install modelscope
        python -c "from modelscope import snapshot_download; \\
                   print(snapshot_download('pengzhendong/faster-whisper-base'))"
    Then set WHISPER_MODEL_SIZE to the returned path in .env.
    """
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "The 'faster-whisper' package is not installed. "
                "Run: pip install faster-whisper"
            )
        logger.info("Loading faster-whisper model: %s", settings.whisper_model_size)
        try:
            _whisper_model = WhisperModel(
                settings.whisper_model_size,
                device="cpu",
                compute_type="int8",
            )
        except Exception as exc:
            msg = str(exc)
            if "outgoing traffic has been disabled" in msg or "HF_HUB_OFFLINE" in msg or "LocalEntryNotFound" in msg:
                raise RuntimeError(
                    f"Whisper model '{settings.whisper_model_size}' not cached and "
                    "Hugging Face Hub is unreachable. Download via ModelScope: "
                    "pip install modelscope && python -c "
                    "\"from modelscope import snapshot_download; "
                    "print(snapshot_download('pengzhendong/faster-whisper-base'))\" "
                    "Then set WHISPER_MODEL_SIZE=<returned_path> in .env."
                )
            raise RuntimeError(f"Failed to load Whisper model: {exc}")
    return _whisper_model


def _transcribe_sync(audio_bytes: bytes, filename: str) -> str:
    """CPU-bound transcription — runs in a thread pool via the async wrapper."""
    model = _get_whisper_model()
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, _info = model.transcribe(tmp_path, language=settings.whisper_language or None)
        return " ".join(seg.text for seg in segments).strip()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    """Convert audio bytes to text via local faster-whisper. Returns the transcript."""
    try:
        return await asyncio.to_thread(_transcribe_sync, audio_bytes, filename)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Whisper transcription failed: {exc}")


# =============================================================================
# Voice — TTS via gTTS (no API key, uses Google's public endpoint)
# =============================================================================

async def synthesize_speech(text: str, language: str | None = None) -> bytes:
    """Convert text to spoken audio (MP3 bytes) via gTTS."""
    try:
        from gtts import gTTS
    except ImportError:
        raise RuntimeError("The 'gTTS' package is not installed. Run: pip install gTTS")

    lang = language or settings.tts_language
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        buffer = io.BytesIO()
        tts.write_to_fp(buffer)
        return buffer.getvalue()
    except Exception as exc:
        raise RuntimeError(f"TTS synthesis failed: {exc}")
