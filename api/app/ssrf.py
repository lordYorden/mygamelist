import ipaddress
import socket
from urllib.parse import urlsplit


class BlockedUrlError(ValueError):
    pass


class SsrfGuard:
    def __init__(self, allowed_domains: str | list[str]) -> None:
        if isinstance(allowed_domains, str):
            domains = allowed_domains.split(",")
        else:
            domains = allowed_domains
        self.allowed_domains = [domain.strip().lower().rstrip(".") for domain in domains if domain.strip()]

    def validate(self, url: str) -> None:
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise BlockedUrlError("URL is not valid") from exc

        if host is None:
            raise BlockedUrlError("URL must include a host")
        if parsed.username is not None or parsed.password is not None:
            raise BlockedUrlError("URLs with userinfo are not permitted")
        if parsed.scheme.lower() != "https":
            raise BlockedUrlError("Only https URLs are permitted")

        normalized_host = host.lower().rstrip(".")
        if not self._is_allowed(normalized_host):
            raise BlockedUrlError("Host is not on the webhook allowlist")

        try:
            resolved = socket.getaddrinfo(normalized_host, port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise BlockedUrlError("Host could not be resolved") from exc

        if not resolved:
            raise BlockedUrlError("Host could not be resolved")

        for result in resolved:
            address = result[4][0].split("%", 1)[0]
            ip = ipaddress.ip_address(address)
            if self._is_blocked_ip(ip):
                raise BlockedUrlError("Requests to internal addresses are not permitted")

    def _is_allowed(self, host: str) -> bool:
        for domain in self.allowed_domains:
            if host == domain or host.endswith(f".{domain}"):
                return True
        return False

    def _is_blocked_ip(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(
            [
                ip.is_loopback,
                ip.is_private,
                ip.is_link_local,
                ip.is_multicast,
                ip.is_unspecified,
                ip.is_reserved,
                getattr(ip, "is_site_local", False),
            ]
        )
