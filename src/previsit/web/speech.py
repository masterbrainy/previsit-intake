"""Speech for intake replies, prepared in parallel with the scope guard (F.1).

The engine shows each AI utterance to `start()` before the guard checks it. Audio is only ever returned by
`audio_for(final_text)`, i.e. for the text the guard let through; if the guard replaced it, the prepared audio is
thrown away and the replacement is synthesised instead. So no unchecked reply can be played.
"""

import logging
from concurrent.futures import Future, ThreadPoolExecutor

from previsit.config import Settings
from previsit.voice import VoiceError, synthesize

logger = logging.getLogger(__name__)
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tts")


class SpeechPrefetch:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pending: dict[str, Future[bytes]] = {}

    def start(self, text: str) -> None:
        if text and text not in self._pending:
            self._pending[text] = _POOL.submit(synthesize, self._settings, text)

    def audio_for(self, final_text: str) -> bytes | None:
        if not final_text:
            return None
        future = self._pending.pop(final_text, None)
        for other in self._pending.values():
            other.cancel()
        try:
            return future.result() if future is not None else synthesize(self._settings, final_text)
        except VoiceError:
            logger.warning("Speech unavailable for this reply; sending text only")
            return None
