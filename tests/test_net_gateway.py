"""Unit tests for gateway resolution (network model Section 3.4).

A floating IP is served by the gw-float of the instance's own subnet. The
resolution is a pure function with one answer, and it is total: the four
outcomes that are not 'served' exist because the remedy differs, and a message
that does not name the remedy leaves the administrator with nothing to do.

The subnets are derived from the remotes figo already knows; configuration adds
only what cannot be derived — the host of a subnet and whether it has a public
VLAN. These tests use dictionaries: no file, no remote, no network.
"""

import pytest


REMOTE_MAP = {
    "local":    {"gw": "10.202.8.129",   "prefix_len": 25, "base_ip": "10.202.8.150"},
    "jeeg":     {"gw": "10.202.8.129",   "prefix_len": 25, "base_ip": "10.202.8.150"},
    "blade3":   {"gw": "10.202.9.129",   "prefix_len": 25, "base_ip": "10.202.9.150"},
    "eln_cloud": {"gw": "10.202.10.129", "prefix_len": 25, "base_ip": "10.202.10.150"},
}

CONFIG = {
    "network": {
        "float_gateways": {
            "10.202.9.128/25": {"scope": "blade3:default.gw-float", "address": "10.202.9.254"},
        },
        "subnets": {
            "10.202.9.128/25": {"host": "blade3", "public_vlan": True},
            "10.202.8.128/25": {"host": "goldrake", "public_vlan": True},
            "10.202.10.128/25": {"host": "eln_cloud", "public_vlan": False},
        },
    }
}


@pytest.fixture
def network(figo):
    parsed, warnings = figo.parse_network_config(CONFIG)
    assert warnings == []
    return figo.network_subnets(REMOTE_MAP, parsed), parsed["gateways"]


# --- Deriving subnets from the remotes --------------------------------------

def test_subnet_of_remote(figo):
    assert figo.subnet_of_remote(REMOTE_MAP["blade3"]) == "10.202.9.128/25"


def test_subnet_of_remote_needs_both_facts(figo):
    assert figo.subnet_of_remote({"gw": "10.202.9.129"}) is None
    assert figo.subnet_of_remote({"prefix_len": 25}) is None
    assert figo.subnet_of_remote({}) is None
    assert figo.subnet_of_remote(None) is None


def test_subnet_of_remote_rejects_nonsense(figo):
    assert figo.subnet_of_remote({"gw": "not-an-address", "prefix_len": 25}) is None


def test_remotes_sharing_a_subnet_are_kept_together(figo):
    """jeeg and the controller are VMs of goldrake: one subnet, three remotes."""
    subnets = figo.network_subnets(REMOTE_MAP, {"subnets": {}})
    assert subnets["10.202.8.128/25"]["remotes"] == ["jeeg", "local"]
    assert subnets["10.202.9.128/25"]["remotes"] == ["blade3"]


def test_configuration_adds_facts_to_a_derived_subnet(figo):
    parsed, _ = figo.parse_network_config(CONFIG)
    subnets = figo.network_subnets(REMOTE_MAP, parsed)
    assert subnets["10.202.8.128/25"]["host"] == "goldrake"
    assert subnets["10.202.8.128/25"]["public_vlan"] is True
    assert subnets["10.202.8.128/25"]["remotes"] == ["jeeg", "local"]


# --- The three outcomes the completion criterion asks for -------------------

def test_served_subnet_names_the_gateway(figo, network):
    subnets, gateways = network
    resolution = figo.resolve_float_gateway("10.202.9.210", subnets, gateways)
    assert resolution.outcome == figo.FLOAT_GATEWAY_SERVED
    assert resolution.subnet == "10.202.9.128/25"
    assert resolution.gateway["scope"] == "blade3:default.gw-float"
    assert "blade3:default.gw-float" in resolution.detail
    assert "10.202.9.254" in resolution.detail


def test_no_gateway_but_host_qualifies_points_at_deploy(figo, network):
    """Every instance of jeeg lands here: goldrake's subnet, no gateway yet."""
    subnets, gateways = network
    resolution = figo.resolve_float_gateway("10.202.8.153", subnets, gateways)
    assert resolution.outcome == figo.FLOAT_GATEWAY_DEPLOYABLE
    assert resolution.host == "goldrake"
    assert "net gateway deploy" in resolution.detail


def test_host_without_public_vlan_says_the_remedy_is_outside_figo(figo, network):
    subnets, gateways = network
    resolution = figo.resolve_float_gateway("10.202.10.160", subnets, gateways)
    assert resolution.outcome == figo.FLOAT_GATEWAY_NO_PUBLIC_VLAN
    assert "public VLAN" in resolution.detail
    assert "outside figo" in resolution.detail


def test_the_three_messages_differ(figo, network):
    """The point of three outcomes is three remedies, so the texts must differ."""
    subnets, gateways = network
    messages = {
        figo.resolve_float_gateway(address, subnets, gateways).detail
        for address in ("10.202.9.210", "10.202.8.153", "10.202.10.160")
    }
    assert len(messages) == 3


# --- Totality: the two outcomes that keep the function total ----------------

def test_unknown_subnet(figo, network):
    subnets, gateways = network
    resolution = figo.resolve_float_gateway("192.168.7.5", subnets, gateways)
    assert resolution.outcome == figo.FLOAT_GATEWAY_UNKNOWN_SUBNET
    assert resolution.subnet is None


def test_malformed_address_is_not_mistaken_for_an_unknown_subnet_message(figo, network):
    subnets, gateways = network
    resolution = figo.resolve_float_gateway("10.202.9", subnets, gateways)
    assert resolution.outcome == figo.FLOAT_GATEWAY_UNKNOWN_SUBNET
    assert "not an IP address" in resolution.detail


def test_public_vlan_not_recorded_says_to_check_rather_than_asserting(figo):
    """Unknown is not the same as false: one asks, the other closes the door."""
    subnets = figo.network_subnets(REMOTE_MAP, {"subnets": {}})
    resolution = figo.resolve_float_gateway("10.202.8.153", subnets, {})
    assert resolution.outcome == figo.FLOAT_GATEWAY_UNKNOWN_VLAN
    assert "public_vlan" in resolution.detail


def test_address_with_a_prefix_is_accepted(figo, network):
    subnets, gateways = network
    assert figo.resolve_float_gateway("10.202.9.210/25", subnets, gateways).outcome == (
        figo.FLOAT_GATEWAY_SERVED
    )


def test_longest_prefix_wins_when_subnets_overlap(figo):
    """br-202-8 carries 10.202.8.0/24 while the instance range is the /25."""
    subnets = {
        "10.202.8.0/24": {"host": "goldrake", "public_vlan": True, "remotes": []},
        "10.202.8.128/25": {"host": "goldrake", "public_vlan": True, "remotes": ["jeeg"]},
    }
    gateways = {"10.202.8.128/25": {"scope": "goldrake:default.gw-float", "address": "10.202.8.254"}}
    resolution = figo.resolve_float_gateway("10.202.8.153", subnets, gateways)
    assert resolution.subnet == "10.202.8.128/25"
    assert resolution.outcome == figo.FLOAT_GATEWAY_SERVED


# --- Reading the configuration ----------------------------------------------

def test_absent_configuration_yields_an_empty_network(figo):
    parsed, warnings = figo.parse_network_config({})
    assert parsed == {"gateways": {}, "subnets": {}}
    assert warnings == []


def test_gateway_without_scope_is_dropped_with_a_warning(figo):
    parsed, warnings = figo.parse_network_config(
        {"network": {"float_gateways": {"10.202.9.128/25": {"address": "10.202.9.254"}}}}
    )
    assert parsed["gateways"] == {}
    assert any("scope" in warning for warning in warnings)


def test_a_subnet_that_is_not_a_subnet_is_dropped_with_a_warning(figo):
    parsed, warnings = figo.parse_network_config(
        {"network": {"subnets": {"blade3": {"host": "blade3"}}}}
    )
    assert parsed["subnets"] == {}
    assert any("is not a subnet" in warning for warning in warnings)


def test_public_vlan_must_be_boolean(figo):
    parsed, warnings = figo.parse_network_config(
        {"network": {"subnets": {"10.202.9.128/25": {"public_vlan": "yes"}}}}
    )
    assert parsed["subnets"]["10.202.9.128/25"]["public_vlan"] is None
    assert any("true or false" in warning for warning in warnings)


def test_host_address_is_normalised_to_its_subnet(figo):
    """'10.202.9.129/25' and '10.202.9.128/25' name the same subnet."""
    parsed, warnings = figo.parse_network_config(
        {"network": {"subnets": {"10.202.9.129/25": {"host": "blade3", "public_vlan": True}}}}
    )
    assert "10.202.9.128/25" in parsed["subnets"]
    assert warnings == []


def test_a_gateway_on_an_undeclared_subnet_still_resolves(figo):
    """Declaring the gateway is enough; the subnet entry is implied."""
    parsed, warnings = figo.parse_network_config(
        {"network": {"float_gateways": {"10.202.9.128/25": {"scope": "blade3:default.gw-float"}}}}
    )
    assert warnings == []
    subnets = figo.network_subnets(REMOTE_MAP, parsed)
    resolution = figo.resolve_float_gateway("10.202.9.210", subnets, parsed["gateways"])
    assert resolution.outcome == figo.FLOAT_GATEWAY_SERVED
