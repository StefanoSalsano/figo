"""Unit tests for the two answers to 'what address does this instance have'.

figo has always shown one number: the one it wrote into 'user.network-config'.
That is a request, and it becomes a fact only if something inside the instance
applies it. Measured on 2026-08-29: a container created from an image without
cloud-init ignored the configuration and took a DHCP address, while every figo
view kept showing the address figo had asked for.

The state that answers the second question was already in the output of
'incus list -f json' that figo runs anyway. Nobody was reading it.
"""

import pytest


def instance(status="Running", configured="10.202.9.217/25", live=("10.202.9.217",)):
    entry = {
        "name": "float-test",
        "status": status,
        "config": {},
    }
    if configured:
        entry["config"]["user.network-config"] = (
            "version: 2\nethernets:\n    eth0:\n        dhcp4: false\n"
            f"        addresses:\n            - {configured}\n"
        )
    if live is not None:
        entry["state"] = {"network": {
            "lo": {"addresses": [{"family": "inet", "address": "127.0.0.1",
                                  "scope": "local"}]},
            "eth0": {"addresses": [{"family": "inet", "address": address,
                                    "scope": "global"} for address in live]},
        }}
    return entry


def test_the_live_addresses_come_from_the_state(figo):
    assert figo.live_ip_device_pairs(instance()) == [("10.202.9.217", "eth0")]


def test_the_scope_is_what_separates_a_real_address_from_the_rest(figo):
    """Shape copied from 'incus list -f json' on blade3, 2026-08-29: loopback
    comes back as scope 'local' and IPv6 link-local as 'link'. Filtering by
    interface name instead would say less and miss a local-scope address on a
    real interface."""
    entry = {"name": "g-alci", "status": "Running", "config": {}, "state": {"network": {
        "lo": {"addresses": [
            {"family": "inet", "address": "127.0.0.1", "scope": "local"},
            {"family": "inet6", "address": "::1", "scope": "local"}]},
        "eth0": {"addresses": [
            {"family": "inet", "address": "10.202.9.211", "scope": "global"},
            {"family": "inet6", "address": "fe80::216:3eff:fe1c:1", "scope": "link"}]},
    }}}
    assert figo.live_ip_device_pairs(entry) == [("10.202.9.211", "eth0")]


def test_a_stopped_instance_measures_nothing(figo):
    """Nothing, not 'no addresses': the question could not be asked."""
    assert figo.live_ip_device_pairs(instance(status="Stopped", live=None)) == []


def test_the_case_that_started_this(figo):
    """Created with 10.202.9.217 from an image with no cloud-init, running on
    the DHCP address 10.202.9.144. Every figo view said .217."""
    entry = instance(configured="10.202.9.217/25", live=("10.202.9.144",))
    configured = figo.get_ip_device_pairs(entry)
    live = figo.live_ip_device_pairs(entry)
    assert configured == [("10.202.9.217/25", "eth0")]
    assert live == [("10.202.9.144", "eth0")]
    assert figo.address_divergence(configured, live) == ["10.202.9.217/25"]


def test_the_ordinary_case_is_silent(figo):
    entry = instance()
    assert figo.address_divergence(
        figo.get_ip_device_pairs(entry), figo.live_ip_device_pairs(entry)) == []


def test_a_stopped_instance_is_not_a_divergence(figo):
    """With nothing measured there is nothing to disagree with, and reporting
    every stopped instance as wrong would bury the one that is."""
    entry = instance(status="Stopped", live=None)
    assert figo.address_divergence(figo.get_ip_device_pairs(entry), []) == []


def test_an_extra_live_address_is_not_a_divergence(figo):
    """The instance holding more than it was asked for is a different question:
    what this checks is that what was asked for is actually there."""
    entry = instance(live=("10.202.9.217", "10.202.9.250"))
    assert figo.address_divergence(
        figo.get_ip_device_pairs(entry), figo.live_ip_device_pairs(entry)) == []


def test_a_global_ipv6_address_is_not_one_of_these_addresses(figo):
    """Constructed, not measured: this testbed has no IPv6 today. But the whole
    model is IPv4 -- subnets, gateways, floating IPs -- and a global IPv6 would
    pass the scope filter and then be compared against IPv4 configuration, where
    it can only ever look like a divergence.
    """
    entry = {"name": "x", "status": "Running", "config": {}, "state": {"network": {
        "eth0": {"addresses": [
            {"family": "inet", "address": "10.202.9.211", "scope": "global"},
            {"family": "inet6", "address": "2001:db8::1", "scope": "global"}]},
    }}}
    assert figo.live_ip_device_pairs(entry) == [("10.202.9.211", "eth0")]
