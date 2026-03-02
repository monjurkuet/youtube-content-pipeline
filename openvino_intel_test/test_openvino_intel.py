#!/usr/bin/env python3
"""
Test script to verify OpenVINO Whisper functionality with Intel GPU using provided audio file.

This script tests:
1. Intel GPU detection
2. Whisper medium model loading with OpenVINO
3. Actual transcription of the provided audio file
4. Performance metrics and error handling
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent  # Go up from openvino_intel_test to project root
sys.path.insert(0, str(project_root))

def test_openvino_intel_transcription():
    """Test OpenVINO Whisper transcription with Intel GPU."""
    print("🔍 Testing OpenVINO Whisper with Intel GPU and provided audio file\n")

    # Test audio file path
    test_audio_path = r"\root\How to Build a Trading Strategy (Step by Step with Playbook).mp3"

    # Convert Windows-style path to proper Unix path
    if test_audio_path.startswith("\\root\\"):
        test_audio_path = "/root/" + test_audio_path[6:]

    # Replace remaining backslashes with forward slashes
    test_audio_path = test_audio_path.replace("\\", "/")

    print(f"📁 Looking for test audio file: {test_audio_path}")

    # Check if the file exists
    if not Path(test_audio_path).exists():
        print(f"❌ Test audio file not found: {test_audio_path}")

        # Look for similar files in the root directory
        root_dir = Path("/root/")
        mp3_files = list(root_dir.glob("*.mp3"))
        if mp3_files:
            print(f"📁 Found MP3 files in /root/:")
            for mp3_file in mp3_files:
                print(f"   - {mp3_file.name}")
            print(f"💡 Please update the test_audio_path variable to point to the correct file.")
        else:
            print(f"💡 No MP3 files found in /root/ directory.")
        return False

    print("✅ Test audio file found")

    try:
        # Import necessary modules
        from src.transcription.whisper_openvino_intel import OpenVINOWhisperTranscriber

        print("\n🔄 Creating OpenVINO Whisper transcriber...")

        # Create transcriber with medium model
        transcriber = OpenVINOWhisperTranscriber(
            model_id="openai/whisper-medium",
            device="GPU",  # Will use GPU if available, fall back to CPU
            cache_dir=os.path.expanduser("~/.cache/whisper_openvino")
        )

        print("✅ OpenVINO Whisper transcriber created successfully")

        # Test device detection
        device = transcriber._detect_device()
        print(f"🎮 Using device: {device}")

        # Start timing the transcription
        start_time = time.time()
        print(f"\n🎤 Starting transcription of: {Path(test_audio_path).name}")

        # Perform transcription
        result = transcriber.transcribe(
            audio_path=test_audio_path,
            language="en",
            chunk_length=30
        )

        end_time = time.time()
        transcription_time = end_time - start_time

        print(f"✅ Transcription completed in {transcription_time:.2f} seconds")
        print(f"🔤 Language detected: {result.get('language', 'unknown')}")

        # Show a sample of the transcription
        transcription_text = result.get("text", "")
        print(f"📝 Transcription length: {len(transcription_text)} characters")

        if len(transcription_text) > 200:
            print(f"📋 Sample transcription (first 200 chars):\n{transcription_text[:200]}...")
        else:
            print(f"📋 Full transcription:\n{transcription_text}")

        # Unload the model
        transcriber.unload()
        print("\n✅ Model unloaded successfully")

        return True

    except Exception as e:
        print(f"❌ OpenVINO transcription test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_basic_openvino_functionality():
    """Test basic OpenVINO functionality."""
    print("🔍 Testing basic OpenVINO functionality...")

    try:
        import openvino as ov
        print(f"✅ OpenVINO version: {ov.__version__}")

        # Test device detection
        core = ov.Core()
        devices = core.available_devices
        print(f"🎮 Available devices: {devices}")

        has_gpu = "GPU" in devices
        if has_gpu:
            print("✅ Intel GPU detected!")
        else:
            print("⚠️  No Intel GPU detected (will use CPU)")

        return True
    except Exception as e:
        print(f"❌ Basic OpenVINO test failed: {e}")
        return False

def test_optimum_intel():
    """Test Optimum Intel functionality."""
    print("\n🔍 Testing Optimum Intel integration...")

    try:
        from optimum.intel.openvino import OVModelForSpeechSeq2Seq
        print("✅ Optimum Intel OpenVINO import successful")

        # Test model mapping
        from src.transcription.whisper_openvino_intel import OpenVINOWhisperTranscriber
        transcriber = OpenVINOWhisperTranscriber(model_id="openai/whisper-medium")

        ov_model_id, compute_type = transcriber._get_openvino_model_id("openai/whisper-medium")
        print(f"📦 OpenVINO model mapping: {ov_model_id} ({compute_type})")

        return True
    except Exception as e:
        print(f"❌ Optimum Intel test failed: {e}")
        return False

def main():
    """Run all OpenVINO Intel tests."""
    print("🚀 OpenVINO Intel GPU & Whisper Medium Model Test Suite\n")

    # Test basic functionality
    basic_passed = test_basic_openvino_functionality()
    optimum_passed = test_optimum_intel()

    # Test actual transcription with provided audio file
    whisper_passed = test_openvino_intel_transcription()

    all_passed = basic_passed and optimum_passed and whisper_passed

    print(f"\n{'🎉 All tests passed!' if all_passed else '💥 Some tests failed!'}")
    print("\n📋 Test Summary:")
    print(f"- Basic OpenVINO functionality: {'✅ Passed' if basic_passed else '❌ Failed'}")
    print(f"- Optimum Intel integration: {'✅ Passed' if optimum_passed else '❌ Failed'}")
    print(f"- Whisper transcription: {'✅ Passed' if whisper_passed else '❌ Failed'}")

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)