"""Reusable Website Interaction Layer and Adapters for JARVIS Browser Automation.
Generic websites work out-of-the-box using universal DOM discovery and heuristics.
Optional specialized adapters provide enhanced selectors, prompt box identifiers,
search URL templates, and result verification indicators for complex single-page apps.
"""

import urllib.parse
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger("Jarvis.WebsiteAdapters")


class BaseWebsiteAdapter(ABC):
    """Abstract base adapter for website-specific interaction hints."""

    name: str = "base"
    domains: List[str] = []
    search_selectors: List[str] = []
    prompt_selectors: List[str] = []
    send_button_selectors: List[str] = []
    auth_indicators: List[str] = []
    login_url_patterns: List[str] = []
    submit_method: str = "enter_key"  # enter_key, click_button, form_submit
    result_indicators: List[str] = []
    user_turn_selectors: List[str] = []
    response_indicators: List[str] = []
    error_indicators: List[str] = []
    requires_login: bool = False

    def supports_domain(self, domain_or_url: str) -> bool:
        """Checks if this adapter explicitly handles the given domain or URL."""
        if not domain_or_url:
            return False
        clean = domain_or_url.lower().strip()
        if "://" in clean:
            clean = urllib.parse.urlparse(clean).netloc
        clean = clean.replace("www.", "")
        for d in self.domains:
            d_clean = d.lower().replace("www.", "")
            if clean == d_clean or clean.endswith("." + d_clean):
                return True
        return False

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        """Optionally generates a direct search query URL if supported."""
        return None

    def get_search_selectors(self) -> List[str]:
        """Returns ordered list of DOM selectors for search inputs."""
        return list(self.search_selectors)

    def get_prompt_selectors(self) -> List[str]:
        """Returns ordered list of DOM selectors for AI prompt or messaging boxes."""
        return list(self.prompt_selectors)

    def get_send_button_selectors(self) -> List[str]:
        """Returns ordered list of DOM selectors for message dispatch / send buttons."""
        return list(self.send_button_selectors)

    def get_auth_indicators(self) -> List[str]:
        """Returns selectors or tokens indicating unauthenticated / login gate state."""
        return list(self.auth_indicators)

    def get_login_url_patterns(self) -> List[str]:
        """Returns URL substrings that indicate an unauthenticated login redirect."""
        return list(self.login_url_patterns)

    def is_auth_blocked(self, url: str, page_content: str = "") -> bool:
        """Determines if the page represents an unauthenticated gate."""
        if not self.requires_login:
            return False
        url_lower = (url or "").lower()
        for pat in self.login_url_patterns:
            if pat.lower() in url_lower:
                return True
        if page_content:
            lower_content = page_content.lower()
            for ind in self.auth_indicators:
                if ind.lower() in lower_content:
                    return True
        return False

    def get_result_indicators(self) -> List[str]:
        """Returns DOM selectors or text fragments indicating successful search/response."""
        return list(self.result_indicators)

    def get_user_turn_selectors(self) -> List[str]:
        """Returns DOM selectors for user message turns in conversation history."""
        return list(self.user_turn_selectors)

    def get_response_indicators(self) -> List[str]:
        """Returns DOM selectors indicating active streaming or model response."""
        return list(self.response_indicators)

    def get_error_indicators(self) -> List[str]:
        """Returns DOM selectors indicating error banners, alerts, or failed submissions."""
        return list(self.error_indicators)


class GenericWebsiteAdapter(BaseWebsiteAdapter):
    """Universal fallback adapter that works on any website using accessibility and DOM patterns."""

    name = "generic"
    domains = ["*"]

    # Layered universal search input selectors ordered by specificity
    search_selectors = [
        "input[type='search']",
        "input[role='searchbox']",
        "input[name='q']",
        "input[name='query']",
        "input[name='search']",
        "input[name='keyword']",
        "input[name='s']",
        "input[id*='search' i]",
        "input[class*='search' i]",
        "input[placeholder*='search' i]",
        "input[placeholder*='find' i]",
        "input[aria-label*='search' i]",
        "textarea[placeholder*='search' i]",
        "input[type='text'][name*='search' i]",
        "form[role='search'] input[type='text']",
        "form[action*='search'] input[type='text']"
    ]

    prompt_selectors = [
        "textarea[placeholder*='message' i]",
        "textarea[placeholder*='prompt' i]",
        "textarea[placeholder*='ask' i]",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "textarea"
    ]

    result_indicators = [
        "[role='main']",
        ".search-results",
        "#search-results",
        ".results",
        "#results",
        ".content",
        "article",
        "main"
    ]

    def supports_domain(self, domain_or_url: str) -> bool:
        return True  # Fallback matches all domains

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        """Generic heuristic search URL builder for sites that use standard /search?q= or ?s=."""
        if not base_url:
            return None
        parsed = urllib.parse.urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        encoded = urllib.parse.quote_plus(query)
        return f"{parsed.scheme}://{parsed.netloc}/search?q={encoded}"


class HiAnimeAdapter(BaseWebsiteAdapter):
    """Adapter for HiAnime streaming website (hianime.to / hianime.at / hianime.tv)."""

    name = "hianime"
    domains = ["hianime.to", "hianime.at", "hianime.tv", "hianime.is", "hianime.ru"]

    search_selectors = [
        "#search-suggest",
        "input[name='keyword']",
        "input.search-input",
        "input[placeholder*='Search anime' i]",
        "input[placeholder*='Search' i]"
    ]

    result_indicators = [
        ".film_list-wrap",
        ".film-detail",
        ".block_area-search",
        ".flw-item"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        domain = "hianime.to"
        if base_url:
            parsed = urllib.parse.urlparse(base_url)
            if parsed.netloc:
                domain = parsed.netloc
        return f"https://{domain}/search?keyword={encoded}"


class YouTubeAdapter(BaseWebsiteAdapter):
    """Adapter for YouTube (desktop & mobile web)."""

    name = "youtube"
    domains = ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"]

    search_selectors = [
        "input#search",
        "input[name='search_query']",
        "input[placeholder*='Search' i]",
        "input[aria-label*='Search' i]"
    ]

    result_indicators = [
        "ytd-video-renderer",
        "ytd-search",
        "#contents",
        "ytd-item-section-renderer"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://www.youtube.com/results?search_query={encoded}"


class ChatGPTAdapter(BaseWebsiteAdapter):
    """Adapter for OpenAI ChatGPT interface."""

    name = "chatgpt"
    domains = ["chatgpt.com", "chat.openai.com"]

    prompt_selectors = [
        "#prompt-textarea",
        "div#prompt-textarea",
        "textarea[placeholder*='Ask anything' i]",
        "textarea[placeholder*='Message ChatGPT' i]",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']"
    ]

    send_button_selectors = [
        "button[data-testid='send-button']",
        "button[aria-label='Send prompt']",
        "button[data-testid='composer-send-button']"
    ]

    login_url_patterns = [
        "/auth/login",
        "/auth/ext_callback",
        "/login"
    ]

    auth_indicators = [
        "[data-testid='login-button']",
        "button:has-text('Log in')",
        "button:has-text('Sign up')",
        "a[href*='/auth/login']"
    ]

    submit_method = "enter_key"
    requires_login = True

    result_indicators = [
        "[data-message-author-role='assistant']",
        ".agent-turn",
        ".markdown",
        "[data-testid='conversation-turn-3']"
    ]

    user_turn_selectors = [
        "[data-message-author-role='user']",
        "div[data-message-author-role='user']",
        "article [data-message-author-role='user']"
    ]

    response_indicators = [
        "[data-message-author-role='assistant']",
        "button[data-testid='stop-button']",
        "button[aria-label='Stop streaming']",
        ".result-streaming"
    ]

    error_indicators = [
        "div[role='alert']",
        ".text-red-500",
        "button[data-testid='retry-button']",
        ".border-red-500"
    ]


class GeminiAdapter(BaseWebsiteAdapter):
    """Adapter for Google Gemini interface."""

    name = "gemini"
    domains = ["gemini.google.com"]

    prompt_selectors = [
        "div.input-area rich-textarea div[contenteditable='true']",
        "rich-textarea div[contenteditable='true']",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true'][aria-label*='Ask Gemini' i]",
        "div[contenteditable='true'][aria-label*='prompt' i]",
        "textarea[aria-label*='prompt' i]",
        "div[contenteditable='true']"
    ]

    send_button_selectors = [
        "button[aria-label*='Send message' i]",
        "button.send-button",
        "button[data-test-id='send-button']",
        "mat-icon[fonticon='send']"
    ]

    login_url_patterns = [
        "accounts.google.com",
        "servicelogin",
        "signin/v2"
    ]

    auth_indicators = [
        "a[href*='accounts.google.com']",
        "button:has-text('Sign in')",
        "a.sign-in-button"
    ]

    submit_method = "click_button"
    requires_login = True

    result_indicators = [
        "message-content",
        "model-response",
        "response-container",
        "div.markdown"
    ]

    user_turn_selectors = [
        "user-query",
        ".query-content",
        ".user-query-container",
        "div.user-query"
    ]

    response_indicators = [
        "model-response",
        ".response-container",
        "loading-container",
        "button[aria-label*='Stop' i]"
    ]

    error_indicators = [
        ".error-message",
        "div[role='alert']",
        ".error-card"
    ]


class ClaudeAdapter(BaseWebsiteAdapter):
    """Adapter for Anthropic Claude interface."""

    name = "claude"
    domains = ["claude.ai"]

    prompt_selectors = [
        "div[contenteditable='true'].ProseMirror",
        "div[contenteditable='true'][role='textbox']",
        "fieldset div[contenteditable='true']",
        "textarea[placeholder*='How can Claude help' i]",
        "div[contenteditable='true']"
    ]

    send_button_selectors = [
        "button[aria-label*='Send Message' i]",
        "button[data-testid='send-button']",
        "button[aria-label='Send message']"
    ]

    login_url_patterns = [
        "/login",
        "/auth",
        "/signup"
    ]

    auth_indicators = [
        "button:has-text('Continue with Google')",
        "button:has-text('Continue with Email')",
        "a[href*='/login']",
        "input[type='email']"
    ]

    submit_method = "click_button"
    requires_login = True

    result_indicators = [
        "[data-is-streaming]",
        "div.font-claude-message",
        "div[data-testid='chat-message']"
    ]

    user_turn_selectors = [
        "div[data-testid='user-message']",
        ".font-user-message",
        "div[data-is-streaming='false']"
    ]

    response_indicators = [
        "div.font-claude-message",
        "[data-is-streaming='true']",
        "button[aria-label*='Stop responding' i]"
    ]

    error_indicators = [
        "[data-testid='error-banner']",
        "div[role='alert']",
        ".text-danger"
    ]


class GitHubAdapter(BaseWebsiteAdapter):
    """Adapter for GitHub."""

    name = "github"
    domains = ["github.com", "www.github.com"]

    search_selectors = [
        "input[name='q']",
        "input[data-target='qbsearch-input.input']",
        "input[placeholder*='Search or jump to' i]",
        "input[placeholder*='Search GitHub' i]",
        "button[data-target='qbsearch-input.inputButton']"
    ]

    result_indicators = [
        "[data-testid='results-list']",
        ".repo-list",
        ".search-title",
        ".Box"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://github.com/search?q={encoded}"


class RedditAdapter(BaseWebsiteAdapter):
    """Adapter for Reddit."""

    name = "reddit"
    domains = ["reddit.com", "www.reddit.com", "old.reddit.com"]

    search_selectors = [
        "input[name='q']",
        "reddit-search-bar input",
        "input[placeholder*='Search Reddit' i]",
        "input[type='search']"
    ]

    result_indicators = [
        "[data-testid='search-results']",
        "shreddit-feed",
        ".search-result-group"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://www.reddit.com/search/?q={encoded}"


class GoogleAdapter(BaseWebsiteAdapter):
    """Adapter for Google Search."""

    name = "google"
    domains = ["google.com", "www.google.com"]

    search_selectors = [
        "textarea[name='q']",
        "input[name='q']",
        "input[title='Search']"
    ]

    result_indicators = [
        "#search",
        "#rso",
        ".g",
        "#center_col"
    ]

    def build_search_url(self, query: str, base_url: Optional[str] = None) -> Optional[str]:
        encoded = urllib.parse.quote_plus(query)
        return f"https://www.google.com/search?q={encoded}"


class WebsiteAdapterRegistry:
    """Registry managing available website adapters with fallback to GenericWebsiteAdapter."""

    def __init__(self):
        self._generic_adapter = GenericWebsiteAdapter()
        self._adapters: List[BaseWebsiteAdapter] = [
            HiAnimeAdapter(),
            YouTubeAdapter(),
            ChatGPTAdapter(),
            GeminiAdapter(),
            ClaudeAdapter(),
            GitHubAdapter(),
            RedditAdapter(),
            GoogleAdapter(),
        ]

    def register_adapter(self, adapter: BaseWebsiteAdapter):
        """Adds a specialized adapter to the front of the registry."""
        self._adapters.insert(0, adapter)
        logger.info(f"Registered website adapter '{adapter.name}' for domains {adapter.domains}")

    def get_adapter(self, domain_or_url: Optional[str]) -> BaseWebsiteAdapter:
        """Returns specialized adapter if matched, otherwise GenericWebsiteAdapter."""
        if not domain_or_url:
            return self._generic_adapter

        for adapter in self._adapters:
            if adapter.supports_domain(domain_or_url):
                return adapter

        return self._generic_adapter


# Global singleton registry
website_adapter_registry = WebsiteAdapterRegistry()
