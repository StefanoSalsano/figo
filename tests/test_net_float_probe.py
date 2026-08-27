"""Unit tests for reading a gw-float gateway (network model Sections 2.3, 3.2).

The truth about public IPs is the configuration inside the gateway container,
read with 'floating-ip list --json'. These tests freeze the shape of that output
as measured on blade3 on 2026-08-27, and cover the taxonomy of what can go wrong
when asking for it.

Nothing here runs a command: the I/O half is one function, and everything it
decides is decided by pure functions that take its result.
"""

import json


# Measured on blade3, 2026-08-27, and matching the four mappings of the field
# survey: .35 -> .210 (f-patri), .36 -> .211 (g-alci), .37 -> .212 (n-cloud),
# and .43 -> 10.202.8.141 disabled.
REAL_OUTPUT = json.dumps({
    "mappings": [
        {"public": "160.80.105.35", "private": "10.202.9.210", "enabled": True,
         "mode": "whitelist",
         "allow": {"tcp": [{"pub_port": 80, "priv_port": 80},
                           {"pub_port": 443, "priv_port": 443}],
                   "icmp": ["echo-reply"]},
         "active": True},
        {"public": "160.80.105.36", "private": "10.202.9.211", "enabled": True,
         "mode": "whitelist",
         "allow": {"tcp": [{"pub_port": 80, "priv_port": 80},
                           {"pub_port": 8088, "priv_port": 8088},
                           {"pub_port": 443, "priv_port": 443}],
                   "icmp": ["echo-reply"]},
         "active": True},
        {"public": "160.80.105.37", "private": "10.202.9.212", "enabled": True,
         "mode": "whitelist",
         "allow": {"tcp": [{"pub_port": 80, "priv_port": 80},
                           {"pub_port": 443, "priv_port": 443}],
                   "icmp": ["echo-reply"]},
         "active": True},
        {"public": "160.80.105.43", "private": "10.202.8.141", "enabled": False,
         "mode": "whitelist",
         "allow": {"tcp": [{"pub_port": 22, "priv_port": 22}],
                   "icmp": ["echo-reply"]},
         "active": False},
    ]
})


# --- The figo scope is not the incus command line ---------------------------

def test_scope_becomes_an_incus_command_line(figo):
    """figo writes remote:project.instance; incus wants the project as an option.

    Writing the figo form straight into an incus command yields 'Instance not
    found', which reads like a missing container rather than a wrong invocation.
    That happened once; this test is why it should not happen twice.
    """
    assert figo.incus_exec_argv("blade3:default.gw-float", ["floating-ip", "list"]) == [
        "incus", "exec", "blade3:gw-float", "--project", "default", "--",
        "floating-ip", "list",
    ]


def test_scope_without_a_project_defaults_to_default(figo):
    assert figo.incus_exec_argv("blade3:gw-float", ["x"])[:5] == [
        "incus", "exec", "blade3:gw-float", "--project", "default",
    ]


def test_scope_in_another_project(figo):
    assert figo.incus_exec_argv("jeeg:figo-stefano.ollama", ["x"])[:5] == [
        "incus", "exec", "jeeg:ollama", "--project", "figo-stefano",
    ]


# --- Parsing what the gateway returns ---------------------------------------

def test_parses_the_measured_output(figo):
    mappings, warnings = figo.parse_floating_ip_list(REAL_OUTPUT)
    assert warnings == []
    assert [m["public"] for m in mappings] == [
        "160.80.105.35", "160.80.105.36", "160.80.105.37", "160.80.105.43",
    ]
    assert [m["private"] for m in mappings][0] == "10.202.9.210"


def test_enabled_and_active_are_kept_apart(figo):
    """The gateway distinguishes them on purpose; merging them loses the point."""
    mappings, _ = figo.parse_floating_ip_list(REAL_OUTPUT)
    assert [(m["enabled"], m["active"]) for m in mappings] == [
        (True, True), (True, True), (True, True), (False, False),
    ]


def test_drift_between_enabled_and_active_survives_parsing(figo):
    """A mapping asked for but not on the interface, and one the other way round.

    On the real gateway the two agree on every mapping, so the measured output
    cannot prove that the parser keeps them apart: a parser that read 'active'
    from 'enabled' would pass every test built on it. This case is constructed
    on purpose, which is also how C2's drift detector will have to be tested.
    """
    mappings, warnings = figo.parse_floating_ip_list(json.dumps({"mappings": [
        {"public": "160.80.105.44", "private": "10.202.9.220",
         "enabled": True, "active": False, "allow": {}},
        {"public": "160.80.105.45", "private": "10.202.9.221",
         "enabled": False, "active": True, "allow": {}},
    ]}))
    assert warnings == []
    assert [(m["enabled"], m["active"]) for m in mappings] == [(True, False), (False, True)]


def test_ports_are_read_as_public_private_pairs(figo):
    mappings, _ = figo.parse_floating_ip_list(REAL_OUTPUT)
    assert mappings[1]["tcp"] == [(80, 80), (8088, 8088), (443, 443)]
    assert mappings[3]["tcp"] == [(22, 22)]
    assert mappings[0]["icmp"] == ["echo-reply"]
    assert mappings[0]["udp"] == []


def test_invalid_json_is_reported_not_swallowed(figo):
    mappings, warnings = figo.parse_floating_ip_list("not json at all")
    assert mappings == []
    assert warnings and "valid JSON" in warnings[0]


def test_output_without_mappings_key(figo):
    mappings, warnings = figo.parse_floating_ip_list('{"something": []}')
    assert mappings == []
    assert warnings and "mappings" in warnings[0]


def test_empty_gateway_is_a_valid_answer(figo):
    mappings, warnings = figo.parse_floating_ip_list('{"mappings": []}')
    assert mappings == []
    assert warnings == []


def test_a_mapping_without_a_public_address_is_skipped_with_a_warning(figo):
    mappings, warnings = figo.parse_floating_ip_list(
        '{"mappings": [{"private": "10.202.9.210", "enabled": true}]}'
    )
    assert mappings == []
    assert warnings


# --- The taxonomy of asking ------------------------------------------------

def test_successful_probe(figo):
    probe = figo.classify_gateway_probe("blade3:default.gw-float", 0, REAL_OUTPUT, "")
    assert probe.outcome == figo.GATEWAY_PROBE_OK
    assert len(probe.mappings) == 4
    assert "4 mapping" in probe.detail


def test_missing_gateway_instance_points_at_the_configuration(figo):
    probe = figo.classify_gateway_probe(
        "blade3:default.gw-float", 1, "",
        'Error: Failed to fetch instance "gw-float" in project "default": Instance not found'
    )
    assert probe.outcome == figo.GATEWAY_PROBE_NOT_FOUND
    assert "config.yaml" in probe.detail


def test_unreachable_remote(figo):
    probe = figo.classify_gateway_probe(
        "blade3:default.gw-float", 1, "", "Error: Failed to connect to blade3: no route to host"
    )
    assert probe.outcome == figo.GATEWAY_PROBE_UNREACHABLE


def test_other_failures_keep_stderr(figo):
    probe = figo.classify_gateway_probe(
        "blade3:default.gw-float", 127, "", "floating-ip: command not found"
    )
    assert probe.outcome == figo.GATEWAY_PROBE_ERROR
    assert "command not found" in probe.detail


def test_success_with_unreadable_output_is_an_error_not_an_empty_gateway(figo):
    """Exit 0 and garbage is a failure: an empty gateway says '{"mappings": []}'."""
    probe = figo.classify_gateway_probe("blade3:default.gw-float", 0, "<html>", "")
    assert probe.outcome == figo.GATEWAY_PROBE_ERROR
