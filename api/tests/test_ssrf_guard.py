import socket

import pytest

from app.ssrf import BlockedUrlError, SsrfGuard


def fake_addrinfo(*addresses: str) -> list[tuple]:
    return [
        (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 0, "", (address, 443))
        for address in addresses
    ]


def test_allows_exact_allowlisted_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: fake_addrinfo("8.8.8.8"))

    SsrfGuard(["hooks.slack.com"]).validate("https://hooks.slack.com/services/test")


def test_allows_suffix_match_for_allowlisted_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: fake_addrinfo("8.8.8.8"))

    SsrfGuard(["discord.com"]).validate("https://webhooks.discord.com/api/test")


@pytest.mark.parametrize(
    ("allowed_domains", "url"),
    [
        (["hooks.slack.com"], "http://hooks.slack.com/services/test"),
        (["hooks.slack.com"], "https://attacker.example.com/collect"),
        (["127.0.0.1"], "https://127.0.0.1/"),
        (["127.1"], "https://127.1/"),
        (["::1"], "https://[::1]/"),
        (["169.254.169.254"], "https://169.254.169.254/latest/meta-data/"),
        (["hooks.slack.com"], "file:///etc/passwd"),
        (["evil.example"], "https://hooks.slack.com@evil.example/"),
    ],
)
def test_blocks_unsafe_urls(allowed_domains: list[str], url: str) -> None:
    with pytest.raises(BlockedUrlError):
        SsrfGuard(allowed_domains).validate(url)


def test_checks_every_resolved_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: fake_addrinfo("8.8.8.8", "127.0.0.1"))

    with pytest.raises(BlockedUrlError, match="internal addresses"):
        SsrfGuard(["hooks.slack.com"]).validate("https://hooks.slack.com/services/test")
