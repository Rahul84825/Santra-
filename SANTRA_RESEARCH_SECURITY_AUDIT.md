# SANTRA Research Engine — Security Hardening & SSRF Defense Audit

## 1. Overview
The SANTRA Universal Research Engine extracts content from arbitrary URLs discovered during search operations. Without strict defensive controls, this capability poses severe security risks, including Server-Side Request Forgery (SSRF), DNS rebinding to local network devices, cloud metadata extraction, and indirect prompt injection.

---

## 2. Implemented Defense In Depth

### A. SSRF & Private Network Perimeter Guard
- **Private IP Range Blocking**: Every IP destination is validated against `PRIVATE_IP_RANGES`:
  - IPv4 Loopback: `127.0.0.0/8`
  - IPv4 Private Class A, B, C: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
  - IPv4 Link-Local & Cloud Metadata: `169.254.0.0/16` (protects `169.254.169.254`)
  - IPv6 Loopback: `::1/128`
  - IPv6 Unique Local: `fc00::/7`
  - IPv6 Link-Local: `fe80::/10`
  - IPv4-Mapped IPv6: `::ffff:0:0/96`

### B. DNS Rebinding Mitigation
- Attack Vector: A malicious domain (`attacker.com`) has a public DNS record that resolves to `127.0.0.1` or `169.254.169.254`. Checking the URL hostname string alone would bypass simple IP regexes.
- Defense: `research_security._verify_dns_resolution(hostname)` performs forward DNS resolution via `socket.getaddrinfo(hostname, None)` before any network connection is attempted. If **any** resolved IP address falls within a private or link-local range, the connection is instantly rejected with `(False, "Hostname resolves to private/internal IP (DNS Rebinding/SSRF guard)")`.

### C. Safe Redirect Handler (`SafeRedirectHandler`)
- Attack Vector: An attacker serves a public URL that returns `HTTP 302 Found` with `Location: http://169.254.169.254/latest/meta-data/`. Standard HTTP clients follow redirects automatically.
- Defense: Subclassed `urllib.request.HTTPRedirectHandler`:
  1. Limits redirect hops to a maximum of 3 (`MAX_REDIRECTS = 3`).
  2. Intercepts each redirect hop and re-runs `research_security.is_safe_url(newurl)`. If unsafe, returns `None` immediately, terminating the connection.

### D. Indirect Prompt Injection Neutralization
- Untrusted web snippets and extracted paragraphs are sanitized using `research_security.sanitize_untrusted_text()`:
  - HTML tags and `<script>`/`<iframe>` elements stripped.
  - Known injection delimiters (`[SYSTEM]`, `[INSTRUCTION]`, `<|im_start|>`, `ignore previous instructions`) are escaped or removed.
  - Source snippets are packaged in the Nemotron prompt under strict contractual isolation headers (`--- VERIFIED SOURCES & EVIDENCE ---`) with explicit instructions forbidding the LLM from executing commands found within web text.

---

## 3. Adversarial Security Test Suite
- `test_security_dns_rebinding_prevention`: Verified malicious domain resolving to `127.0.0.1` blocked (PASS).
- `test_security_link_local_and_mapped_ipv6`: Verified `fe80::` and `::ffff:127.0.0.1` blocked (PASS).
- `test_safe_redirect_handler_blocks_ssrf_hop`: Verified 302 redirect to `169.254.169.254` aborted (PASS).
- `test_safe_redirect_handler_max_hops`: Verified infinite redirect loops capped at 3 hops (PASS).

