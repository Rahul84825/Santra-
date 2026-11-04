"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Resource Guard Module

Governs background maintenance execution to prevent VRAM, CPU, and thread contention.
Protects main thread, gaming sessions, and active voice interactions.
"""

import time
import logging
import threading
from typing import Callable, Dict, Optional, Any, Set
import psutil

logger = logging.getLogger("Santra.Evolution.ResourceGuard")

# Games and competitive 3D applications where background CPU/GPU spikes cause frame drops
GAME_PROCESS_NAMES: Set[str] = {
    "valorant-win64-shipping.exe",
    "valorant.exe",
    "riotclientservices.exe",
    "cs2.exe",
    "csgo.exe",
    "gta5.exe",
    "r5apex.exe",
    "overwatch.exe",
    "fortniteclient-win64-shipping.exe",
    "fortnitelauncher.exe",
    "league of legends.exe",
    "dota2.exe",
    "eldenring.exe",
    "cyberpunk2077.exe",
    "minecraft.windows.exe",
    "javaw.exe",
}

# Runtime statuses where SANTRA is actively interacting with the user
ACTIVE_VOICE_STATUSES = {
    "LISTENING",
    "TRANSCRIBING",
    "ROUTING",
    "THINKING",
    "SYNTHESIZING",
    "SPEAKING",
    "STREAMING_RESPONSE",
    "RESEARCH_PLANNING",
    "WAITING_FOR_NVIDIA",
}


class ResourceGuard:
    """Evaluates system headroom and yields background work to foreground tasks."""

    def __init__(
        self,
        max_cpu_percent: float = 30.0,
        max_ram_percent: float = 80.0,
        game_scan_interval_s: float = 30.0
    ):
        self.max_cpu_percent = max_cpu_percent
        self.max_ram_percent = max_ram_percent
        self.game_scan_interval_s = game_scan_interval_s

        self._lock = threading.Lock()
        self._last_game_scan_time: float = 0.0
        self._cached_game_detected: Optional[str] = None
        self._activity_callbacks: list[Callable[[], bool]] = []

    def register_activity_check(self, fn: Callable[[], bool]):
        """Registers a callable that returns True when voice/command processing is active."""
        with self._lock:
            if fn not in self._activity_callbacks:
                self._activity_callbacks.append(fn)

    def is_voice_or_command_active(self, runtime_status: Optional[str] = None) -> bool:
        """Checks if voice input, routing, or speaking is currently taking place."""
        if runtime_status and runtime_status.upper() in ACTIVE_VOICE_STATUSES:
            return True

        with self._lock:
            callbacks = list(self._activity_callbacks)

        for cb in callbacks:
            try:
                if cb():
                    return True
            except Exception as e:
                logger.debug(f"[RESOURCE_GUARD] Activity check callback error: {e}")

        return False

    def check_game_running(self) -> Optional[str]:
        """
        Scans running processes for competitive games with a 30-second TTL cache
        to avoid repeatedly enumerating hundreds of Windows processes.
        """
        now = time.time()
        with self._lock:
            if (now - self._last_game_scan_time) < self.game_scan_interval_s:
                return self._cached_game_detected

        detected = None
        try:
            for proc in psutil.process_iter(['name']):
                try:
                    pname = (proc.info.get('name') or '').lower()
                    if pname in GAME_PROCESS_NAMES:
                        detected = pname
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.debug(f"[RESOURCE_GUARD] Process scan warning: {e}")

        with self._lock:
            self._last_game_scan_time = now
            self._cached_game_detected = detected

        return detected

    def can_run_background_tasks(self, runtime_status: Optional[str] = None) -> bool:
        """
        Returns True if CPU < 30%, RAM < 80%, not gaming, AC plugged or healthy battery,
        and no active voice interaction is occurring.
        """
        # 1. Voice / User Activity Check (fastest, memory lookup)
        if self.is_voice_or_command_active(runtime_status):
            return False

        # 2. Game Check (cached 30s)
        game = self.check_game_running()
        if game:
            return False

        # 3. CPU Check (instant, non-blocking)
        try:
            cpu = psutil.cpu_percent(interval=None)
            if cpu > self.max_cpu_percent:
                return False
        except Exception:
            pass

        # 4. RAM Check
        try:
            ram = psutil.virtual_memory().percent
            if ram > self.max_ram_percent:
                return False
        except Exception:
            pass

        # 5. Battery Check (avoid draining battery on untethered laptop)
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                # If on battery power and below 50%, pause background tasks
                if not battery.power_plugged and battery.percent < 50:
                    return False
        except Exception:
            pass

        return True

    def get_system_snapshot(self, runtime_status: Optional[str] = None) -> Dict[str, Any]:
        """Provides a complete resource state report for logging and diagnostics."""
        cpu = 0.0
        ram = 0.0
        plugged = True
        battery_pct = 100

        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            batt = psutil.sensors_battery()
            if batt:
                plugged = bool(batt.power_plugged)
                battery_pct = batt.percent
        except Exception:
            pass

        game = self.check_game_running()
        voice_active = self.is_voice_or_command_active(runtime_status)
        can_run = (
            not voice_active
            and game is None
            and cpu <= self.max_cpu_percent
            and ram <= self.max_ram_percent
            and (plugged or battery_pct >= 50)
        )

        reasons = []
        if voice_active:
            reasons.append("Voice/UI interaction active")
        if game:
            reasons.append(f"Gaming process active ({game})")
        if cpu > self.max_cpu_percent:
            reasons.append(f"CPU high ({cpu:.1f}% > {self.max_cpu_percent}%)")
        if ram > self.max_ram_percent:
            reasons.append(f"RAM high ({ram:.1f}% > {self.max_ram_percent}%)")
        if not plugged and battery_pct < 50:
            reasons.append(f"Low battery ({battery_pct}% unplugged)")

        return {
            "can_run": can_run,
            "cpu_percent": cpu,
            "memory_percent": ram,
            "battery_plugged": plugged,
            "battery_percent": battery_pct,
            "game_detected": game,
            "voice_active": voice_active,
            "reasons": reasons
        }


# Singleton instance
resource_guard = ResourceGuard()
