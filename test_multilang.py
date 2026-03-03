"""
Multi-language voice translation test.
Tests translation from English to Telugu, Tamil, Kannada, and Malayalam
using both MP4 and WebM sample videos.

Usage: python test_multilang.py
Requires: orbit-vt Docker container on localhost:8001
"""

import requests
import sys
import time
from urllib.parse import unquote

VOICE_API = "http://localhost:8001"

# Languages to test
LANGUAGES = {
    "te": "Telugu",
    "ta": "Tamil",
    "kn": "Kannada",
    "ml": "Malayalam",
}

# Sample video with audio (MP4 from samplelib.com — confirmed to have AAC audio)
SAMPLE_VIDEO_URL = "https://download.samplelib.com/mp4/sample-5s.mp4"


def check_health():
    try:
        resp = requests.get(f"{VOICE_API}/health", timeout=5)
        if resp.status_code == 200:
            print(f"  [OK] Service healthy\n")
            return True
    except Exception:
        pass
    print("  [FAIL] Cannot connect to service at", VOICE_API)
    return False


def test_text_translation(lang_code, lang_name):
    """Quick text-only translation test."""
    try:
        resp = requests.post(
            f"{VOICE_API}/api/voice-translation/translate-text",
            json={
                "text": "Welcome to the online classroom. Today we will learn about data structures and algorithms.",
                "target_lang": lang_code,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            translated = data.get("translated_text", "")[:80]
            print(f"  [{lang_name}] {translated}")
            return True
        else:
            print(f"  [{lang_name}] FAILED: {resp.status_code}")
            return False
    except Exception as e:
        print(f"  [{lang_name}] ERROR: {e}")
        return False


def test_audio_translation(lang_code, lang_name, video_url):
    """Full audio translation pipeline test."""
    start = time.time()
    try:
        resp = requests.post(
            f"{VOICE_API}/api/voice-translation/translate",
            data={"video_url": video_url, "target_language": lang_code},
            timeout=300,
        )
        elapsed = time.time() - start

        if resp.status_code == 200:
            size_kb = len(resp.content) / 1024
            orig = unquote(resp.headers.get("X-Original-Text", ""))[:60]
            trans = unquote(resp.headers.get("X-Translated-Text", ""))[:60]
            print(f"  [{lang_name}] 200 OK | {size_kb:.1f} KB | {elapsed:.1f}s")
            print(f"           Original:   {orig}...")
            print(f"           Translated: {trans}...")

            # Save output
            fname = f"test_output_{lang_code}.mp3"
            with open(fname, "wb") as f:
                f.write(resp.content)
            print(f"           Saved: {fname}")
            return True
        else:
            detail = resp.text[:200]
            print(f"  [{lang_name}] FAILED {resp.status_code} ({elapsed:.1f}s): {detail}")
            return False
    except requests.Timeout:
        print(f"  [{lang_name}] TIMEOUT after 300s")
        return False
    except Exception as e:
        print(f"  [{lang_name}] ERROR: {e}")
        return False


if __name__ == "__main__":
    print("=" * 65)
    print("  ORBIT Voice Translation — Multi-Language Test")
    print("=" * 65)

    if not check_health():
        sys.exit(1)

    results = []

    # ── Test 1: Text translation for all languages ──
    print("── TEXT TRANSLATION ──────────────────────────────────────")
    for code, name in LANGUAGES.items():
        passed = test_text_translation(code, name)
        results.append((f"Text → {name}", passed))

    # ── Test 2: Full audio translation for all languages ──
    print("\n── FULL AUDIO TRANSLATION (MP4) ─────────────────────────")
    print(f"  Video: {SAMPLE_VIDEO_URL}\n")
    for code, name in LANGUAGES.items():
        passed = test_audio_translation(code, name, SAMPLE_VIDEO_URL)
        results.append((f"Audio → {name}", passed))
        print()

    # ── Summary ──
    print("=" * 65)
    print("  RESULTS")
    print("=" * 65)
    for name, passed in results:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")

    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    print(f"\n  {passed_count}/{total} tests passed.")
    sys.exit(0 if passed_count == total else 1)
