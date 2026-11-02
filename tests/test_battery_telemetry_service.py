"""
Tests for Windows Battery Telemetry Service & Query Routing:
- Mocked percentage retrieval
- Charging / plugged AC status
- Unknown remaining-time handling (explicit message without invention)
- Missing battery / desktop without battery
- Telemetry cache TTL validation (freshness and expiry)
- Intent engine query routing
- Deterministic bypass in intelligence router (zero LLM overhead)
- Windows Hardware Integration Test (clearly separated from mocked tests)
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from core.os.power_manager import PowerManager
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import intelligence_router


class TestBatteryTelemetryMocked(unittest.TestCase):
    """Unit tests with mocked telemetry data to test all edge cases deterministically."""

    def setUp(self):
        self.power_mgr = PowerManager()

    def test_battery_on_ac_power_charging(self):
        """When plugged in, percent is reported and charging status is noted without inventing hours."""
        mock_battery = MagicMock(percent=85, power_plugged=True, secsleft=-2)
        with patch("psutil.sensors_battery", return_value=mock_battery):
            # Invalidate cache
            self.power_mgr._battery_cache_time = 0
            telemetry = self.power_mgr.get_battery_telemetry()

            self.assertTrue(telemetry["has_battery"])
            self.assertTrue(telemetry["telemetry_available"])
            self.assertEqual(telemetry["percentage"], 85)
            self.assertTrue(telemetry["power_plugged"])
            self.assertIn("85%", telemetry["message"])
            self.assertIn("plugged in", telemetry["message"].lower())

    def test_battery_discharging_with_valid_remaining_time(self):
        """When discharging and OS provides secsleft, remaining time is formatted accurately."""
        # 7200 seconds = 2 hours
        mock_battery = MagicMock(percent=65, power_plugged=False, secsleft=7200)
        with patch("psutil.sensors_battery", return_value=mock_battery):
            self.power_mgr._battery_cache_time = 0
            telemetry = self.power_mgr.get_battery_telemetry()

            self.assertEqual(telemetry["percentage"], 65)
            self.assertFalse(telemetry["power_plugged"])
            self.assertEqual(telemetry["time_remaining_seconds"], 7200)
            self.assertEqual(telemetry["time_remaining_formatted"], "2 hours")
            self.assertIn("2 hours", telemetry["message"])

    def test_battery_discharging_with_unknown_remaining_time(self):
        """When discharging and OS does not provide estimate, percentage is stated and estimate is explicitly unknown."""
        mock_battery = MagicMock(percent=45, power_plugged=False, secsleft=-1)
        with patch("psutil.sensors_battery", return_value=mock_battery):
            self.power_mgr._battery_cache_time = 0
            telemetry = self.power_mgr.get_battery_telemetry()

            self.assertEqual(telemetry["percentage"], 45)
            self.assertFalse(telemetry["power_plugged"])
            self.assertIsNone(telemetry["time_remaining_seconds"])
            self.assertIn("Windows did not provide a reliable time estimate", telemetry["message"])

    def test_no_battery_detected_desktop(self):
        """On a desktop system without a battery, report absence truthfully without fabricating readings."""
        def mock_sps(byref):
            byref._obj.BatteryFlag = 128
            byref._obj.ACLineStatus = 1
            return 1

        with patch("psutil.sensors_battery", return_value=None), \
             patch("ctypes.windll.kernel32.GetSystemPowerStatus", side_effect=mock_sps):
            self.power_mgr._battery_cache_time = 0
            telemetry = self.power_mgr.get_battery_telemetry()

            self.assertFalse(telemetry["has_battery"])
            self.assertTrue(telemetry["telemetry_available"])
            self.assertIsNone(telemetry["percentage"])
            self.assertIn("No battery detected", telemetry["message"])

    def test_battery_cache_ttl_behavior(self):
        """Cache should return same reading within 2 seconds, but refresh on subsequent call after expiry."""
        mock_1 = MagicMock(percent=90, power_plugged=True, secsleft=-2)
        mock_2 = MagicMock(percent=91, power_plugged=True, secsleft=-2)

        with patch("psutil.sensors_battery", side_effect=[mock_1, mock_2]) as mock_call:
            self.power_mgr._battery_cache_time = 0

            # First read (calls psutil)
            t1 = self.power_mgr.get_battery_telemetry()
            self.assertEqual(t1["percentage"], 90)
            self.assertEqual(mock_call.call_count, 1)

            # Second read within TTL (uses in-memory cache)
            t2 = self.power_mgr.get_battery_telemetry()
            self.assertEqual(t2["percentage"], 90)
            self.assertEqual(mock_call.call_count, 1)

            # Simulate TTL expiry
            self.power_mgr._battery_cache_time = time.time() - 5.0
            t3 = self.power_mgr.get_battery_telemetry()
            self.assertEqual(t3["percentage"], 91)
            self.assertEqual(mock_call.call_count, 2)


class TestBatteryIntentRouting(unittest.TestCase):
    """Verifies that all battery-life and power questions route directly to the deterministic tool."""

    @classmethod
    def setUpClass(cls):
        cls.intent_engine = IntentEngine()

    def test_battery_life_question_intents(self):
        queries = [
            "How much battery do I have?",
            "How much battery do I have left?",
            "How much battery life is left?",
            "What is my battery level?",
            "What's my battery percentage?",
            "Is my laptop charging?",
            "Am I plugged in?",
            "How long can I use the laptop?",
            "battery status",
            "battery percentage"
        ]
        for q in queries:
            node = self.intent_engine.parse(q)
            self.assertEqual(node.get("intent"), "system_telemetry", f"Failed intent on: '{q}'")
            self.assertEqual(node.get("action"), "battery_info", f"Failed action on: '{q}'")

    def test_intelligence_router_battery_bypass(self):
        """Ensures that battery questions bypass Layer 2 LLM in intelligence_router._is_informational_question."""
        battery_queries = [
            "How much battery do I have?",
            "How much battery do I have left?",
            "Is my laptop charging?",
            "Am I plugged in?",
            "How long can I use the laptop?"
        ]
        for q in battery_queries:
            clean = q.lower().strip()
            is_info = intelligence_router._is_informational_question(q, clean)
            self.assertFalse(
                is_info,
                f"Battery query '{q}' must NOT be treated as open-ended informational LLM question."
            )


class TestActualWindowsBatteryHardwareIntegration(unittest.TestCase):
    """Actual Windows 11 hardware integration test: reads real system telemetry."""

    def test_live_windows_battery_reading(self):
        power_mgr = PowerManager()
        # Invalidate cache to ensure fresh read from OS
        power_mgr._battery_cache_time = 0
        telemetry = power_mgr.get_battery_telemetry()

        print("\n--- ACTUAL WINDOWS 11 HARDWARE TELEMETRY ---")
        print(f"Has Battery: {telemetry.get('has_battery')}")
        print(f"Telemetry Available: {telemetry.get('telemetry_available')}")
        print(f"Percentage: {telemetry.get('percentage')}%")
        print(f"Power Plugged: {telemetry.get('power_plugged')}")
        print(f"Is Charging: {telemetry.get('is_charging')}")
        print(f"Time Remaining Formatted: {telemetry.get('time_remaining_formatted')}")
        print(f"Message: {telemetry.get('message')}")
        print("-------------------------------------------\n")

        self.assertIn("has_battery", telemetry)
        self.assertIn("telemetry_available", telemetry)
        self.assertIn("message", telemetry)

        # On this machine, verify that telemetry works truthfully
        if telemetry.get("has_battery"):
            self.assertTrue(telemetry["telemetry_available"])
            self.assertIsInstance(telemetry["percentage"], (int, float))
            self.assertGreaterEqual(telemetry["percentage"], 0)
            self.assertLessEqual(telemetry["percentage"], 100)
            self.assertIsInstance(telemetry["power_plugged"], bool)


if __name__ == "__main__":
    unittest.main()
