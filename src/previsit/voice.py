"""Speech-to-text and text-to-speech for the browser voice channel."""

import io
import logging

from previsit.config import Settings

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/mpeg": "mp3", "audio/wav": "wav"}


class VoiceError(RuntimeError):
    pass


def _client(settings: Settings):
    from openai import OpenAI

    key = settings.openai_api_key.get_secret_value()
    if not key:
        raise VoiceError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=key, timeout=45.0, max_retries=2)


def transcribe(settings: Settings, audio: bytes, mime: str) -> str:
    extension = AUDIO_EXTENSIONS.get(mime.split(";")[0].strip(), "webm")
    buffer = io.BytesIO(audio)
    buffer.name = f"turn.{extension}"
    try:
        result = _client(settings).audio.transcriptions.create(model=settings.transcribe_model, file=buffer)
    except Exception as exc:
        logger.exception("Transcription failed")
        raise VoiceError("Sorry, I couldn't hear that. Please try again or type your answer.") from exc
    return result.text.strip()


def synthesize(settings: Settings, text: str) -> bytes:
    try:
        response = _client(settings).audio.speech.create(
            model=settings.tts_model,
            voice=settings.tts_voice,
            input=text,
            instructions="Speak calmly and warmly, at a steady pace, like a kind clinic nurse.",
            response_format="mp3",
        )
    except Exception as exc:
        logger.exception("Speech synthesis failed")
        raise VoiceError("speech synthesis failed") from exc
    return response.read()
