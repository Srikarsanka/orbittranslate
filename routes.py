import os
import tempfile
import shutil
import urllib.parse

from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from service import VoiceTranslationService

router = APIRouter()
service = VoiceTranslationService()


def cleanup_files(*filepaths):
    """Background task to remove temporary files after response is sent."""
    for filepath in filepaths:
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error cleaning up file {filepath}: {e}")


# ─────────────────────────────────────────────────────────────
#  POST /api/voice-translation/translate
#  Used by the student dashboard "Translate" button.
#  Returns: mp3 audio file with translated speech.
# ─────────────────────────────────────────────────────────────
@router.post("/translate")
async def translate_audio(
    background_tasks: BackgroundTasks,
    target_language: str = Form(...),
    file: UploadFile = File(None),
    video_url: str = Form(None),
):
    if not file and not video_url:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'file' (uploaded video) or 'video_url' (Cloudinary/remote URL)"
        )

    tmp_upload_path = None

    try:
        # If uploaded file, save to temp disk first
        if file:
            suffix = os.path.splitext(file.filename or "upload.webm")[1] or ".webm"
            tmp_upload_path = os.path.join(tempfile.gettempdir(), f"orbit_upload_{os.urandom(8).hex()}{suffix}")
            with open(tmp_upload_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

        result = service.process_audio(
            audio_filepath=tmp_upload_path or "",
            target_language=target_language,
            video_url=video_url,         # ← was always ignored before, now correctly passed
        )

    finally:
        # Always clean up the uploaded temp file (but NOT the TTS output — done after response)
        if tmp_upload_path and os.path.exists(tmp_upload_path):
            try:
                os.remove(tmp_upload_path)
            except Exception:
                pass

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error during processing"))

    output_filepath = result["output_filepath"]

    # Schedule TTS mp3 cleanup after the response is sent
    background_tasks.add_task(cleanup_files, output_filepath)

    # URL-encode text headers to avoid ASCII issues with non-Latin characters
    headers = {
        "X-Original-Text": urllib.parse.quote(result.get("original_text", "")[:500]),
        "X-Translated-Text": urllib.parse.quote(result.get("translated_text", "")[:500]),
        "X-Source-Language": result.get("source_language", "en"),
    }

    return FileResponse(
        path=output_filepath,
        media_type="audio/mpeg",
        filename="translated_audio.mp3",
        headers=headers,
    )


# ─────────────────────────────────────────────────────────────
#  POST /api/voice-translation/translate-json
#  JSON version of /translate for easy Node.js proxy usage.
#  Body: { "videoUrl": "...", "targetLanguage": "hi" }
#  Returns: mp3 audio file
# ─────────────────────────────────────────────────────────────
class TranslateJsonRequest(BaseModel):
    videoUrl: str
    targetLanguage: str


@router.post("/translate-json")
async def translate_audio_json(body: TranslateJsonRequest, background_tasks: BackgroundTasks):
    if not body.videoUrl:
        raise HTTPException(status_code=400, detail="videoUrl is required")

    print(f"[translate-json] Processing: lang={body.targetLanguage}, url={body.videoUrl[:80]}...")

    result = service.process_audio(
        audio_filepath="",
        target_language=body.targetLanguage,
        video_url=body.videoUrl,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

    output_filepath = result["output_filepath"]
    background_tasks.add_task(cleanup_files, output_filepath)

    return FileResponse(
        path=output_filepath,
        media_type="audio/mpeg",
        filename="translated_audio.mp3",
    )


# ─────────────────────────────────────────────────────────────
#  POST /api/voice-translation/transcribe
#  Used by the recording player for timestamped subtitles.
#  Body: { "videoUrl": "...", "lang": "te" }
#  Returns: { segments: [{start, end, text, translated?, _translatedLang?}] }
# ─────────────────────────────────────────────────────────────
class TranscribeRequest(BaseModel):
    videoUrl: str
    lang: str = "en"


class TranslateTextRequest(BaseModel):
    text: str
    target_lang: str


@router.post("/translate-text")
async def translate_text_only(body: TranslateTextRequest):
    """
    Lightweight endpoint: translates a plain text string to target_lang.
    Used by recording_player.html for subtitle/transcript translation
    (no audio/video processing — just text in, translated text out).
    """
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    if not body.target_lang:
        raise HTTPException(status_code=400, detail="target_lang is required")

    translated = service.translate_text(body.text, body.target_lang)
    return JSONResponse(content={
        "success": True,
        "original_text": body.text,
        "translated_text": translated,
        "target_lang": body.target_lang,
    })


@router.post("/transcribe")
async def transcribe_video(body: TranscribeRequest):
    if not body.videoUrl or not body.videoUrl.strip():
        raise HTTPException(status_code=400, detail="videoUrl is required")

    result = service.get_transcript_segments(
        video_url=body.videoUrl,
        lang=body.lang,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Transcription failed"))

    return JSONResponse(content={
        "success": True,
        "segments": result["segments"],
        "text": result.get("text", ""),
        "totalSegments": len(result["segments"]),
    })
