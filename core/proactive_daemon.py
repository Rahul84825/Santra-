import time
import psutil
import logging
import threading
from typing import Callable, Optional

from memory.persistent_memory import persistent_memory
from modules.communication.email_service import email_service

logger = logging.getLogger("Jarvis.ProactiveDaemon")

class ProactiveDaemon:
    """Proactive background monitor that watches system status, battery, reminders,
    and background notifications, alerting the user without needing a wake-word trigger.
    """

    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.on_proactive_alert_cb: Optional[Callable[[str, str, bool], None]] = None
        
        # State tracking to prevent notification spam
        self._last_battery_alert_time = 0.0
        self._battery_alert_dispatched = False
        self._battery_alert_cooldown = 600.0  # 10 minutes repeat cooldown if continuously low
        self._last_email_check_time = 0.0
        self._known_unread_count = 0

    def start(self, on_proactive_alert: Optional[Callable[[str, str, bool], None]] = None):
        """Starts background proactive monitoring loop."""
        if self._running:
            return

        if on_proactive_alert:
            self.on_proactive_alert_cb = on_proactive_alert

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, name="ProactiveDaemonThread", daemon=True)
        self._thread.start()
        logger.info("Jarvis Proactive Background Daemon started.")

    def stop(self):
        """Halts background proactive monitor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("Jarvis Proactive Background Daemon stopped.")

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_battery()
                self._check_email_updates()
            except Exception as e:
                logger.error(f"Error during proactive daemon check: {e}")

            # Sleep in small slices to allow rapid shutdown
            for _ in range(int(self.check_interval)):
                if not self._running:
                    break
                time.sleep(1.0)

    def _check_battery(self):
        """Checks if battery is critically low and discharging using power_manager telemetry.
        - Respects configurable low threshold (default 15%).
        - Alerts once upon crossing threshold while discharging.
        - Does not spam every polling cycle (has 10-min cooldown if continuously discharging below threshold).
        - Re-arms immediately when plugged in or when charged above threshold + hysteresis.
        - Emits no spurious warnings on missing or invalid telemetry.
        """
        try:
            from core.os.power_manager import power_manager
            telemetry = power_manager.get_battery_telemetry()
        except Exception as te:
            logger.debug(f"[PROACTIVE_BATTERY] Failed to get battery telemetry: {te}")
            return

        if not telemetry or not telemetry.get("has_battery") or not telemetry.get("telemetry_available"):
            # Missing or invalid telemetry: Do NOT generate an alert
            return

        percent = telemetry.get("percentage")
        if percent is None:
            return

        power_plugged = telemetry.get("power_plugged", False)
        is_charging = telemetry.get("is_charging", False)

        try:
            from config.settings import config
            threshold = getattr(config, "low_battery_threshold", 15)
        except Exception:
            threshold = 15

        # 1. Re-arm if plugged into AC power or actively charging
        if power_plugged or is_charging:
            if self._battery_alert_dispatched:
                logger.info("[PROACTIVE_BATTERY] Power connected; re-arming low-battery alert.")
                self._battery_alert_dispatched = False
            return

        # 2. Re-arm if battery recovered above threshold + hysteresis (e.g. 15% + 3% = 18%)
        if percent > (threshold + 3):
            if self._battery_alert_dispatched:
                logger.info(f"[PROACTIVE_BATTERY] Battery recovered to {percent}%; re-arming low-battery alert.")
                self._battery_alert_dispatched = False
            return

        # 3. Discharging and at or below threshold: trigger alert
        if percent <= threshold:
            now = time.time()
            if not self._battery_alert_dispatched or (now - self._last_battery_alert_time > self._battery_alert_cooldown):
                self._battery_alert_dispatched = True
                self._last_battery_alert_time = now
                msg = f"Battery warning: Your battery is at {percent}%. Please connect the charger."
                logger.warning(f"[PROACTIVE ALERT] {msg}")
                self._dispatch_alert("Low Battery", msg, speak=True)

    def _check_email_updates(self):
        """Checks for new unread emails periodically."""
        now = time.time()
        if now - self._last_email_check_time > 300:  # Every 5 minutes
            self._last_email_check_time = now
            try:
                unread = email_service.get_unread_emails(limit=3)
                if unread and not unread[0].get("is_demo"):
                    count = len(unread)
                    if count > self._known_unread_count and count > 0:
                        first_subject = unread[0].get("subject", "New message")
                        sender = unread[0].get("sender", "Unknown").split("<")[0].strip()
                        msg = f"You have {count} unread email{'s' if count > 1 else ''}. Latest from {sender}: {first_subject}"
                        self._dispatch_alert("New Email", msg, speak=False)
                    self._known_unread_count = count
            except Exception:
                pass

    def _dispatch_alert(self, title: str, message: str, speak: bool = False):
        if self.on_proactive_alert_cb:
            try:
                self.on_proactive_alert_cb(title, message, speak)
            except Exception as e:
                logger.error(f"Error in proactive alert callback: {e}")

# Singleton instance
proactive_daemon = ProactiveDaemon()
