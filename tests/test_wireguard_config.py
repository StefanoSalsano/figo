"""Golden test for the WireGuard client configuration figo hands to a user.

The file is an interface with a human and with a VPN server: if the [Peer]
section changes silently, the user gets something that looks configured and
cannot connect, and nothing in figo notices. Freezing the text is the cheapest
detector available.

This is also what replaces, without touching the real MikroTik, the check that
removing the dead `PublicKey` constant left the generated file unchanged: the
peer key rendered here comes from WG_SERVER_PUB_KEY, and a test says so.
"""

import textwrap


def expected(text):
    return textwrap.dedent(text).lstrip("\n")


def test_client_config_is_frozen(figo):
    """The whole file, rendered from explicit facts."""
    rendered = figo.format_wireguard_client_config(
        private_key="cHJpdmF0ZS1rZXktZm9yLXRlc3RzLW9ubHk9",
        ip_address="10.202.1.42",
        server_public_key="c2VydmVyLXB1YmxpYy1rZXktZm9yLXRlc3Rz",
        allowed_ips="10.192.0.0/10",
        endpoint="vpn.example.org:13232",
    )
    assert rendered == expected("""
        [Interface]
        PrivateKey = cHJpdmF0ZS1rZXktZm9yLXRlc3RzLW9ubHk9
        Address = 10.202.1.42/24

        [Peer]
        PublicKey = c2VydmVyLXB1YmxpYy1rZXktZm9yLXRlc3Rz
        AllowedIPs = 10.192.0.0/10
        Endpoint = vpn.example.org:13232
    """)


def test_address_carries_the_prefix(figo):
    """The /24 is added by the template: a client written without it gets no route."""
    rendered = figo.format_wireguard_client_config("k", "10.202.1.42")
    assert "Address = 10.202.1.42/24" in rendered


def test_peer_key_defaults_to_the_single_server_key(figo):
    """The peer key comes from WG_SERVER_PUB_KEY, and from nowhere else.

    This is the regression guard for the removed duplicate: whoever rotates the
    server key edits that one constant and this test proves the generated file
    follows. A second constant holding the same value would not.
    """
    rendered = figo.format_wireguard_client_config("k", "10.202.1.42")
    assert f"PublicKey = {figo.WG_SERVER_PUB_KEY}" in rendered
    assert not hasattr(figo, "PublicKey"), (
        "a module-level PublicKey is back: one key, one constant"
    )


def test_peer_defaults_come_from_the_module_constants(figo):
    rendered = figo.format_wireguard_client_config("k", "10.202.1.42")
    assert f"AllowedIPs = {figo.AllowedIPs}" in rendered
    assert f"Endpoint = {figo.Endpoint}" in rendered


def test_file_ends_with_a_newline(figo):
    """wg-quick tolerates a missing final newline; editors and diffs do not."""
    assert figo.format_wireguard_client_config("k", "10.202.1.42").endswith("\n")
