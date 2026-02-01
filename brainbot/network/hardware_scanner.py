"""Hardware scanner for detecting node capabilities."""

import logging
import os
import platform
import shutil
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

from .models import (
    CapabilityManifest,
    CapabilitySpec,
    HardwareCapability,
    UsagePolicy,
)

logger = logging.getLogger(__name__)


class HardwareScanner:
    """
    Scans system hardware to build a capability manifest.

    Detects:
    - GPU (NVIDIA CUDA, AMD ROCm, Apple Metal)
    - Displays (HDMI, Pi displays, framebuffer)
    - Cameras (USB, Pi camera module)
    - Audio (microphones, speakers)
    - LEDs (NeoPixel via existing config)
    - Fans (PWM via existing config)
    - System resources (CPU, RAM, disk)
    - Raspberry Pi specifics
    """

    def __init__(self, hardware_config: Optional[dict] = None):
        """
        Initialize scanner.

        Args:
            hardware_config: Optional existing hardware config (from Settings)
        """
        self.hardware_config = hardware_config or {}

    def scan(self) -> CapabilityManifest:
        """Perform full hardware scan and return manifest."""
        logger.info("Starting hardware scan...")

        manifest = CapabilityManifest(
            platform=platform.system().lower(),
            platform_version=platform.release(),
            hostname=socket.gethostname(),
            scanned_at=datetime.now(),
        )

        # System resources
        manifest.cpu_cores = psutil.cpu_count() or 1
        manifest.ram_gb = psutil.virtual_memory().total / (1024**3)
        manifest.disk_gb = psutil.disk_usage("/").total / (1024**3)

        # Raspberry Pi detection
        manifest.is_raspberry_pi = self._detect_raspberry_pi()
        if manifest.is_raspberry_pi:
            manifest.pi_model = self._get_pi_model()

        # Scan all hardware categories
        capabilities = []
        capabilities.extend(self._scan_gpu())
        capabilities.extend(self._scan_displays())
        capabilities.extend(self._scan_cameras())
        capabilities.extend(self._scan_audio())
        capabilities.extend(self._scan_leds())
        capabilities.extend(self._scan_fans())
        capabilities.extend(self._scan_sensors())
        capabilities.extend(self._scan_network())
        capabilities.extend(self._scan_storage())

        manifest.capabilities = capabilities

        logger.info(
            f"Scan complete: {len([c for c in capabilities if c.available])} "
            f"capabilities detected"
        )
        return manifest

    def _detect_raspberry_pi(self) -> bool:
        """Check if running on Raspberry Pi."""
        # Check /proc/cpuinfo for Raspberry Pi
        try:
            cpuinfo = Path("/proc/cpuinfo")
            if cpuinfo.exists():
                content = cpuinfo.read_text().lower()
                if "raspberry" in content or "bcm2" in content:
                    return True
        except Exception:
            pass

        # Check device tree
        try:
            model_path = Path("/proc/device-tree/model")
            if model_path.exists():
                model = model_path.read_text().lower()
                if "raspberry" in model:
                    return True
        except Exception:
            pass

        return False

    def _get_pi_model(self) -> Optional[str]:
        """Get Raspberry Pi model string."""
        try:
            model_path = Path("/proc/device-tree/model")
            if model_path.exists():
                return model_path.read_text().strip().rstrip("\x00")
        except Exception:
            pass
        return None

    def _scan_gpu(self) -> list[CapabilitySpec]:
        """Detect GPU capabilities."""
        capabilities = []

        # NVIDIA CUDA
        nvidia_detected = False
        nvidia_details = {}

        if shutil.which("nvidia-smi"):
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    nvidia_detected = True
                    parts = result.stdout.strip().split(",")
                    nvidia_details = {
                        "gpu_name": parts[0].strip() if len(parts) > 0 else "Unknown",
                        "memory_mb": parts[1].strip() if len(parts) > 1 else "Unknown",
                    }
            except Exception as e:
                logger.debug(f"NVIDIA detection failed: {e}")

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.GPU_CUDA,
                available=nvidia_detected,
                details=nvidia_details,
                detection_method="nvidia-smi",
            )
        )

        # AMD ROCm
        rocm_detected = False
        rocm_details = {}

        rocminfo = shutil.which("rocminfo") or "/opt/rocm/bin/rocminfo"
        if Path(rocminfo).exists():
            try:
                result = subprocess.run(
                    [rocminfo],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and "Agent" in result.stdout:
                    rocm_detected = True
                    rocm_details["rocm_path"] = rocminfo
            except Exception as e:
                logger.debug(f"ROCm detection failed: {e}")

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.GPU_ROCM,
                available=rocm_detected,
                details=rocm_details,
                detection_method="rocminfo",
            )
        )

        # Apple Metal (macOS)
        metal_detected = False
        metal_details = {}

        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and ("Metal" in result.stdout or "Apple" in result.stdout):
                    metal_detected = True
                    # Extract GPU name
                    for line in result.stdout.split("\n"):
                        if "Chipset Model" in line:
                            metal_details["gpu_name"] = line.split(":")[1].strip()
                            break
            except Exception as e:
                logger.debug(f"Metal detection failed: {e}")

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.GPU_METAL,
                available=metal_detected,
                details=metal_details,
                detection_method="system_profiler",
            )
        )

        # GPU_NONE if no GPU detected
        has_gpu = nvidia_detected or rocm_detected or metal_detected
        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.GPU_NONE,
                available=not has_gpu,
                detection_method="fallback",
            )
        )

        return capabilities

    def _scan_displays(self) -> list[CapabilitySpec]:
        """Detect display capabilities."""
        capabilities = []

        # Check existing hardware config for Pi displays
        lcd_1inch_enabled = self.hardware_config.get("lcd_1inch", {}).get("enabled", False)
        lcd_5inch_enabled = self.hardware_config.get("lcd_5inch", {}).get("enabled", False)

        # 1-inch OLED (from config or I2C detection)
        oled_detected = lcd_1inch_enabled
        if not oled_detected:
            # Try I2C detection
            oled_detected = self._detect_i2c_device(0x3C)  # Common SSD1306 address

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.DISPLAY_1INCH,
                available=oled_detected,
                details={"i2c_address": "0x3C"} if oled_detected else {},
                detection_method="config" if lcd_1inch_enabled else "i2c_scan",
            )
        )

        # 5-inch display (from config or SPI detection)
        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.DISPLAY_5INCH,
                available=lcd_5inch_enabled,
                details=self.hardware_config.get("lcd_5inch", {}),
                detection_method="config",
            )
        )

        # HDMI display (via xrandr or framebuffer)
        hdmi_detected = False
        hdmi_details = {}

        if shutil.which("xrandr"):
            try:
                result = subprocess.run(
                    ["xrandr", "--query"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and " connected" in result.stdout:
                    hdmi_detected = True
                    # Count connected displays
                    connected = result.stdout.count(" connected")
                    hdmi_details["connected_displays"] = connected
            except Exception:
                pass

        # Fallback: check framebuffer
        if not hdmi_detected:
            fb0 = Path("/dev/fb0")
            if fb0.exists():
                hdmi_detected = True
                hdmi_details["framebuffer"] = "/dev/fb0"

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.DISPLAY_HDMI,
                available=hdmi_detected,
                details=hdmi_details,
                detection_method="xrandr" if shutil.which("xrandr") else "framebuffer",
            )
        )

        # Headless (if no display detected)
        has_display = oled_detected or lcd_5inch_enabled or hdmi_detected
        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.DISPLAY_HEADLESS,
                available=not has_display,
                detection_method="fallback",
            )
        )

        return capabilities

    def _scan_cameras(self) -> list[CapabilitySpec]:
        """Detect camera capabilities."""
        capabilities = []

        # USB cameras via /dev/video*
        usb_cameras = list(Path("/dev").glob("video*"))
        usb_detected = len(usb_cameras) > 0
        usb_details = {}
        if usb_detected:
            usb_details["devices"] = [str(c) for c in usb_cameras]

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.CAMERA_USB,
                available=usb_detected,
                details=usb_details,
                detection_method="/dev/video*",
                # Cameras require explicit consent
                usage_policy=UsagePolicy.EXPLICIT,
                requires_confirmation=True,
                allowed_task_types=["photo", "timelapse", "security"],
            )
        )

        # Raspberry Pi camera module
        pi_camera_detected = False
        pi_camera_details = {}

        if shutil.which("libcamera-hello"):
            try:
                result = subprocess.run(
                    ["libcamera-hello", "--list-cameras"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and "Available cameras" in result.stdout:
                    pi_camera_detected = True
                    pi_camera_details["libcamera"] = True
            except Exception:
                pass

        # Legacy raspistill check
        if not pi_camera_detected and shutil.which("raspistill"):
            # Check if legacy camera stack available
            vcgencmd = shutil.which("vcgencmd")
            if vcgencmd:
                try:
                    result = subprocess.run(
                        [vcgencmd, "get_camera"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if "detected=1" in result.stdout:
                        pi_camera_detected = True
                        pi_camera_details["legacy"] = True
                except Exception:
                    pass

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.CAMERA_PI,
                available=pi_camera_detected,
                details=pi_camera_details,
                detection_method="libcamera" if pi_camera_details.get("libcamera") else "raspistill",
                usage_policy=UsagePolicy.EXPLICIT,
                requires_confirmation=True,
                allowed_task_types=["photo", "timelapse", "security"],
            )
        )

        # No camera fallback
        has_camera = usb_detected or pi_camera_detected
        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.CAMERA_NONE,
                available=not has_camera,
                detection_method="fallback",
            )
        )

        return capabilities

    def _scan_audio(self) -> list[CapabilitySpec]:
        """Detect audio input/output capabilities."""
        capabilities = []

        # Microphone detection
        mic_detected = False
        mic_details = {}

        if shutil.which("arecord"):
            try:
                result = subprocess.run(
                    ["arecord", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and "card" in result.stdout.lower():
                    mic_detected = True
                    # Count cards
                    cards = result.stdout.count("card")
                    mic_details["devices"] = cards
            except Exception:
                pass

        # macOS: check for audio input devices
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPAudioDataType"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if "Input Source" in result.stdout or "Microphone" in result.stdout:
                    mic_detected = True
            except Exception:
                pass

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.MICROPHONE,
                available=mic_detected,
                details=mic_details,
                detection_method="arecord" if shutil.which("arecord") else "system_profiler",
                # Microphones require explicit consent
                usage_policy=UsagePolicy.EXPLICIT,
                requires_confirmation=True,
                allowed_task_types=["voice_command", "recording", "transcription"],
            )
        )

        # Speaker detection
        speaker_detected = False
        speaker_details = {}

        if shutil.which("aplay"):
            try:
                result = subprocess.run(
                    ["aplay", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and "card" in result.stdout.lower():
                    speaker_detected = True
                    cards = result.stdout.count("card")
                    speaker_details["devices"] = cards
            except Exception:
                pass

        # macOS: check for audio output
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPAudioDataType"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if "Output Source" in result.stdout or "Speaker" in result.stdout:
                    speaker_detected = True
            except Exception:
                pass

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.SPEAKER,
                available=speaker_detected,
                details=speaker_details,
                detection_method="aplay" if shutil.which("aplay") else "system_profiler",
            )
        )

        # No audio fallback
        has_audio = mic_detected or speaker_detected
        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.AUDIO_NONE,
                available=not has_audio,
                detection_method="fallback",
            )
        )

        return capabilities

    def _scan_leds(self) -> list[CapabilitySpec]:
        """Detect LED capabilities."""
        capabilities = []

        # Check existing hardware config
        led_enabled = self.hardware_config.get("led", {}).get("enabled", False)
        led_details = {}
        if led_enabled:
            led_details = {
                "pin": self.hardware_config.get("led", {}).get("pin", 18),
                "num_pixels": self.hardware_config.get("led", {}).get("num_pixels", 8),
            }

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.LED_STRIP,
                available=led_enabled,
                details=led_details,
                detection_method="config",
            )
        )

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.LED_NONE,
                available=not led_enabled,
                detection_method="fallback",
            )
        )

        return capabilities

    def _scan_fans(self) -> list[CapabilitySpec]:
        """Detect fan control capabilities."""
        capabilities = []

        # Check existing hardware config
        fan_enabled = self.hardware_config.get("fan", {}).get("enabled", False)
        fan_details = {}
        if fan_enabled:
            fan_details = {
                "pin": self.hardware_config.get("fan", {}).get("pin", 12),
                "min_temp": self.hardware_config.get("fan", {}).get("min_temp", 40),
                "max_temp": self.hardware_config.get("fan", {}).get("max_temp", 70),
            }

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.FAN_PWM,
                available=fan_enabled,
                details=fan_details,
                detection_method="config",
            )
        )

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.FAN_NONE,
                available=not fan_enabled,
                detection_method="fallback",
            )
        )

        return capabilities

    def _scan_sensors(self) -> list[CapabilitySpec]:
        """Detect sensor capabilities."""
        capabilities = []

        # Temperature sensor (common on Pi)
        temp_detected = False
        temp_details = {}

        thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if thermal_path.exists():
            temp_detected = True
            try:
                temp_c = int(thermal_path.read_text().strip()) / 1000.0
                temp_details["current_temp_c"] = temp_c
            except Exception:
                pass

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.SENSOR_TEMP,
                available=temp_detected,
                details=temp_details,
                detection_method="thermal_zone",
            )
        )

        # Other sensors would be detected via I2C or config
        # For now, mark as unavailable
        for sensor in [
            HardwareCapability.SENSOR_HUMIDITY,
            HardwareCapability.SENSOR_MOTION,
            HardwareCapability.SENSOR_LIGHT,
        ]:
            capabilities.append(
                CapabilitySpec(
                    capability=sensor,
                    available=False,
                    detection_method="not_implemented",
                )
            )

        return capabilities

    def _scan_network(self) -> list[CapabilitySpec]:
        """Detect network capabilities."""
        capabilities = []

        # Get network interfaces
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        has_ethernet = False
        has_wifi = False
        has_bluetooth = False

        for iface_name, addrs in interfaces.items():
            iface_stats = stats.get(iface_name)
            if not iface_stats or not iface_stats.isup:
                continue

            name_lower = iface_name.lower()

            # Ethernet (eth*, en*, enp*)
            if any(name_lower.startswith(p) for p in ["eth", "en0", "en1", "enp"]):
                has_ethernet = True

            # WiFi (wlan*, wl*)
            if any(name_lower.startswith(p) for p in ["wlan", "wl", "wifi"]):
                has_wifi = True

        # Bluetooth detection
        if shutil.which("bluetoothctl"):
            try:
                result = subprocess.run(
                    ["bluetoothctl", "show"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and "Powered: yes" in result.stdout:
                    has_bluetooth = True
            except Exception:
                pass

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.NETWORK_ETHERNET,
                available=has_ethernet,
                detection_method="psutil",
            )
        )

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.NETWORK_WIFI,
                available=has_wifi,
                detection_method="psutil",
            )
        )

        capabilities.append(
            CapabilitySpec(
                capability=HardwareCapability.NETWORK_BLUETOOTH,
                available=has_bluetooth,
                detection_method="bluetoothctl",
            )
        )

        return capabilities

    def _scan_storage(self) -> list[CapabilitySpec]:
        """Detect storage capabilities."""
        capabilities = []

        # Analyze disk partitions
        partitions = psutil.disk_partitions()

        has_ssd = False
        has_hdd = False
        has_sd = False
        has_nas = False

        for part in partitions:
            device = part.device.lower()
            fstype = part.fstype.lower()
            mountpoint = part.mountpoint

            # NAS detection (NFS, CIFS, network mounts)
            if fstype in ["nfs", "nfs4", "cifs", "smbfs"]:
                has_nas = True
                continue

            # SD card detection (common on Pi)
            if "mmcblk" in device:
                has_sd = True
                continue

            # Try to detect SSD vs HDD via rotational flag
            if device.startswith("/dev/"):
                # Extract device name (e.g., sda from /dev/sda1)
                base_device = device.split("/")[-1].rstrip("0123456789")
                rotational_path = Path(f"/sys/block/{base_device}/queue/rotational")
                if rotational_path.exists():
                    try:
                        rotational = int(rotational_path.read_text().strip())
                        if rotational == 0:
                            has_ssd = True
                        else:
                            has_hdd = True
                    except Exception:
                        pass

        # macOS: assume SSD for now (most Macs have SSDs)
        if platform.system() == "Darwin":
            has_ssd = True

        capabilities.extend([
            CapabilitySpec(
                capability=HardwareCapability.STORAGE_SSD,
                available=has_ssd,
                detection_method="rotational_flag",
            ),
            CapabilitySpec(
                capability=HardwareCapability.STORAGE_HDD,
                available=has_hdd,
                detection_method="rotational_flag",
            ),
            CapabilitySpec(
                capability=HardwareCapability.STORAGE_SD,
                available=has_sd,
                detection_method="device_name",
            ),
            CapabilitySpec(
                capability=HardwareCapability.STORAGE_NAS,
                available=has_nas,
                detection_method="fstype",
            ),
        ])

        return capabilities

    def _detect_i2c_device(self, address: int) -> bool:
        """Check if an I2C device exists at the given address."""
        if not shutil.which("i2cdetect"):
            return False

        try:
            result = subprocess.run(
                ["i2cdetect", "-y", "1"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Address format in output is hex without 0x
                addr_str = f"{address:02x}"
                return addr_str in result.stdout.lower()
        except Exception:
            pass

        return False
