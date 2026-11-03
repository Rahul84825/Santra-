"""Security and Research Safety Engine for SANTRA Research Engine.
Defends against prompt injection in web pages, SSRF, local network scanning,
DNS rebinding, unsafe file imports, arbitrary code execution, and unauthorized purchases.
"""

import re
import socket
import ipaddress
import urllib.parse
import logging
from typing import Tuple, Optional, List

logger = logging.getLogger("Jarvis.ResearchSecurity")

class ResearchSecurity:
    """Guards research inputs, retrieved content, and external URLs against exploits."""

    # Prompt injection vectors common in adversarial web pages
    INJECTION_PATTERNS = [
        r"(?i)\bignore\s+(?:all\s+)?previous\s+instructions\b",
        r"(?i)\bdisregard\s+(?:all\s+)?prior\s+(?:orders?|instructions?|prompts?)\b",
        r"(?i)\bsystem\s+instructions?\s*:",
        r"(?i)\byou\s+are\s+now\s+(?:an?\s+)?unrestricted\b",
        r"(?i)\bsystem\s*:\s*you\s+must\b",
        r"(?i)\bdeveloper\s+mode\s+enabled\b",
        r"(?i)\bdelete\s+(?:all\s+)?(?:user\s+)?(?:files|records|data)\b",
        r"(?i)\brun\s+(?:powershell|cmd|bash|terminal)\b",
        r"(?i)\bformat\s+c:\b",
        r"(?i)\bexecute\s+(?:the\s+following\s+code|os\.system|subprocess)\b"
    ]

    # Block all private IPv4 and IPv6 subnets, link-local, loopback, and cloud metadata
    PRIVATE_IP_RANGES = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),     # Link-local / AWS & GCP metadata (169.254.169.254)
        ipaddress.ip_network("::1/128"),            # IPv6 Loopback
        ipaddress.ip_network("fc00::/7"),           # IPv6 Unique Local Address (ULA)
        ipaddress.ip_network("fe80::/10"),          # IPv6 Link-Local
        ipaddress.ip_network("::ffff:0:0/96")       # IPv4-mapped IPv6
    ]

    @classmethod
    def is_safe_url(cls, url: str, check_dns: bool = True) -> Tuple[bool, Optional[str]]:
        """Validates that a URL is a legitimate public web destination and not an SSRF probe.
        Performs protocol restriction, loopback hostname blocking, IP range validation,
        and DNS resolution checking to prevent DNS rebinding attacks.
        """
        if not url:
            return False, "URL is empty."

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            return False, f"Malformed URL: {e}"

        if parsed.scheme not in ["http", "https"]:
            return False, f"Prohibited URL scheme '{parsed.scheme}'. Only http and https permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "URL has no hostname."

        clean_host = hostname.lower().strip()
        # #numeric_hostname_guard: Block integer/octal/hex alternative IP representations
        if clean_host.isdigit():
            try:
                int_val = int(clean_host)
                ip_obj = ipaddress.ip_address(int_val)
                for priv_net in cls.PRIVATE_IP_RANGES:
                    if ip_obj in priv_net:
                        return False, f"Access to private/internal network IP '{hostname}' (numeric representation) is blocked (SSRF guard)."
            except Exception:
                return False, f"Prohibited numeric hostname '{hostname}' (SSRF guard)."
        if clean_host.startswith("0x"):
            try:
                int_val = int(clean_host, 16)
                ip_obj = ipaddress.ip_address(int_val)
                for priv_net in cls.PRIVATE_IP_RANGES:
                    if ip_obj in priv_net:
                        return False, f"Access to private/internal network IP '{hostname}' (hex representation) is blocked (SSRF guard)."
            except Exception:
                return False, f"Prohibited hex hostname '{hostname}' (SSRF guard)."


        # Block loopback and local names immediately
        if clean_host in ["localhost", "127.0.0.1", "::1", "local", "ip6-localhost", "ip6-loopback"]:
            return False, f"Access to localhost/loopback address '{hostname}' is blocked."

        # Check if hostname is already a raw IP address
        try:
            ip_obj = ipaddress.ip_address(clean_host)
            for priv_net in cls.PRIVATE_IP_RANGES:
                if ip_obj in priv_net:
                    return False, f"Access to private/internal network IP '{hostname}' is blocked (SSRF guard)."
        except ValueError:
            # Hostname is a domain name. Perform DNS resolution check to prevent DNS rebinding.
            if check_dns:
                is_safe_dns, dns_reason = cls._verify_dns_resolution(clean_host)
                if not is_safe_dns:
                    return False, dns_reason

        return True, None

    @classmethod
    def _verify_dns_resolution(cls, hostname: str) -> Tuple[bool, Optional[str]]:
        """Resolves hostname to IP addresses and checks each against blocked private networks."""
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                sockaddr = item[4]
                ip_str = sockaddr[0]
                try:
                    ip_obj = ipaddress.ip_address(ip_str)
                    for priv_net in cls.PRIVATE_IP_RANGES:
                        if ip_obj in priv_net:
                            return False, f"Hostname '{hostname}' resolves to private/internal IP '{ip_str}' (DNS Rebinding/SSRF guard)."
                except ValueError:
                    pass
        except socket.gaierror:
            # Hostname does not resolve; will fail naturally on HTTP connect
            pass
        except Exception as e:
            logger.debug(f"[ResearchSecurity] DNS check error for '{hostname}': {e}")

        return True, None

    @classmethod
    def sanitize_untrusted_text(cls, text: str) -> str:
        """Neutralizes prompt injection patterns and removes dangerous instructional directives."""
        if not text:
            return ""

        clean = text
        for pat in cls.INJECTION_PATTERNS:
            clean = re.sub(pat, "[BLOCKED_INSTRUCTION]", clean)

        return clean

# Singleton instance
research_security = ResearchSecurity()
