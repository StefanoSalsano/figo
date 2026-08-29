"""Unit tests for 'figo net float diagnose' (network model Section 7.4).

The order of the checks is the feature, not the checks themselves: from the
cheapest and most frequent cause to the rarest, so that the wrong default
route -- the most common fault in this deployment -- is seen before anyone
opens a firewall rule. These tests pin that order and the verdicts that make
a row a problem.

Nothing here runs a command: everything the diagnosis decides is decided by a
pure function that receives the facts.
"""

import pytest


GATEWAY = {"scope": "blade3:default.gw-float", "address": "10.202.9.254"}


def mapping(enabled=True, active=True, tcp=((443, 443), (8088, 8088)), drift=None):
    return {"public": "160.80.105.36", "private": "10.202.9.211",
            "enabled": enabled, "active": active, "mode": "whitelist",
            "tcp": list(tcp), "udp": [], "icmp": [], "icmp_all": False,
            "label": None, "note": None, "drift": drift}


def checks(rows):
    return [row[0] for row in rows]


# --- Reading what listens inside the instance -------------------------------

def test_ss_output_becomes_addresses_and_ports(figo):
    out = ("LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*\n"
           "LISTEN 0 511  [::]:443 [::]:*\n"
           "LISTEN 0 4096 127.0.0.1:8088 0.0.0.0:*\n")
    assert figo.parse_listening_ports(out) == [
        ("0.0.0.0", 22), ("::", 443), ("127.0.0.1", 8088)]


def test_a_port_bound_to_loopback_is_not_served(figo):
    """The failure that looks healthy from inside: the process is up, the port
    answers locally, and every connection through the floating IP is refused."""
    listeners = [("127.0.0.1", 8088)]
    assert figo.listener_verdict(listeners, 8088) == figo.LISTENER_LOOPBACK


def test_a_port_nobody_listens_on(figo):
    assert figo.listener_verdict([("0.0.0.0", 22)], 8088) == figo.LISTENER_CLOSED


def test_a_port_served_on_every_interface(figo):
    assert figo.listener_verdict([("0.0.0.0", 8088)], 8088) == figo.LISTENER_OPEN
    assert figo.listener_verdict([("::", 8088)], 8088) == figo.LISTENER_OPEN
    assert figo.listener_verdict([("10.202.9.211", 8088)], 8088) == figo.LISTENER_OPEN


def test_loopback_and_a_real_address_together_are_served(figo):
    assert figo.listener_verdict(
        [("127.0.0.1", 8088), ("10.202.9.211", 8088)], 8088) == figo.LISTENER_OPEN


# --- The order of the checks ------------------------------------------------

def test_the_order_is_by_cost_and_frequency(figo):
    rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(drift={"missing": 0, "extra": 0,
                                                      "consistent": True}),
        figo.FLOAT_INVARIANT_OK, "fine", [("0.0.0.0", 443), ("0.0.0.0", 8088)], []
    )
    assert checks(rows) == [
        "gateway", "mapping", "invariant", "rules", "listener", "listener", "upstream"]
    assert problems == []


def test_a_gateway_that_does_not_answer_stops_the_diagnosis(figo):
    """Everything after it would be guesswork, and a long list of unknowns
    hides the one thing that is known."""
    rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_NOT_FOUND, None, None, None, None, []
    )
    assert checks(rows) == ["gateway"]
    assert len(problems) == 1


def test_no_gateway_at_all_is_the_first_answer(figo):
    rows, problems = figo.diagnose_rows(None, figo.GATEWAY_PROBE_ERROR, None,
                                        None, None, None, [])
    assert checks(rows) == ["gateway"]
    assert problems


def test_an_instance_with_no_mapping_stops_there(figo):
    rows, _ = figo.diagnose_rows(GATEWAY, figo.GATEWAY_PROBE_OK, None,
                                 None, None, None, [])
    assert checks(rows) == ["gateway", "mapping"]


# --- What counts as a problem -----------------------------------------------

def test_the_wrong_default_route_is_a_problem(figo):
    rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(), figo.FLOAT_INVARIANT_VIOLATED,
        "routes via 10.202.9.129", [("0.0.0.0", 443), ("0.0.0.0", 8088)], []
    )
    assert [row[0] for row in problems] == ["invariant"]


def test_an_invariant_that_could_not_be_read_is_not_a_problem(figo):
    """Unknown is not wrong: reporting it as a fault would send the reader to
    fix something that may be perfectly fine."""
    rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(), figo.FLOAT_INVARIANT_UNKNOWN,
        "the instance is stopped", None, []
    )
    assert "invariant" not in [row[0] for row in problems]


def test_rule_drift_is_a_problem_and_unknown_drift_is_not(figo):
    _rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK,
        mapping(drift={"missing": 2, "extra": 0, "consistent": False}),
        figo.FLOAT_INVARIANT_OK, "fine", [("0.0.0.0", 443), ("0.0.0.0", 8088)], []
    )
    assert [row[0] for row in problems] == ["rules"]

    _rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(drift=None),
        figo.FLOAT_INVARIANT_OK, "fine", [("0.0.0.0", 443), ("0.0.0.0", 8088)], []
    )
    assert problems == []


def test_the_port_nobody_listens_on_is_named(figo):
    """The example of Section 7.4: everything right, and 8088 silent."""
    _rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(), figo.FLOAT_INVARIANT_OK, "fine",
        [("0.0.0.0", 443)], []
    )
    assert len(problems) == 1
    assert "8088" in problems[0][1]


def test_listeners_that_could_not_be_read_are_not_reported_as_closed(figo):
    rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(), figo.FLOAT_INVARIANT_OK, "fine",
        None, []
    )
    assert problems == []
    assert [row[2] for row in rows if row[0] == "listener"] == ["not read", "not read"]


def test_a_disabled_mapping_is_a_problem_but_does_not_stop_the_rest(figo):
    rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(enabled=False, active=False),
        figo.FLOAT_INVARIANT_NOT_CHECKED, "off", [("0.0.0.0", 443)], []
    )
    assert "mapping" in [row[0] for row in problems]
    assert "listener" in checks(rows)


# --- What figo was told, and what it cannot test ----------------------------

def test_a_known_constraint_is_reported_without_being_a_problem(figo):
    """It is somebody else's word, and it may be stale: it belongs in the
    report, not in the count of faults figo established."""
    entry = {"public_ip": "160.80.105.36", "public_range": None, "protocol": "tcp",
             "ports": [443], "effect": "blocked", "confidence": "declared",
             "source": "CDC", "date": "2026-08-26", "note": None, "direction": None}
    rows, problems = figo.diagnose_rows(
        GATEWAY, figo.GATEWAY_PROBE_OK, mapping(), figo.FLOAT_INVARIANT_OK, "fine",
        [("0.0.0.0", 443), ("0.0.0.0", 8088)], [(entry, [443])]
    )
    upstream = [row for row in rows if row[0] == "upstream"][0]
    assert "declared" in upstream[2] and "2026-08-26" in upstream[2]
    assert problems == []


def test_the_commands_figo_cannot_run_itself(figo):
    commands = figo.external_check_commands("160.80.105.36", [443, 8088])
    assert commands[0].startswith("curl") and "https://160.80.105.36/" in commands[0]
    assert commands[1] == "nc -vz -w 5 160.80.105.36 8088"
