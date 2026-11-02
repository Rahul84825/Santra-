# tests/test_multistep_orchestration_100.py
"""Comprehensive suite of 100 Multi-Step Orchestration test cases for SANTRA.

Validates:
- Compound command splitting via CommandNormalizer
- IntentEngine structured multi-step decomposition (intent: 'multi_step_task')
- Sub-step action and target fidelity
- Browser, application, typing, and system action chaining
"""

import unittest
from core.intent_engine import IntentEngine

class TestMultiStepOrchestration100(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ie = IntentEngine()

    def test_multi_app_chaining_25_cases(self):
        """Test 25 sequential multi-application opening and closing requests."""
        cases = [
            ("Open Chrome and open VS Code", 2),
            ("Open Notepad and open Calculator", 2),
            ("Open Spotify and open Chrome", 2),
            ("Open VS Code and open Notepad", 2),
            ("Open Terminal and open Calculator", 2),
            ("Open Downloads and open Chrome", 2),
            ("Close Chrome and open Brave", 2),
            ("Close Notepad and open Wordpad", 2),
            ("Open GitHub and open YouTube", 2),
            ("Open Brave and open VS Code", 2),
            ("Open Spotify and increase volume", 2),
            ("Close Calculator and volume up", 2),
            ("Open Chrome, open VS Code and open Notepad", 3),
            ("Open Brave, open YouTube and open Spotify", 3),
            ("Close Chrome and close Notepad", 2),
            ("Open Terminal and open VS Code", 2),
            ("Open Notepad and open Downloads", 2),
            ("Open Chrome and open Spotify", 2),
            ("Open Calculator and open Notepad", 2),
            ("Open VS Code and open Terminal", 2),
            ("Close Spotify and open YouTube", 2),
            ("Open Brave and open GitHub", 2),
            ("Open Chrome, open Spotify and volume up", 3),
            ("Open Downloads and open VS Code", 2),
            ("Open YouTube and open Chrome", 2),
        ]
        for cmd, expected_count in cases:
            with self.subTest(cmd=cmd):
                res = self.ie.parse(cmd)
                self.assertEqual(res.get("intent"), "multi_step_task", f"Failed for '{cmd}'")
                self.assertEqual(len(res.get("steps", [])), expected_count)

    def test_app_and_search_chaining_25_cases(self):
        """Test 25 requests combining app launch or browser with search actions."""
        cases = [
            "Open Chrome and search for machine learning",
            "Open Chrome and search for Python tutorials",
            "Open Brave and search for HiAnime",
            "Open Chrome and search for GitHub repositories",
            "Open Brave and search for anime streaming",
            "Open Chrome and search for FastAPI documentation",
            "Open Brave and search for Rust programming",
            "Open Chrome and search for deep learning research",
            "Open Brave and search for latest tech news",
            "Open Chrome and search for docker containers",
            "Open Brave and search for kubernetes architecture",
            "Open Chrome and search for quantum computing",
            "Open Brave and search for linux kernel source",
            "Open Chrome and search for sqlite documentation",
            "Open Brave and search for web scraping python",
            "Open Chrome and search for pyqt6 tutorial",
            "Open Brave and search for async python programming",
            "Open Chrome and search for artificial intelligence papers",
            "Open Brave and search for brave browser extensions",
            "Open Chrome and search for numpy tutorials",
            "Open Brave and search for ctranslate2 cuda",
            "Open Chrome and search for whisper models",
            "Open Brave and search for git commands cheat sheet",
            "Open Chrome and search for vscode shortcuts",
            "Open Brave and search for python unittest documentation"
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                res = self.ie.parse(cmd)
                self.assertEqual(res.get("intent"), "multi_step_task", f"Failed for '{cmd}'")
                self.assertGreaterEqual(len(res.get("steps", [])), 2)
                intents = [s.get("intent") for s in res.get("steps", [])]
                self.assertIn("web_search", intents)

    def test_system_and_media_chaining_25_cases(self):
        """Test 25 requests chaining system operations with volume, screenshots, or lock."""
        cases = [
            ("Take screenshot and open downloads", 2),
            ("Lock computer and mute volume", 2),
            ("Take screenshot and open chrome", 2),
            ("Volume up and take screenshot", 2),
            ("Volume down and take screenshot", 2),
            ("Mute volume and lock computer", 2),
            ("Unmute volume and open spotify", 2),
            ("Take screenshot and open vs code", 2),
            ("Volume up and open spotify", 2),
            ("Volume down and open notepad", 2),
            ("Take screenshot and open paint", 2),
            ("Lock computer and volume down", 2),
            ("Mute volume and take screenshot", 2),
            ("Unmute volume and volume up", 2),
            ("Take screenshot and open calculator", 2),
            ("Volume up and open youtube", 2),
            ("Volume down and mute volume", 2),
            ("Lock computer and close chrome", 2),
            ("Take screenshot and open terminal", 2),
            ("Volume up and open brave", 2),
            ("Take screenshot and open pictures", 2),
            ("Lock computer and mute", 2),
            ("Volume down and open chrome", 2),
            ("Take screenshot and open folder", 2),
            ("Lock computer and turn off monitor", 2)
        ]
        for cmd, expected_count in cases:
            with self.subTest(cmd=cmd):
                res = self.ie.parse(cmd)
                self.assertEqual(res.get("intent"), "multi_step_task", f"Failed for '{cmd}'")
                self.assertEqual(len(res.get("steps", [])), expected_count)

    def test_mixed_browser_and_task_chaining_25_cases(self):
        """Test 25 complex workflows chaining browser, applications, and productivity tools."""
        cases = [
            "Open Chrome and open GitHub",
            "Open Brave and open HiAnime",
            "Open VS Code and open Terminal",
            "Open Chrome and open YouTube",
            "Open Brave and open Reddit",
            "Open VS Code and open GitHub",
            "Open Chrome and open Downloads",
            "Open Brave and open Twitter",
            "Open Notepad and open Calculator",
            "Open VS Code and open Chrome",
            "Open Brave and open YouTube",
            "Open Spotify and open Chrome",
            "Open Chrome and open Gmail",
            "Open Brave and open Stack Overflow",
            "Open VS Code and open Notepad",
            "Open Chrome and open LinkedIn",
            "Open Brave and open Wikipedia",
            "Open Terminal and open Chrome",
            "Open VS Code and open Brave",
            "Open Chrome and open Google Drive",
            "Open Brave and open Discord",
            "Open Spotify and open YouTube",
            "Open VS Code and open Spotify",
            "Open Chrome and open Netflix",
            "Open Brave and open Twitch"
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                res = self.ie.parse(cmd)
                self.assertEqual(res.get("intent"), "multi_step_task", f"Failed for '{cmd}'")
                self.assertGreaterEqual(len(res.get("steps", [])), 2)

if __name__ == "__main__":
    unittest.main()

