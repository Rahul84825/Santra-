"""
Intelligent Audio Device Resolver for Jarvis.
Automatically detects and pairs Bluetooth headsets/earbuds (e.g. Airdopes, AirPods, Galaxy Buds, etc.)
with the active audio input stream, preventing device routing mismatches where output plays to earbuds
while input is mistakenly captured from the laptop's internal microphone.
Supports dynamic hardware hot-swap, sample-rate capability detection, and PortAudio topology refreshes.
"""

import re
import logging
import threading
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger("Jarvis.AudioDeviceResolver")

# Generic tokens to exclude when extracting hardware device model names
EXCLUDED_TOKENS = {
    "headphones", "headset", "earbuds", "speakers", "speaker", "audio",
    "realtek", "device", "input", "output", "hands-free", "handsfree",
    "directsound", "wasapi", "microsoft", "mapper", "stereo", "capture"
}

_CACHE_LOCK = threading.Lock()


class AudioDeviceResult(tuple):
    """Result tuple representing resolved audio device.
    Maintains 100% backward compatibility as a 2-tuple (device_index, device_name),
    while exposing hardware sample rate and resampling metadata.
    """
    def __new__(cls, index: Optional[int], name: str, sample_rate: int = 16000, requires_resampling: bool = False):
        return super().__new__(cls, (index, name))

    def __init__(self, index: Optional[int], name: str, sample_rate: int = 16000, requires_resampling: bool = False):
        self.device_index = index
        self.device_name = name
        self.sample_rate = sample_rate
        self.requires_resampling = requires_resampling

    @property
    def index(self) -> Optional[int]:
        return self[0]

    @property
    def name(self) -> str:
        return self[1]


def refresh_device_cache() -> bool:
    """Thread-safe re-initialization of PortAudio subsystem to discover newly plugged
    or unplugged audio hardware on Windows/Linux.
    """
    with _CACHE_LOCK:
        try:
            from core.lazy_loader import lazy_import
            sd = lazy_import("sounddevice")
            if hasattr(sd, "_terminate") and hasattr(sd, "_initialize"):
                sd._terminate()
                sd._initialize()
                logger.info("[AUDIO_ROUTER] PortAudio device cache refreshed successfully.")
                return True
        except Exception as e:
            logger.warning(f"[AUDIO_ROUTER] Failed to refresh PortAudio device cache: {e}")
        return False


def get_device_topology_signature() -> Tuple[Any, ...]:
    """Returns a lightweight, fast signature representing the current audio hardware topology.
    Used by background watchdogs to detect hardware changes in sub-millisecond time.
    """
    try:
        from core.lazy_loader import lazy_import
        sd = lazy_import("sounddevice")
        devices = sd.query_devices()
        def_devs = tuple(sd.default.device) if hasattr(sd.default, "device") else ()
        names = tuple(d.get("name", "") for d in devices)
        return (def_devs, len(devices), names)
    except Exception:
        return ()


def get_all_audio_devices() -> List[Dict[str, Any]]:
    """Returns a list of all audio devices available to sounddevice."""
    try:
        from core.lazy_loader import lazy_import
        sd = lazy_import("sounddevice")
        devices = sd.query_devices()
        return list(devices)
    except Exception as e:
        logger.error(f"Failed to query audio devices: {e}")
        return []


def _check_rate_support(sd, device_idx: int) -> Tuple[bool, int, bool]:
    """Checks whether the device natively supports 16kHz mono.
    If not, tests its default hardware sample rate (e.g. 44.1kHz or 48kHz).
    Returns: (is_supported, sample_rate, requires_resampling)
    """
    # 1. First priority: native 16000Hz mono
    try:
        sd.check_input_settings(device=device_idx, samplerate=16000, channels=1)
        return True, 16000, False
    except Exception:
        pass

    # 2. Second priority: native default hardware rate
    try:
        dev_info = sd.query_devices(device_idx)
        native_rate = int(dev_info.get("default_samplerate", 44100))
        sd.check_input_settings(device=device_idx, samplerate=native_rate, channels=1)
        return True, native_rate, True
    except Exception:
        pass

    # 3. Third priority: test standard fallback rates
    for rate in (48000, 44100):
        try:
            sd.check_input_settings(device=device_idx, samplerate=rate, channels=1)
            return True, rate, True
        except Exception:
            continue

    return False, 16000, False


def resolve_audio_input_device(preferred: Optional[Any] = None, force_refresh: bool = False) -> AudioDeviceResult:
    """
    Intelligently resolves the audio input device index.

    Priority:
    1. Explicit User Preference (exact index or name substring)
    2. Headset Auto-Pairing: If default audio output is a Bluetooth headset/earbuds,
       automatically pairs with the corresponding headset microphone.
    3. System Default Input Device
    4. First available input device fallback

    Returns:
        AudioDeviceResult tuple of (device_index, device_name) with .sample_rate and .requires_resampling attributes.
    """
    if force_refresh:
        refresh_device_cache()

    from core.lazy_loader import lazy_import
    sd = lazy_import("sounddevice")

    try:
        devices = list(sd.query_devices())
        def_in, def_out = sd.default.device
    except Exception as e:
        logger.warning(f"Could not query default sound devices: {e}")
        return AudioDeviceResult(None, "System Default", 16000, False)

    if not devices:
        return AudioDeviceResult(None, "System Default", 16000, False)

    # 1. Check explicit preferred configuration (if not "auto" or None)
    if preferred is not None and str(preferred).strip().lower() not in ["auto", "none", ""]:
        # Numeric index
        if isinstance(preferred, int) or (isinstance(preferred, str) and preferred.strip().isdigit()):
            idx = int(preferred)
            if 0 <= idx < len(devices) and devices[idx]["max_input_channels"] > 0:
                name = devices[idx]["name"]
                supported, rate, resample = _check_rate_support(sd, idx)
                if supported:
                    logger.info(f"[AUDIO_ROUTER] Using explicitly configured audio input device [{idx}]: {name} (Rate={rate}Hz, Resample={resample})")
                    return AudioDeviceResult(idx, name, rate, resample)
                else:
                    logger.warning(f"[AUDIO_ROUTER] Preferred device [{idx}] '{name}' rejected input settings.")

        # Name substring match
        pref_str = str(preferred).strip().lower()
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and pref_str in d["name"].lower():
                supported, rate, resample = _check_rate_support(sd, i)
                if supported:
                    logger.info(f"[AUDIO_ROUTER] Matched explicitly preferred input name '{preferred}' -> [{i}]: {d['name']} (Rate={rate}Hz)")
                    return AudioDeviceResult(i, d["name"], rate, resample)

    # 2. Automatic Headset Pairing
    # If the user has Bluetooth earbuds/headset as the default output (e.g. Airdopes, AirPods, Galaxy Buds),
    # find the matching headset microphone.
    if def_out is not None and 0 <= def_out < len(devices):
        out_name = devices[def_out]["name"]
        
        # Tokenize output device name to isolate unique brand/model identifiers
        raw_tokens = re.split(r"[\s\(\)\-_,]+", out_name)
        hardware_tokens = [
            t for t in raw_tokens 
            if len(t) >= 3 and t.lower() not in EXCLUDED_TOKENS
        ]

        if hardware_tokens:
            for token in hardware_tokens:
                token_lower = token.lower()
                for i, d in enumerate(devices):
                    if d["max_input_channels"] > 0 and token_lower in d["name"].lower():
                        supported, rate, resample = _check_rate_support(sd, i)
                        if supported:
                            logger.info(
                                f"[AUDIO_ROUTER] Headset auto-pairing active! "
                                f"Output: '{out_name}' -> Matched Input: [{i}] '{d['name']}' (Rate={rate}Hz, Resample={resample})"
                            )
                            return AudioDeviceResult(i, d["name"], rate, resample)

    # 3. Fallback to System Default Input Device
    if def_in is not None and 0 <= def_in < len(devices):
        def_name = devices[def_in]["name"]
        supported, rate, resample = _check_rate_support(sd, def_in)
        if supported:
            logger.info(f"[AUDIO_ROUTER] Using system default input device [{def_in}]: {def_name} (Rate={rate}Hz, Resample={resample})")
            return AudioDeviceResult(def_in, def_name, rate, resample)
        else:
            logger.warning(f"Default input device [{def_in}] failed rate checks. Searching fallbacks...")

    # 4. Search any valid input device supporting input settings
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            supported, rate, resample = _check_rate_support(sd, i)
            if supported:
                logger.info(f"[AUDIO_ROUTER] Fallback input device selected [{i}]: {d['name']} (Rate={rate}Hz, Resample={resample})")
                return AudioDeviceResult(i, d["name"], rate, resample)

    return AudioDeviceResult(None, "System Default", 16000, False)
