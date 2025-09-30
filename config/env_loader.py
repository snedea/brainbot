"""
Environment configuration loader for voice settings.

This module loads voice assistant configuration from environment variables
using python-dotenv, with validation and helpful error messages.
"""

import os
import logging
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    raise ImportError(
        "python-dotenv is required for voice mode. "
        "Install it with: pip install python-dotenv"
    )

from .voice_config import VoiceConfig

logger = logging.getLogger(__name__)


def load_voice_config(env_file: Optional[Path] = None) -> VoiceConfig:
    """
    Load voice configuration from environment variables.

    Args:
        env_file: Optional path to .env file (defaults to .env in project root)

    Returns:
        VoiceConfig instance with settings from environment

    Raises:
        ValueError: If required settings are missing or invalid
        FileNotFoundError: If specified model files don't exist
    """
    # Load .env file
    if env_file is None:
        env_file = Path(__file__).parent.parent / ".env"

    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment from {env_file}")
    else:
        logger.warning(f"No .env file found at {env_file}")
        logger.info("Copy .env.example to .env and configure your settings")

    # Get Porcupine access key (required)
    access_key = os.getenv('PORCUPINE_ACCESS_KEY', '').strip()
    if not access_key or access_key == 'YOUR_ACCESS_KEY_HERE':
        raise ValueError(
            "PORCUPINE_ACCESS_KEY is required for voice mode.\n"
            "Get your free access key from: https://console.picovoice.ai/\n"
            "Then add it to your .env file"
        )

    # Get wake word settings
    keyword = os.getenv('PORCUPINE_KEYWORD', 'computer').strip()
    keyword_path_str = os.getenv('PORCUPINE_KEYWORD_PATH', '').strip()

    # Determine keywords vs keyword_paths
    wake_keywords = None
    wake_keyword_paths = None

    if keyword_path_str:
        keyword_path = Path(keyword_path_str).expanduser()
        if keyword_path.exists():
            wake_keyword_paths = [keyword_path]
            logger.info(f"Using custom wake word from {keyword_path}")
        else:
            logger.warning(f"Custom keyword file not found: {keyword_path}")
            logger.info(f"Falling back to built-in keyword: {keyword}")
            wake_keywords = [keyword]
    else:
        wake_keywords = [keyword]
        logger.info(f"Using built-in wake word: {keyword}")

    # Get audio device settings
    mic_index_str = os.getenv('MIC_INDEX', '-1').strip()
    try:
        mic_index = int(mic_index_str)
        if mic_index == -1:
            mic_index = None
    except ValueError:
        logger.warning(f"Invalid MIC_INDEX: {mic_index_str}, using default")
        mic_index = None

    # Get model paths with defaults
    home = Path.home()
    project_root = home / "homelab" / "brainbot"

    whisper_bin = Path(os.getenv(
        'WHISPER_BIN',
        str(home / 'homelab' / 'whisper.cpp' / 'build' / 'bin' / 'main')
    )).expanduser()

    whisper_model = Path(os.getenv(
        'WHISPER_MODEL',
        str(home / 'homelab' / 'whisper.cpp' / 'models' / 'ggml-base.en.bin')
    )).expanduser()

    piper_bin = Path(os.getenv(
        'PIPER_BIN',
        str(home / 'piper' / 'piper' / 'piper')
    )).expanduser()

    piper_voice = Path(os.getenv(
        'PIPER_VOICE',
        str(home / 'piper' / 'en_US-lessac-medium.onnx')
    )).expanduser()

    llama_model = Path(os.getenv(
        'LLAMA_MODEL',
        str(home / '.cache' / 'brainbot' / 'tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf')
    )).expanduser()

    # Validate critical paths exist
    missing_files = []
    for name, path in [
        ('Whisper binary', whisper_bin),
        ('Whisper model', whisper_model),
        ('Piper binary', piper_bin),
        ('Piper voice', piper_voice),
        ('LLaMA model', llama_model)
    ]:
        if not path.exists():
            missing_files.append(f"  - {name}: {path}")

    if missing_files:
        raise FileNotFoundError(
            "Missing required files:\n" +
            "\n".join(missing_files) +
            "\n\nRun ./setup_voice.sh to install voice mode dependencies"
        )

    # Get performance settings
    llama_threads = int(os.getenv('LLAMA_THREADS', '4'))

    # Get recording settings
    silence_threshold = int(os.getenv('SILENCE_THRESHOLD', '500'))
    max_recording_sec = float(os.getenv('MAX_RECORDING_SEC', '30'))
    silence_duration_sec = float(os.getenv('SILENCE_DURATION_SEC', '2.0'))

    # Get temp directory
    tmp_dir = Path(os.getenv('TMP_DIR', '/tmp/brainbot')).expanduser()
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Create and return config
    config = VoiceConfig(
        # Porcupine (note: VoiceConfig expects 'access_key', not 'porcupine_access_key')
        access_key=access_key,
        wake_keywords=wake_keywords,
        wake_keyword_paths=wake_keyword_paths,

        # Audio
        audio_device_index=mic_index,
        silence_threshold=silence_threshold,
        max_recording_sec=max_recording_sec,
        silence_duration_sec=silence_duration_sec,

        # Model paths
        whisper_bin=whisper_bin,
        whisper_model=whisper_model,
        piper_bin=piper_bin,
        piper_voice=piper_voice,
        llama_model_path=llama_model,

        # Performance
        llama_threads=llama_threads,

        # Temp directory
        tmp_dir=tmp_dir
    )

    logger.info("Voice configuration loaded successfully")
    return config


def check_voice_mode_ready() -> tuple[bool, str]:
    """
    Check if voice mode is ready to use.

    Returns:
        Tuple of (is_ready, message)
    """
    try:
        load_voice_config()
        return True, "Voice mode is ready"
    except ValueError as e:
        return False, f"Configuration error: {e}"
    except FileNotFoundError as e:
        return False, f"Missing files: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"