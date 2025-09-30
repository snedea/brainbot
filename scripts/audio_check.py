#!/usr/bin/env python3
"""
Audio device testing utility for BrainBot voice mode.

This script helps users:
- List all available audio devices
- Identify input devices for recording
- Test microphone by recording a sample
- Verify audio setup before running voice mode
"""

import sys
import wave
import time
from pathlib import Path

try:
    import pyaudio
except ImportError:
    print("❌ PyAudio not installed")
    print("Install it with: pip install pyaudio")
    sys.exit(1)


def list_devices():
    """List all available audio devices."""
    print("\n" + "=" * 50)
    print("🎤 AVAILABLE AUDIO DEVICES")
    print("=" * 50)

    p = pyaudio.PyAudio()

    print(f"\nFound {p.get_device_count()} total devices:\n")

    input_devices = []
    output_devices = []

    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            name = info['name']
            max_in = info['maxInputChannels']
            max_out = info['maxOutputChannels']
            rate = int(info['defaultSampleRate'])

            if max_in > 0:
                input_devices.append((i, name, rate))
            if max_out > 0:
                output_devices.append((i, name, rate))

        except Exception as e:
            print(f"⚠️  Warning: Could not read device {i}: {e}")

    # Print input devices
    print("📥 INPUT DEVICES (Microphones):")
    if input_devices:
        for idx, name, rate in input_devices:
            print(f"  [{idx}] {name} ({rate}Hz)")
    else:
        print("  None found")

    print("\n📤 OUTPUT DEVICES (Speakers):")
    if output_devices:
        for idx, name, rate in output_devices:
            print(f"  [{idx}] {name} ({rate}Hz)")
    else:
        print("  None found")

    # Show default devices
    try:
        default_in = p.get_default_input_device_info()
        print(f"\n⭐ Default input: [{default_in['index']}] {default_in['name']}")
    except:
        print("\n⚠️  No default input device found")

    try:
        default_out = p.get_default_output_device_info()
        print(f"⭐ Default output: [{default_out['index']}] {default_out['name']}")
    except:
        print("⚠️  No default output device found")

    p.terminate()
    return input_devices


def test_recording(device_index=None, duration=3):
    """
    Test recording from microphone.

    Args:
        device_index: Optional device index (None = default)
        duration: Recording duration in seconds
    """
    print("\n" + "=" * 50)
    print(f"🎙️  RECORDING TEST ({duration} seconds)")
    print("=" * 50)

    p = pyaudio.PyAudio()

    # Recording parameters
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000  # 16kHz for whisper.cpp

    print(f"\nRecording from device: ", end="")
    if device_index is not None:
        info = p.get_device_info_by_index(device_index)
        print(f"[{device_index}] {info['name']}")
    else:
        print("Default device")

    try:
        # Open stream
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )

        print(f"\n🔴 Recording... (speak into your microphone)")

        frames = []
        for i in range(0, int(RATE / CHUNK * duration)):
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)

                # Simple progress indicator
                if i % 10 == 0:
                    print(".", end="", flush=True)

            except Exception as e:
                print(f"\n⚠️  Read error: {e}")
                break

        print("\n✅ Recording complete")

        # Stop and close stream
        stream.stop_stream()
        stream.close()

        # Save to file
        output_path = Path("/tmp/brainbot_audio_test.wav")
        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        print(f"\n💾 Saved to: {output_path}")
        print(f"📊 Format: 16kHz mono, 16-bit PCM")
        print(f"\n▶️  Play back with:")
        print(f"   aplay {output_path}")
        print(f"\n   or:")
        print(f"   ffplay -nodisp -autoexit {output_path}")

        return True

    except OSError as e:
        print(f"\n❌ Recording failed: {e}")
        print("\nCommon causes:")
        print("  • Microphone not connected")
        print("  • Device already in use")
        print("  • Permission denied (try: sudo usermod -a -G audio $USER)")
        return False

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

    finally:
        p.terminate()


def main():
    """Main test routine."""
    print("\n" + "=" * 50)
    print("🎤 BrainBot Audio Check")
    print("=" * 50)

    # Check if pyaudio works
    try:
        p = pyaudio.PyAudio()
        p.terminate()
    except Exception as e:
        print(f"\n❌ PyAudio initialization failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Install portaudio: sudo apt-get install portaudio19-dev")
        print("  2. Reinstall pyaudio: pip install --force-reinstall pyaudio")
        sys.exit(1)

    # List devices
    input_devices = list_devices()

    if not input_devices:
        print("\n❌ No input devices found!")
        print("\nTroubleshooting:")
        print("  • Check if microphone is connected")
        print("  • Try: arecord -l")
        print("  • Check permissions: ls -la /dev/snd/")
        sys.exit(1)

    # Ask user if they want to test recording
    print("\n" + "=" * 50)
    response = input("\n🎙️  Test recording? [Y/n]: ").strip().lower()

    if response in ['', 'y', 'yes']:
        # Ask which device to test
        if len(input_devices) > 1:
            print("\nAvailable input devices:")
            for idx, name, _ in input_devices:
                print(f"  [{idx}] {name}")

            device_input = input("\nEnter device index (or press Enter for default): ").strip()

            if device_input:
                try:
                    device_index = int(device_input)
                except ValueError:
                    print("Invalid index, using default")
                    device_index = None
            else:
                device_index = None
        else:
            device_index = None

        # Test recording
        success = test_recording(device_index, duration=3)

        if success:
            print("\n" + "=" * 50)
            print("✅ AUDIO CHECK COMPLETE")
            print("=" * 50)
            print("\nYour audio setup is working!")
            print("\nNext steps:")
            print("  1. Set up .env file with your Porcupine key")
            print("  2. Run: python3 brain_bot.py --voice")

            if device_index is not None:
                print(f"\n💡 To use this device in voice mode:")
                print(f"   Add to .env: MIC_INDEX={device_index}")
        else:
            print("\n" + "=" * 50)
            print("❌ AUDIO CHECK FAILED")
            print("=" * 50)
            print("\nPlease fix the audio issues before using voice mode.")
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Audio check cancelled")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)