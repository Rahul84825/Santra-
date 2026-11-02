import unittest
from unittest.mock import MagicMock, patch
from core.intent_engine import IntentEngine
from core.os.browser_manager import BrowserManager
from core.platform.windows_platform import WindowsPlatform
from modules.system.executor import CommandExecutor
from core.os.browser_intent import BrowserIntentParser, BrowserIntent, BrowserActionType

class TestHiAnimeBraveNavigation(unittest.TestCase):
    def setUp(self):
        self.intent_engine = IntentEngine()
        self.parser = BrowserIntentParser()

    def test_all_seven_exact_phrases(self):
        watching_phrases = [
            "Open watched anime",
            "Open my watched anime",
            "Open anime watchlist",
            "Open my anime list"
        ]
        home_phrases = [
            "Open anime site",
            "Open HiAnime",
            "Open HiAnime homepage"
        ]

        for phrase in watching_phrases:
            res = self.intent_engine.parse(phrase)
            self.assertEqual(res.get("intent"), "browser_action", f"Failed intent for '{phrase}'")
            self.assertEqual(res.get("target_browser"), "brave", f"Failed browser for '{phrase}'")
            self.assertEqual(res.get("url"), "https://hianime.at/user/watching", f"Failed url for '{phrase}'")
            meta = res.get("metadata", {})
            self.assertEqual(meta.get("strict_browser"), "brave", f"Failed strict_browser for '{phrase}'")

        for phrase in home_phrases:
            res = self.intent_engine.parse(phrase)
            self.assertEqual(res.get("intent"), "browser_action", f"Failed intent for '{phrase}'")
            self.assertEqual(res.get("target_browser"), "brave", f"Failed browser for '{phrase}'")
            self.assertEqual(res.get("url"), "https://hianime.at/", f"Failed url for '{phrase}'")
            meta = res.get("metadata", {})
            self.assertEqual(meta.get("strict_browser"), "brave", f"Failed strict_browser for '{phrase}'")

    def test_unrelated_and_isolated_words_do_not_navigate(self):
        # Isolated generic words must NOT trigger navigation
        isolated_words = ["anime", "watching", "site"]
        for word in isolated_words:
            intent = self.parser.parse(word)
            self.assertNotEqual(intent.action_type, BrowserActionType.OPEN_URL, f"Isolated '{word}' triggered OPEN_URL")
            node = self.intent_engine.parse(word)
            self.assertNotEqual(node.get("action_type"), "open_url", f"Isolated '{word}' triggered open_url")
            self.assertNotEqual(node.get("url"), "https://hianime.at/", f"Isolated '{word}' opened home")
            self.assertNotEqual(node.get("url"), "https://hianime.at/user/watching", f"Isolated '{word}' opened watching")

        # Ambiguous phrase "open anime" must NOT navigate to HiAnime
        ambig_intent = self.parser.parse("open anime")
        self.assertNotEqual(ambig_intent.action_type, BrowserActionType.OPEN_URL, "'open anime' should not navigate")
        ambig_node = self.intent_engine.parse("open anime")
        self.assertNotEqual(ambig_node.get("url"), "https://hianime.at/", "'open anime' should not open homepage")
        self.assertNotEqual(ambig_node.get("url"), "https://hianime.at/user/watching", "'open anime' should not open watching")

    def test_strict_browser_enforcement_in_browser_manager(self):
        bm = BrowserManager()
        with patch.object(bm, 'is_browser_available', return_value=False):
            resolved, err = bm.resolve_target_browser("brave", strict_browser=True)
            self.assertIsNone(resolved, "Should not resolve to any fallback when brave is missing and strict_browser=True")
            self.assertIsNotNone(err)
            self.assertEqual(err, "I couldn't find Brave Browser.")

    def test_windows_platform_strict_brave_rejection_without_chrome_fallback(self):
        wp = WindowsPlatform()
        with patch.object(wp, '_probe_browser_executable', return_value=None), \
             patch.object(wp, 'open_url') as mock_open_url:
            success = wp.open_browser("brave", "https://hianime.at/user/watching")
            self.assertFalse(success, "Must return False when Brave is not found")
            mock_open_url.assert_not_called()

    def test_exact_response_phrasing_success(self):
        from core.os.browser_automation import BrowserAutomationEngine

        mock_bm = MagicMock()
        mock_bm.open_browser.return_value = {"success": True, "browser": "brave"}

        engine = BrowserAutomationEngine()
        engine.browser_mgr = mock_bm
        engine.session_mgr = MagicMock()
        engine.session_mgr.is_website_already_open.return_value = None

        # 1. Watching page response
        engine._verify_navigation = MagicMock(return_value=(True, "https://hianime.at/user/watching"))
        watching_intent = BrowserIntent(
            action_type=BrowserActionType.OPEN_URL,
            target_browser="brave",
            url="https://hianime.at/user/watching",
            site_name="HiAnime Watching",
            metadata={"strict_browser": "brave", "service": "hianime_watching"}
        )
        res_watch = engine.execute_intent(watching_intent)
        self.assertEqual(res_watch["message"], "Opening your watched anime in Brave.")

        # 2. Homepage response
        engine._verify_navigation = MagicMock(return_value=(True, "https://hianime.at/"))
        home_intent = BrowserIntent(
            action_type=BrowserActionType.OPEN_URL,
            target_browser="brave",
            url="https://hianime.at/",
            site_name="HiAnime",
            metadata={"strict_browser": "brave", "service": "hianime_home"}
        )
        res_home = engine.execute_intent(home_intent)
        self.assertEqual(res_home["message"], "Opening HiAnime in Brave.")

    def test_exact_response_phrasing_missing_brave(self):
        from core.os.browser_automation import BrowserAutomationEngine

        mock_bm = MagicMock()
        mock_bm.open_browser.return_value = {"success": False, "message": "I couldn't find Brave Browser."}

        engine = BrowserAutomationEngine()
        engine.browser_mgr = mock_bm
        engine.session_mgr = MagicMock()

        watching_intent = BrowserIntent(
            action_type=BrowserActionType.OPEN_URL,
            target_browser="brave",
            url="https://hianime.at/user/watching",
            site_name="HiAnime Watching",
            metadata={"strict_browser": "brave", "service": "hianime_watching"}
        )
        res = engine.execute_intent(watching_intent)
        self.assertFalse(res["success"])
        self.assertEqual(res["message"], "I couldn't find Brave Browser.")

    def test_exact_response_phrasing_navigation_failure_to_confirm(self):
        from core.os.browser_automation import BrowserAutomationEngine

        mock_bm = MagicMock()
        mock_bm.open_browser.return_value = {"success": True, "browser": "brave"}

        engine = BrowserAutomationEngine()
        engine.browser_mgr = mock_bm
        engine.session_mgr = MagicMock()
        engine.session_mgr.is_website_already_open.return_value = None
        # Navigation could not be verified
        engine._verify_navigation = MagicMock(return_value=(False, None))

        watching_intent = BrowserIntent(
            action_type=BrowserActionType.OPEN_URL,
            target_browser="brave",
            url="https://hianime.at/user/watching",
            site_name="HiAnime Watching",
            metadata={"strict_browser": "brave", "service": "hianime_watching"}
        )
        res = engine.execute_intent(watching_intent)
        self.assertEqual(res["message"], "Brave opened, but I couldn't confirm the page loaded.")

    def test_executor_handles_open_website_intent(self):
        mock_bm = MagicMock()
        mock_bm.open_browser.return_value = {"success": True, "browser": "brave"}
        
        executor = CommandExecutor()
        executor.browser_mgr = mock_bm
        
        intent_node = {
            "intent": "open_website",
            "target": "HiAnime Watching",
            "url": "https://hianime.at/user/watching",
            "browser": "brave",
            "strict_browser": True
        }
        
        res = executor.execute(intent_node)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("message"), "Opening your watched anime in Brave.")
        mock_bm.open_browser.assert_called_with(
            browser_name="brave",
            url="https://hianime.at/user/watching",
            strict_browser=True
        )

if __name__ == "__main__":
    unittest.main()
