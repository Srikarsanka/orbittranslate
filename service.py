import os
import uuid
import tempfile
import subprocess
import requests
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
from gtts import gTTS

# Language code mapping — deep_translator uses different codes than BCP-47
LANG_MAP = {
    "en": "english",
    "hi": "hindi",
    "te": "telugu",
    "ta": "tamil",
    "ml": "malayalam",
    "kn": "kannada",
    "fr": "french",
    "de": "german",
    "es": "spanish",
    "zh": "chinese (simplified)",
    "ar": "arabic",
    "ja": "japanese",
    "ko": "korean",
    "ru": "russian",
    "pt": "portuguese",
    "it": "italian",
}

# gTTS language codes (different from deep_translator)
GTTS_LANG_MAP = {
    "en": "en",
    "hi": "hi",
    "te": "te",
    "ta": "ta",
    "ml": "ml",
    "kn": "kn",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "zh": "zh",
    "ar": "ar",
    "ja": "ja",
    "ko": "ko",
    "ru": "ru",
    "pt": "pt",
    "it": "it",
}

_model_instance = None


def get_whisper_model() -> WhisperModel:
    """Lazy-load the Whisper model (singleton) so it's only loaded once."""
    global _model_instance
    if _model_instance is None:
        print("Loading Whisper 'small' model (better multilingual support)...")
        _model_instance = WhisperModel("small", device="cpu", compute_type="int8")
        print("Whisper model loaded.")
    return _model_instance


class VoiceTranslationService:

    @staticmethod
    def download_video(video_url: str) -> str:
        """Download a video/audio from a URL and save to a temp file. Returns local path."""
        suffix = ".webm"
        if ".mp4" in video_url:
            suffix = ".mp4"
        elif ".mp3" in video_url:
            suffix = ".mp3"

        tmp_video = os.path.join(tempfile.gettempdir(), f"orbit_dl_{uuid.uuid4().hex}{suffix}")
        print(f"Downloading video from URL to {tmp_video} ...")

        with requests.get(video_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp_video, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        print(f"Downloaded {os.path.getsize(tmp_video) / (1024*1024):.1f} MB")
        return tmp_video

    @staticmethod
    def extract_audio(video_path: str) -> str:
        """Extract audio from a video file using ffmpeg. Returns path to .wav file."""
        # Pre-check: verify the file has an audio stream
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            video_path,
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        if not probe_result.stdout.strip():
            raise RuntimeError("Video file has no audio stream — cannot extract audio for transcription.")

        audio_path = os.path.join(
            tempfile.gettempdir(), f"orbit_audio_{uuid.uuid4().hex}.wav"
        )
        cmd = [
            "ffmpeg", "-y",
            "-err_detect", "ignore_err",  # Handle webm timestamp issues
            "-i", video_path,
            "-vn",               # no video
            "-acodec", "pcm_s16le",
            "-ar", "16000",      # 16kHz — Whisper's native rate
            "-ac", "1",          # mono
            "-af", "aresample=async=1:min_comp=0.001:min_hard_comp=0.100000",  # Fix async audio for browser webm
            audio_path
        ]
        print(f"Extracting audio with ffmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"ffmpeg stderr: {result.stderr[-500:]}")
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
        audio_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
        print(f"Audio extracted to {audio_path} ({audio_size / 1024:.1f} KB)")
        if audio_size < 1000:
            print(f"WARNING: Audio file is very small ({audio_size} bytes) — may contain no audio data")
        return audio_path

    @staticmethod
    def transcribe_audio(audio_path: str, source_lang: str = None) -> tuple[str, list[dict]]:
        """
        Transcribe audio using faster-whisper.
        Returns (full_text, segments_list).
        """
        model = get_whisper_model()
        # Use source_lang hint if provided, otherwise auto-detect
        whisper_lang = source_lang if source_lang and source_lang != "auto" else None
        print(f"Transcribing with Whisper (language={whisper_lang or 'auto-detect'}, vad_filter=True)...")
        segments_gen, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=whisper_lang,
            vad_filter=True,   # Filter out non-speech segments
            vad_parameters=dict(
                min_silence_duration_ms=300,   # Reduced from 500 for better detection
                speech_pad_ms=400,             # Pad speech segments to avoid clipping
            ),
        )

        segments = []
        full_parts = []
        for seg in segments_gen:
            text = seg.text.strip()
            if text:
                segments.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": text,
                })
                full_parts.append(text)

        full_text = " ".join(full_parts)
        print(f"Transcribed {len(segments)} segments, {len(full_text)} chars. Detected language: {info.language}")
        return full_text, segments

    @staticmethod
    def translate_text(text: str, target_lang: str) -> str:
        """Translate text to target_lang using GoogleTranslator (deep-translator)."""
        if not text.strip() or target_lang == "en":
            return text
        try:
            # Let GoogleTranslator auto-detect the source language
            translator = GoogleTranslator(source="auto", target=target_lang)
            result = translator.translate(text)
            return result or text
        except Exception as e:
            print(f"Translation error: {e}")
            return text

    @staticmethod
    def text_to_speech(text: str, target_lang: str) -> str:
        """Convert text to speech using gTTS. Returns path to mp3 file."""
        gtts_lang = GTTS_LANG_MAP.get(target_lang, "en")
        output_path = os.path.join(
            tempfile.gettempdir(), f"orbit_tts_{uuid.uuid4().hex}.mp3"
        )
        print(f"Generating TTS in '{gtts_lang}'...")
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        tts.save(output_path)
        print(f"TTS saved to {output_path}")
        return output_path

    # ─────────────────────────────────────────────────────────────
    # Public API used by routes.py
    # ─────────────────────────────────────────────────────────────

    def process_audio(
        self,
        audio_filepath: str,
        target_language: str,
        video_url: str = None,
    ) -> dict:
        """
        Full pipeline:
          1. Download video (if URL given)
          2. Extract audio with ffmpeg
          3. Transcribe with Whisper
          4. Translate to target_language
          5. Generate TTS mp3
          6. Return result dict
        """
        tmp_video = None
        tmp_audio = None
        try:
            # Step 1 — obtain video file
            if video_url:
                tmp_video = self.download_video(video_url)
                source_path = tmp_video
            elif audio_filepath and os.path.exists(audio_filepath):
                source_path = audio_filepath
            else:
                raise ValueError("No video URL or valid audio file path provided.")

            # Step 2 — extract audio
            tmp_audio = self.extract_audio(source_path)

            # Step 3 — transcribe (auto-detect language, small model handles multilingual well)
            original_text, segments = self.transcribe_audio(tmp_audio)
            print(f"Transcription result: {len(segments)} segments, text length: {len(original_text)}")
            if original_text:
                print(f"First 200 chars: {original_text[:200]}")

            if not original_text.strip():
                print("WARNING: No speech detected in the audio. Falling back gracefully.")
                original_text = "No speech detected in this recording."
                # We do not raise an error here because the frontend expects an audio file.
                # Generating a TTS that says "No speech detected" is better than a 500 error.

            # Step 4 — translate
            translated_text = self.translate_text(original_text, target_language)

            # Step 5 — TTS
            output_filepath = self.text_to_speech(translated_text, target_language)

            return {
                "success": True,
                "original_text": original_text,
                "translated_text": translated_text,
                "segments": segments,
                "source_language": "en",
                "output_filepath": output_filepath,
            }

        except Exception as e:
            print(f"process_audio error: {e}")
            return {"success": False, "error": str(e)}

        finally:
            # Clean up temp downloads (not the TTS output — caller cleans that)
            for path in [tmp_video, tmp_audio]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

    def get_transcript_segments(self, video_url: str, lang: str = "en") -> dict:
        """
        Returns timestamped segments only (no TTS).
        Used by the recording player's /transcribe endpoint.
        Optionally translates each segment if lang != 'en'.
        """
        tmp_video = None
        tmp_audio = None
        try:
            tmp_video = self.download_video(video_url)
            tmp_audio = self.extract_audio(tmp_video)
            full_text, segments = self.transcribe_audio(tmp_audio)

            if lang != "en":
                print(f"Translating {len(segments)} segments to '{lang}'...")
                for seg in segments:
                    seg["translated"] = self.translate_text(seg["text"], lang)
                    seg["_translatedLang"] = lang

            return {"success": True, "segments": segments, "text": full_text}

        except Exception as e:
            print(f"get_transcript_segments error: {e}")
            return {"success": False, "error": str(e)}

        finally:
            for path in [tmp_video, tmp_audio]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
