"""
Unit and Integration Tests for Proactive Low-Battery Alerts:
- Threshold crossing while discharging triggers alert
- Repeated polling while below threshold does not spam duplicate alerts (deduplication)
- Charging / plugged AC suppresses inappropriate alerts
- Missing or invalid telemetry produces no fabricated warning
- Alert re-arming after AC power connection
- Alert re-arming after recovery above threshold + hysteresis
- Configurable threshold support
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from core.proactive_daemon import ProactiveDaemon


class TestLowBatteryAlerts(unittest.TestCase):
    """Verifies that automatic proactive low-battery alerts behave reliably without alert spam."""

    def setUp(self):
        self.daemon = ProactiveDaemon(check_interval=1.0)
        self.dispatched_alerts = []
        self.daemon.on_proactive_alert_cb = lambda title, msg, speak: self.dispatched_alerts.append(
            {"title": title, "message": msg, "speak": speak}
        )

    def test_alert_triggered_when_discharging_below_threshold(self):
        """When discharging and battery is at 12% (threshold 15%), an alert is dispatched with voice enabled."""
        mock_telemetry = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 12,
            "power_plugged": False,
            "is_charging": False,
            "status": "12% discharging"
        }
        with patch("core.os.power_manager.power_manager.get_battery_telemetry", return_value=mock_telemetry):
            self.daemon._check_battery()

            self.assertEqual(len(self.dispatched_alerts), 1)
            alert = self.dispatched_alerts[0]
            self.assertEqual(alert["title"], "Low Battery")
            self.assertTrue(alert["speak"])
            self.assertIn("12%", alert["message"])
            self.assertTrue(self.daemon._battery_alert_dispatched)

    def test_no_repeated_alerts_on_subsequent_polling_cycles(self):
        """While remaining low and discharging, subsequent checks should not repeat the alert within cooldown."""
        mock_telemetry = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 11,
            "power_plugged": False,
            "is_charging": False
        }
        with patch("core.os.power_manager.power_manager.get_battery_telemetry", return_value=mock_telemetry):
            # First cycle: alert triggers
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 1)

            # Second cycle (30 seconds later): should be suppressed by deduplication flag
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 1)

            # Third cycle: still suppressed
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 1)

    def test_charging_suppresses_low_battery_alert(self):
        """When plugged into AC power (even at 5%), no warning should be dispatched."""
        mock_telemetry = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 5,
            "power_plugged": True,
            "is_charging": True
        }
        with patch("core.os.power_manager.power_manager.get_battery_telemetry", return_value=mock_telemetry):
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 0)
            self.assertFalse(self.daemon._battery_alert_dispatched)

    def test_missing_or_invalid_telemetry_produces_no_warning(self):
        """When telemetry is unavailable or system has no battery, no spurious warnings are emitted."""
        mock_telemetry = {
            "has_battery": False,
            "telemetry_available": False,
            "percentage": None,
            "power_plugged": False
        }
        with patch("core.os.power_manager.power_manager.get_battery_telemetry", return_value=mock_telemetry):
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 0)

        with patch("core.os.power_manager.power_manager.get_battery_telemetry", return_value=None):
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 0)

    def test_alert_rearming_after_plugging_in(self):
        """Plugging in should re-arm the alert so that subsequent discharge below threshold triggers a fresh alert."""
        low_discharging = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 14,
            "power_plugged": False,
            "is_charging": False
        }
        plugged_in = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 14,
            "power_plugged": True,
            "is_charging": True
        }

        with patch("core.os.power_manager.power_manager.get_battery_telemetry") as mock_telem:
            # 1. First discharge triggers alert
            mock_telem.return_value = low_discharging
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 1)
            self.assertTrue(self.daemon._battery_alert_dispatched)

            # 2. User plugs in laptop: re-arms alert
            mock_telem.return_value = plugged_in
            self.daemon._check_battery()
            self.assertFalse(self.daemon._battery_alert_dispatched)

            # 3. User unplugs laptop while still low: should alert again
            mock_telem.return_value = low_discharging
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 2)
            self.assertTrue(self.daemon._battery_alert_dispatched)

    def test_alert_rearming_after_recovery_above_hysteresis(self):
        """When battery charges above threshold + hysteresis (e.g. 19% > 15% + 3%), alert re-arms."""
        low_discharging = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 10,
            "power_plugged": False,
            "is_charging": False
        }
        recovered_discharging = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 20,
            "power_plugged": False,
            "is_charging": False
        }

        with patch("core.os.power_manager.power_manager.get_battery_telemetry") as mock_telem:
            mock_telem.return_value = low_discharging
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 1)

            # Recovered above hysteresis threshold
            mock_telem.return_value = recovered_discharging
            self.daemon._check_battery()
            self.assertFalse(self.daemon._battery_alert_dispatched)

            # Drops below threshold again
            mock_telem.return_value = low_discharging
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 2)

    def test_configurable_threshold(self):
        """Custom threshold (e.g. 25%) should trigger alert when battery drops to 22%."""
        mock_telemetry = {
            "has_battery": True,
            "telemetry_available": True,
            "percentage": 22,
            "power_plugged": False,
            "is_charging": False
        }
        mock_config = MagicMock(low_battery_threshold=25)
        with patch("core.os.power_manager.power_manager.get_battery_telemetry", return_value=mock_telemetry), \
             patch.dict("sys.modules", {"config.settings": MagicMock(config=mock_config)}):
            self.daemon._check_battery()
            self.assertEqual(len(self.dispatched_alerts), 1)
            self.assertIn("22%", self.dispatched_alerts[0]["message"])


if __name__ == "__main__":
    unittest.main()
