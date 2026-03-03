"""
Test script for the Voice Translation service.
Downloads a sample video with clear English speech and sends it through
the full translation pipeline (transcribe → translate → TTS).

Usage:
    python test_voice_translation.py
    
Requires: The orbit-vt Docker container running on localhost:8001
"""

import requests
import sys
import os
import time

# ─── Configuration ───────────────────────────────────────────────────
VOICE_API = "http://localhost:8001"

# Sample video: Big Buck Bunny (short clip with narration-like audio)
# We'll use a short, well-known public-domain MP4 that has clear audio
SAMPLE_VIDEO_URLS = [
    # 1. A short sample video with speech (NASA)  
    "https://www.nasa.gov/wp-content/uploads/2024/06/hubble_nicmos_hh2_infrared_rotate_30fps.mp4",
    # 2. Sample video from W3Schools (with audio track)
    "https://www.w3schools.com/html/mov_bbb.mp4",
]

TARGET_LANGUAGE = "hi"  # Translate to Hindi for testing


def check_health():
    """Check if the voice translation service is running."""
    print("=" * 60)
    print("STEP 1: Health Check")
    print("=" * 60)
    try:
        resp = requests.get(f"{VOICE_API}/health", timeout=5)
        if resp.status_code == 200:
            print(f"  ✓ Service is healthy: {resp.json()}")
            return True
        else:
            print(f"  ✗ Health check failed: {resp.status_code}")
            return False
    except requests.ConnectionError:
        print(f"  ✗ Cannot connect to {VOICE_API}")
        print(f"    Make sure the Docker container is running:")
        print(f"    docker run -d --name orbit-vt -p 8001:8001 orbit-voice-translation")
        return False


def test_translate_with_local_file():
    """
    Test using a local sample audio file.
    Creates a small WAV file with a TTS-generated speech for reliable testing.
    """
    print("\n" + "=" * 60)
    print("STEP 2: Test with a publicly hosted sample video")
    print("=" * 60)

    # Try to use a direct video URL — the service downloads it internally
    # We'll use the translate endpoint with video_url parameter
    
    # First, let's try with a direct downloadable video 
    # Using a short test video from a CDN
    test_url = "https://download.samplelib.com/mp4/sample-5s.mp4"
    
    print(f"  Sending video URL to translate endpoint...")
    print(f"  Video URL: {test_url}")
    print(f"  Target language: {TARGET_LANGUAGE}")
    
    start_time = time.time()
    
    try:
        resp = requests.post(
            f"{VOICE_API}/api/voice-translation/translate",
            data={
                "video_url": test_url,
                "target_language": TARGET_LANGUAGE,
            },
            timeout=300,  # 5 min timeout for download + processing
        )
        
        elapsed = time.time() - start_time
        print(f"\n  Response status: {resp.status_code} (took {elapsed:.1f}s)")
        
        if resp.status_code == 200:
            # Check headers for text
            original_text = resp.headers.get("X-Original-Text", "")
            translated_text = resp.headers.get("X-Translated-Text", "")
            content_type = resp.headers.get("Content-Type", "")
            content_length = len(resp.content)
            
            print(f"  Content-Type: {content_type}")
            print(f"  Audio size: {content_length:,} bytes ({content_length/1024:.1f} KB)")
            
            if original_text:
                from urllib.parse import unquote
                print(f"  Original text: {unquote(original_text)[:200]}")
            if translated_text:
                from urllib.parse import unquote
                print(f"  Translated text: {unquote(translated_text)[:200]}")
            
            # Save the audio for manual verification
            output_path = os.path.join(os.path.dirname(__file__), "test_output.mp3")
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"\n  ✓ SUCCESS! Audio saved to: {output_path}")
            print(f"  ✓ You can play this file to verify the translated speech.")
            return True
        else:
            print(f"  ✗ FAILED: {resp.text[:500]}")
            return False
            
    except requests.Timeout:
        print(f"  ✗ Request timed out after 300s")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_translate_text():
    """Test the lightweight text-only translation endpoint."""
    print("\n" + "=" * 60)
    print("STEP 3: Test text-only translation endpoint")
    print("=" * 60)
    
    try:
        resp = requests.post(
            f"{VOICE_API}/api/voice-translation/translate-text",
            json={
                "text": "Hello, this is a test of the voice translation service. The quick brown fox jumps over the lazy dog.",
                "target_lang": TARGET_LANGUAGE,
            },
            timeout=30,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Original:   {data.get('original_text', '')[:100]}")
            print(f"  Translated: {data.get('translated_text', '')[:100]}")
            print(f"  ✓ Text translation works!")
            return True
        else:
            print(f"  ✗ FAILED: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     ORBIT Voice Translation Service — Test Suite        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    
    # Step 1: Health check
    if not check_health():
        sys.exit(1)
    
    results = []
    
    # Step 2: Test text translation (quick sanity check)
    results.append(("Text Translation", test_translate_text()))
    
    # Step 3: Test full audio translation with sample video
    results.append(("Full Audio Translation", test_translate_with_local_file()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {name}")
    
    all_passed = all(p for _, p in results)
    print(f"\n{'All tests passed!' if all_passed else 'Some tests failed.'}")
    sys.exit(0 if all_passed else 1)

