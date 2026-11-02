"""
Audio Device Watcher & Hot-Swap Monitor for SANTRA.
Provides zero-latency native Windows 11 audio endpoint notification via Windows Core Audio (MMDevice API)
with robust cross-platform heartbeat watchdog and automatic hot-swap recovery dispatch.
"""

import os
import sys
import time
import logging
import threading
from typing import Optional, Callable, List, Tuple, Dict, Any

logger = logging.getLogger("Jarvis.AudioDeviceWatcher")

# Windows Core Audio COM Interfaces via pycaw / comtypes
_COM_AVAILABLE = False
try:
    if sys.platform == "win32":
        from comtypes import COMObject
        from pycaw.pycaw import AudioUtilities, IMMNotificationClient
        _COM_AVAILABLE = True
except Exception as com_err:
    logger.debug(f"Windows Core Audio COM interfaces unavailable: {com_err}")
    _COM_AVAILABLE = False


class _WindowsNotificationClient:
    """Internal COM client for Windows IMMNotificationClient callbacks."""
    pass

if _COM_AVAILABLE:
    class _WindowsEndpointClient(COMObject):
        _com_interfaces_ = [IMMNotificationClient]

        def __init__(self, callback: Callable[[str, Dict[str, Any]], None]):
            super().__init__()
            self._callback = callback

        def OnDeviceStateChanged(self, pwstrDeviceId, dwNewState):
            try:
                self._callback("state_changed", {"device_id": str(pwstrDeviceId), "state": int(dwNewState)})
            except Exception as e:
                logger.debug(f"Error in OnDeviceStateChanged: {e}")
            return 0

        def OnDeviceAdded(self, pwstrDeviceId):
            try:
                self._callback("device_added", {"device_id": str(pwstrDeviceId)})
            except Exception as e:
                logger.debug(f"Error in OnDeviceAdded: {e}")
            return 0

        def OnDeviceRemoved(self, pwstrDeviceId):
            try:
                self._callback("device_removed", {"device_id": str(pwstrDeviceId)})
            except Exception as e:
                logger.debug(f"Error in OnDeviceRemoved: {e}")
            return 0

        def OnDefaultDeviceChanged(self, flow, role, pwstrDefaultDeviceId):
            try:
                self._callback("default_changed", {
                    "flow": int(flow),
                    "role": int(role),
                    "device_id": str(pwstrDefaultDeviceId) if pwstrDefaultDeviceId else None
                })
            except Exception as e:
                logger.debug(f"Error in OnDefaultDeviceChanged: {e}")
            return 0

        def OnPropertyValueChanged(self, pwstrDeviceId, key):
            return 0


class AudioDeviceWatcher:
    """Monitors audio hardware endpoint changes, disconnections, and stream failures.
    
    Combines:
    1. Native Windows MMDevice API notifications (instant event-driven trigger).
    2. Cross-platform heartbeat watchdog (polls stream liveness, callback timeout, and topology shifts).
    3. Smart debouncing to coalesce rapid Windows disconnect/reconnect bursts into a single clean transition.
    """

    def __init__(
        self,
        on_endpoint_change: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        debounce_seconds: float = 0.25,
        watchdog_interval: float = 1.0,
        stream_health_checker: Optional[Callable[[], Tuple[bool, str]]] = None
    ):
        self.on_endpoint_change = on_endpoint_change
        self.debounce_seconds = debounce_seconds
        self.watchdog_interval = watchdog_interval
        self.stream_health_checker = stream_health_checker

        self._running = False
        self._lock = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None
        self._last_event_time = 0.0
        self._pending_events: List[Tuple[str, Dict[str, Any]]] = []

        # COM specific
        self._com_client = None
        self._com_client_ptr = None
        self._enumerator = None
        self._com_registered = False

        # Watchdog thread
        self._watchdog_thread: Optional[threading.Thread] = None

        # Topology tracking
        self._last_topology_signature = None

    def start(self):
        """Starts the audio device watcher (COM notifications and background watchdog)."""
        with self._lock:
            if self._running:
                return
            self._running = True

            # Register COM notifications on Windows if available
            if _COM_AVAILABLE and sys.platform == "win32":
                try:
                    self._com_client = _WindowsEndpointClient(self._on_raw_event)
                    self._enumerator = AudioUtilities.GetDeviceEnumerator()
                    self._com_client_ptr = self._com_client.QueryInterface(IMMNotificationClient)
                    res = self._enumerator.RegisterEndpointNotificationCallback(self._com_client_ptr)
                    if res == 0:
                        self._com_registered = True
                        logger.info("[AUDIO_WATCHER] Native Windows Core Audio endpoint notification registered.")
                    else:
                        logger.warning(f"[AUDIO_WATCHER] Windows COM registration returned code {res}. Relying on watchdog.")
                except Exception as ex:
                    logger.warning(f"[AUDIO_WATCHER] Failed to register Windows COM endpoint client: {ex}. Relying on watchdog.")
                    self._com_registered = False

            # Initialize baseline topology signature
            try:
                from core.audio_device_resolver import get_device_topology_signature
                self._last_topology_signature = get_device_topology_signature()
            except Exception:
                self._last_topology_signature = None

            # Start watchdog thread
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="AudioDeviceWatchdogThread",
                daemon=True
            )
            self._watchdog_thread.start()
            logger.info("[AUDIO_WATCHER] Audio device watcher and health watchdog started.")

    def stop(self):
        """Stops the audio device watcher and releases COM registrations."""
        with self._lock:
            if not self._running:
                return
            self._running = False

            # Cancel pending debounce timer
            if self._debounce_timer:
                try:
                    self._debounce_timer.cancel()
                except Exception:
                    pass
                self._debounce_timer = None

            # Unregister COM
            if self._com_registered and self._enumerator and self._com_client_ptr:
                try:
                    self._enumerator.UnregisterEndpointNotificationCallback(self._com_client_ptr)
                    logger.info("[AUDIO_WATCHER] Windows Core Audio endpoint notification unregistered.")
                except Exception as ex:
                    logger.debug(f"[AUDIO_WATCHER] Error unregistering COM callback: {ex}")
                self._com_registered = False
                self._com_client_ptr = None
                self._enumerator = None
                self._com_client = None

        if self._watchdog_thread and threading.current_thread() != self._watchdog_thread:
            self._watchdog_thread.join(timeout=1.5)
            self._watchdog_thread = None

        logger.info("[AUDIO_WATCHER] Audio device watcher stopped.")

    def _on_raw_event(self, event_type: str, details: Dict[str, Any]):
        """Raw event callback received from Windows COM or Watchdog."""
        with self._lock:
            if not self._running:
                return

            self._pending_events.append((event_type, details))
            self._last_event_time = time.time()

            # Reset or start debounce timer
            if self._debounce_timer:
                try:
                    self._debounce_timer.cancel()
                except Exception:
                    pass

            self._debounce_timer = threading.Timer(self.debounce_seconds, self._dispatch_debounced_event)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _dispatch_debounced_event(self):
        """Dispatches consolidated event after debounce window expires."""
        with self._lock:
            if not self._running or not self._pending_events:
                return
            events = list(self._pending_events)
            self._pending_events.clear()
            self._debounce_timer = None

        # Consolidate events
        primary_event = events[-1][0]
        logger.info(f"[AUDIO_WATCHER] Debounced endpoint change detected ({len(events)} events coalesced). Primary: '{primary_event}'.")

        # Update topology signature
        try:
            from core.audio_device_resolver import get_device_topology_signature
            self._last_topology_signature = get_device_topology_signature()
        except Exception:
            pass

        if self.on_endpoint_change:
            try:
                self.on_endpoint_change(primary_event, {"coalesced_count": len(events), "events": events})
            except Exception as ex:
                logger.error(f"[AUDIO_WATCHER] Error executing endpoint change callback: {ex}", exc_info=True)

    def trigger_recovery_now(self, reason: str = "manual_trigger"):
        """Programmatically triggers immediate audio stream recovery."""
        self._on_raw_event(reason, {"manual": True, "timestamp": time.time()})

    def _watchdog_loop(self):
        """Background loop monitoring stream health, callback heartbeat, and topology shifts."""
        logger.debug("[AUDIO_WATCHER] Watchdog loop running.")
        from core.audio_device_resolver import get_device_topology_signature

        while self._running:
            time.sleep(self.watchdog_interval)
            if not self._running:
                break

            try:
                # 1. Check Stream Health if checker registered
                if self.stream_health_checker:
                    healthy, reason = self.stream_health_checker()
                    if not healthy:
                        logger.warning(f"[AUDIO_WATCHER] Stream health check failed: {reason}. Triggering hot-swap recovery.")
                        self._on_raw_event("stream_unhealthy", {"reason": reason})
                        continue

                # 2. Check Device Topology Signature Shift
                current_sig = get_device_topology_signature()
                if self._last_topology_signature is not None and current_sig != self._last_topology_signature:
                    logger.info("[AUDIO_WATCHER] Hardware topology signature changed. Triggering hot-swap recovery.")
                    self._last_topology_signature = current_sig
                    self._on_raw_event("topology_shift", {"new_signature": str(current_sig)})

            except Exception as e:
                logger.debug(f"[AUDIO_WATCHER] Watchdog iteration error: {e}")

        logger.debug("[AUDIO_WATCHER] Watchdog loop exited.")

