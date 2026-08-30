"""Unit tests for `figo vpn audit` (network model Section 4.2).

The VPN user state lives in two registries that can disagree -- the .conf files
figo writes, and the peers the access router enforces -- and nothing has ever
compared them. The first real comparison, on 30/8/2026, found eleven peers with
no .conf and six addresses claimed twice, so these tests are written against
shapes taken from that measurement rather than invented ones.

Three of them exist because the audit can be wrong in a way that looks right:
the interface must be the one the clients actually talk to (the testbed router
carries two WireGuard interfaces, and comparing against the wrong one reports a
clean or a catastrophic state with equal confidence), values in RouterOS terse
output can contain spaces, and a disabled peer is neither present nor absent.
"""

import pytest


SERVER_KEY = "c2VydmVyLXB1YmxpYy1rZXktZm9yLXRlc3Rz"


def conf(address="10.202.1.19", prefixlen=24, server_key=SERVER_KEY):
    return f"""[Interface]
PrivateKey = cHJpdmF0ZS1rZXktZm9yLXRlc3Rz
Address = {address}/{prefixlen}

[Peer]
PublicKey = {server_key}
AllowedIPs = 10.192.0.0/10
Endpoint = vpn.example.org:13232
"""


def user(address="10.202.1.19", public_key="KEY-A", prefixlen=24):
    return {"address": address, "prefixlen": prefixlen, "public_key": public_key,
            "server_public_key": SERVER_KEY}


def peer(public_key="KEY-A", address="10.202.1.19/32", comment="a-amici",
         flags="", interface="wireguard2"):
    return {"index": "22", "flags": flags, "comment": comment,
            "interface": interface, "public-key": public_key,
            "allowed-address": address}


def kinds(findings):
    return [item["kind"] for item in findings]


# --- Reading the client configuration ---------------------------------------

def test_conf_yields_address_and_server_key(figo):
    read = figo.parse_wireguard_client_conf(conf())
    assert read == {"address": "10.202.1.19", "prefixlen": 24,
                    "server_public_key": SERVER_KEY}


def test_the_client_private_key_is_never_mistaken_for_the_server_key(figo):
    """PrivateKey sits in [Interface]; only [Peer] carries a PublicKey."""
    read = figo.parse_wireguard_client_conf(conf())
    assert read["server_public_key"] == SERVER_KEY


def test_a_conf_without_a_peer_section_reports_no_server(figo):
    read = figo.parse_wireguard_client_conf(
        "[Interface]\nPrivateKey = x\nAddress = 10.202.1.19/24\n")
    assert read["server_public_key"] is None
    assert read["address"] == "10.202.1.19"


# --- Reading the router -----------------------------------------------------

def test_terse_values_may_contain_spaces(figo):
    line = (" 6   comment=Paolo GPUNet interface=wireguard2 "
            "public-key=srJlv0Sd= allowed-address=10.202.1.5/32,192.168.33.5/32")
    row, = figo.parse_mikrotik_terse(line)
    assert row["comment"] == "Paolo GPUNet"
    assert row["interface"] == "wireguard2"
    assert row["allowed-address"] == "10.202.1.5/32,192.168.33.5/32"


def test_the_disabled_flag_is_kept(figo):
    row, = figo.parse_mikrotik_terse(" 9 X comment=l-montefo interface=wireguard2")
    assert row["index"] == "9"
    assert row["flags"] == "X"


def test_a_row_without_flags_has_none(figo):
    row, = figo.parse_mikrotik_terse(" 5   comment=Stefano interface=wireguard2")
    assert row["flags"] == ""


def test_lines_with_no_fields_are_skipped(figo):
    text = "Flags: X - disabled, D - dynamic\n\n 0   name=wireguard1\n"
    rows = figo.parse_mikrotik_terse(text)
    assert len(rows) == 1
    assert rows[0]["name"] == "wireguard1"


def test_empty_values_survive(figo):
    row, = figo.parse_mikrotik_terse(" 1   endpoint-address= endpoint-port=0")
    assert row["endpoint-address"] == ""
    assert row["endpoint-port"] == "0"


# --- Choosing the interface by measurement ----------------------------------

def interfaces():
    return [{"name": "wireguard1", "public-key": "MANAGEMENT-KEY"},
            {"name": "wireguard2", "public-key": SERVER_KEY}]


def test_the_interface_is_the_one_holding_the_clients_server_key(figo):
    assert figo.wireguard_interface_for_server_key(interfaces(), SERVER_KEY) == "wireguard2"


def test_no_interface_matches_is_not_a_guess(figo):
    """A router that does not carry this server is a finding, not a default."""
    assert figo.wireguard_interface_for_server_key(interfaces(), "OTHER") is None


def test_two_interfaces_with_the_same_key_refuse_to_resolve(figo):
    same = [{"name": "wireguard1", "public-key": SERVER_KEY},
            {"name": "wireguard2", "public-key": SERVER_KEY}]
    assert figo.wireguard_interface_for_server_key(same, SERVER_KEY) is None


def test_no_server_key_at_all_refuses_to_resolve(figo):
    assert figo.wireguard_interface_for_server_key(interfaces(), None) is None


# --- The four questions of Section 4.2 --------------------------------------

def test_a_matching_pair_produces_nothing(figo):
    assert figo.vpn_audit_findings({"a-amici": user()}, [peer()]) == []


def test_a_conf_with_no_peer_is_reported(figo):
    found = figo.vpn_audit_findings({"a-amici": user()}, [])
    assert kinds(found) == ["no-peer"]


def test_a_peer_with_no_conf_is_reported(figo):
    found = figo.vpn_audit_findings({}, [peer(comment="l-montefo")])
    assert kinds(found) == ["orphan-peer-enabled"]


def test_a_disabled_orphan_is_less_urgent_than_a_live_one(figo):
    found = figo.vpn_audit_findings({}, [
        peer(public_key="KEY-B", comment="live", address="10.202.1.19/32"),
        peer(public_key="KEY-C", comment="dormant", address="10.202.1.20/32", flags="X")])
    assert kinds(found) == ["orphan-peer-enabled", "orphan-peer-disabled"]


def test_the_join_is_on_the_key_not_on_the_comment(figo):
    """Same name, different key: the peer someone rebuilt by hand."""
    found = figo.vpn_audit_findings({"a-amici": user(public_key="KEY-A")},
                                    [peer(public_key="KEY-REBUILT")])
    assert kinds(found) == ["no-peer", "orphan-peer-enabled"]


def test_a_peer_labelled_differently_is_still_matched(figo):
    found = figo.vpn_audit_findings({"a-amici": user()}, [peer(comment="Amici")])
    assert kinds(found) == ["comment-mismatch"]


def test_an_address_the_router_does_not_enforce_is_a_mismatch(figo):
    found = figo.vpn_audit_findings({"a-amici": user(address="10.202.1.19")},
                                    [peer(address="10.202.1.99/32")])
    assert kinds(found) == ["address-mismatch"]


def test_an_allowed_address_wider_than_a_slash_32(figo):
    found = figo.vpn_audit_findings({"a-amici": user()}, [peer(address="10.202.1.19/24")])
    assert kinds(found) == ["allowed-address-wide"]


def test_a_second_allowed_address_outside_the_client_subnet(figo):
    found = figo.vpn_audit_findings(
        {"a-amici": user()}, [peer(address="10.202.1.19/32,192.168.33.5/32")])
    assert kinds(found) == ["allowed-address-extra"]


def test_a_second_address_inside_the_client_subnet_is_not_reported_twice(figo):
    """It is already visible as a duplicate if anyone else holds it."""
    found = figo.vpn_audit_findings(
        {"a-amici": user()}, [peer(address="10.202.1.19/32,10.202.1.99/32")])
    assert kinds(found) == []


def test_two_peers_on_one_address(figo):
    found = figo.vpn_audit_findings(
        {"a-amici": user()},
        [peer(), peer(public_key="KEY-OLD", comment="a-gauti", flags="X")])
    assert kinds(found) == ["duplicate-address", "orphan-peer-disabled"]
    assert found[0]["subject"] == "10.202.1.19"
    assert "a-gauti (disabled)" in found[0]["detail"]


def test_a_dormant_duplicate_is_still_a_duplicate(figo):
    """The peer is one click from being enabled; the conflict is not dormant."""
    found = figo.vpn_audit_findings(
        {}, [peer(public_key="K1", comment="one", flags="X"),
             peer(public_key="K2", comment="two", flags="X")])
    assert "duplicate-address" in kinds(found)


def test_several_flags_still_mean_disabled(figo):
    """RouterOS prints one letter per flag; X can arrive with company.

    Constructed, not measured: the peers seen on 30/8 carried X alone. The
    shape is what the parser must survive, and comparing the flag string
    instead of searching it passed every other test in this file.
    """
    found = figo.vpn_audit_findings({"a-amici": user()}, [peer(flags="XD")])
    assert kinds(found) == ["peer-disabled"]


def test_no_subnet_no_claim_about_being_outside_it(figo):
    """Disagreeing client files: figo does not know what the range is."""
    users = {"a-amici": user(address="10.202.1.19", prefixlen=24),
             "other": user(address="10.203.1.19", public_key="KEY-O", prefixlen=24)}
    peers = [peer(address="10.202.1.19/32,192.168.33.5/32"),
             peer(public_key="KEY-O", comment="other", address="10.203.1.19/32")]
    assert "allowed-address-extra" not in kinds(figo.vpn_audit_findings(users, peers))


def test_a_user_whose_peer_is_disabled_cannot_connect(figo):
    found = figo.vpn_audit_findings({"a-amici": user()}, [peer(flags="X")])
    assert kinds(found) == ["peer-disabled"]


# --- What the allocator cannot see ------------------------------------------

def test_a_router_only_address_above_the_base_is_named(figo):
    found = figo.vpn_audit_findings(
        {"a-amici": user(address="10.202.1.19")},
        [peer(), peer(public_key="KEY-Z", comment="m-arian",
                      address="10.202.1.28/32", flags="X")],
        base_address="10.202.1.15")
    assert "allocator-blind" in kinds(found)
    assert "10.202.1.28" in found[-1]["detail"]


def test_an_address_below_the_base_is_not_a_future_collision(figo):
    """The allocator starts at the base, so it will never hand this one out."""
    found = figo.vpn_audit_findings(
        {"a-amici": user()},
        [peer(), peer(public_key="KEY-G", comment="Stefano GPUNet",
                      address="10.202.1.2/32")],
        base_address="10.202.1.15")
    assert "allocator-blind" not in kinds(found)


def test_without_a_base_no_claim_is_made_about_the_future(figo):
    found = figo.vpn_audit_findings(
        {"a-amici": user()},
        [peer(), peer(public_key="KEY-Z", address="10.202.1.28/32", comment="m-arian")])
    assert "allocator-blind" in kinds(found)


# --- The subnet comes from the files, not from a constant -------------------

def test_the_subnet_is_read_from_the_client_configurations(figo):
    subnet = figo.vpn_client_subnet({"a": user(address="10.202.1.19", prefixlen=24)})
    assert str(subnet) == "10.202.1.0/24"


def test_disagreeing_configurations_yield_no_subnet(figo):
    subnet = figo.vpn_client_subnet({
        "a": user(address="10.202.1.19", prefixlen=24),
        "b": user(address="10.203.1.19", prefixlen=24)})
    assert subnet is None


# --- Ordering ---------------------------------------------------------------

def test_the_most_consequential_finding_comes_first(figo):
    found = figo.vpn_audit_findings(
        {"a-amici": user(), "d-palmi": user(address="10.202.1.22", public_key="KEY-D")},
        [peer(comment="Amici"),
         peer(public_key="KEY-OLD", comment="a-gauti", flags="X")])
    assert kinds(found)[0] == "duplicate-address"


def test_every_kind_produced_is_in_the_declared_order(figo):
    found = figo.vpn_audit_findings(
        {"a-amici": user(), "missing": user(address="10.202.1.40", public_key="KEY-M")},
        [peer(comment="Amici", address="10.202.1.19/24,192.168.33.5/32"),
         peer(public_key="KEY-OLD", comment="a-gauti", flags="X")],
        base_address="10.202.1.15")
    assert set(kinds(found)) <= set(figo.VPN_AUDIT_ORDER)


# --- The server key, and what happens when the files disagree ---------------

def test_the_server_key_comes_from_the_client_files(figo):
    assert figo.vpn_server_key({"a": user(), "b": user(public_key="KEY-B")}) == SERVER_KEY


def test_clients_configured_for_two_servers_cannot_be_audited_together(figo):
    mixed = {"a": user(), "b": dict(user(public_key="KEY-B"), server_public_key="OTHER")}
    assert figo.vpn_server_key(mixed) is None


def test_no_server_key_anywhere(figo):
    assert figo.vpn_server_key({"a": dict(user(), server_public_key=None)}) is None


# --- A user figo cannot match at all ----------------------------------------

def test_a_user_without_a_public_key_is_not_declared_peerless(figo):
    """No .wgpub means no join key: saying 'no peer' would be a verdict."""
    found = figo.vpn_audit_findings({"a-amici": dict(user(), public_key=None)}, [peer()])
    assert kinds(found) == ["no-public-key", "orphan-peer-enabled"]


# --- Rendering --------------------------------------------------------------

def test_the_first_line_says_what_was_compared(figo):
    lines = figo.format_vpn_audit([], interface="wireguard2", user_count=12, peer_count=23)
    assert lines[0] == "interface wireguard2: 12 user records, 23 peers"
    assert lines[1] == "the two registries agree."


def test_one_record_is_singular(figo):
    lines = figo.format_vpn_audit([], interface="wg", user_count=1, peer_count=1)
    assert lines[0] == "interface wg: 1 user record, 1 peer"


def test_the_counts_line_follows_the_declared_order(figo):
    findings = [{"kind": "orphan-peer-enabled", "subject": "x", "detail": "d"},
                {"kind": "duplicate-address", "subject": "10.202.1.19", "detail": "d"}]
    lines = figo.format_vpn_audit(findings, interface="wg", user_count=2, peer_count=2)
    assert lines[1] == "1 duplicate-address, 1 orphan-peer-enabled"


def test_every_finding_is_rendered(figo):
    findings = [{"kind": "no-peer", "subject": "a-amici", "detail": "allocated, never pushed"}]
    lines = figo.format_vpn_audit(findings, interface="wg", user_count=1, peer_count=0)
    assert any("a-amici" in line and "never pushed" in line for line in lines)
