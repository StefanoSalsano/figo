"""Unit tests for the upstream policy (network model Section 7.2).

What the university network permits cannot be measured from inside the testbed
(7.5), so figo never refuses on it: it warns, and the warning has to carry
enough provenance to be judged -- who said it, when, and whether anybody ever
tested it.

Two failure modes are checked here more than the happy path, because both are
silent: an entry that cannot be judged (no date, no source, no confidence) and
an entry stated more broadly than anybody verified. The second is not
hypothetical -- the model itself once generalised a comment about one address
to a whole /24 that was later shown to allow the port.
"""

import datetime

import pytest


TODAY = datetime.date(2026, 8, 29)


def policy(**overrides):
    entry = {
        "scope": {"public_ip": "160.80.105.43"},
        "protocol": "tcp",
        "ports": [22],
        "effect": "blocked",
        "confidence": "declared",
        "source": "CDC - recorded in gw-float config.yaml",
        "date": "2026-08-26",
    }
    entry.update(overrides)
    return {"upstream_policy": [entry]}


# --- Reading the file -------------------------------------------------------

def test_a_complete_entry_is_read(figo):
    entries, warnings = figo.parse_upstream_policy(policy())
    assert warnings == []
    assert entries[0]["public_ip"] == "160.80.105.43"
    assert entries[0]["ports"] == [22]
    assert entries[0]["confidence"] == "declared"


def test_no_policy_at_all_is_not_a_problem(figo):
    assert figo.parse_upstream_policy({}) == ([], [])
    assert figo.parse_upstream_policy(None) == ([], [])


def test_an_undated_assertion_is_dropped(figo):
    """This knowledge decays; undated, it would look authoritative forever."""
    entries, warnings = figo.parse_upstream_policy(policy(date=None))
    assert entries == []
    assert warnings and "decays" in warnings[0]


def test_an_unsourced_assertion_is_dropped(figo):
    """A constraint nobody is named for cannot be questioned, only obeyed."""
    entries, warnings = figo.parse_upstream_policy(policy(source=""))
    assert entries == []
    assert warnings and "source" in warnings[0]


def test_an_assertion_without_confidence_is_dropped(figo):
    entries, warnings = figo.parse_upstream_policy(policy(confidence=None))
    assert entries == []
    assert warnings and "verified" in warnings[0]


def test_an_assertion_about_every_port_of_an_address_is_dropped(figo):
    """Broader than anything anyone measured: exactly the false-warning trap."""
    entries, warnings = figo.parse_upstream_policy(policy(ports=None))
    assert entries == []
    assert warnings and "broader" in warnings[0]


def test_an_assertion_with_no_scope_is_dropped(figo):
    entries, warnings = figo.parse_upstream_policy(policy(scope={}))
    assert entries == []
    assert warnings and "every mapping" in warnings[0]


def test_a_malformed_address_is_reported_not_guessed(figo):
    entries, warnings = figo.parse_upstream_policy(policy(scope={"public_ip": "160.80"}))
    assert entries == []
    assert warnings


def test_one_bad_entry_does_not_lose_the_good_ones(figo):
    config = {"upstream_policy": [
        policy()["upstream_policy"][0],
        {"scope": {"public_ip": "160.80.105.44"}, "protocol": "tcp", "ports": [80],
         "effect": "blocked", "confidence": "declared", "source": "x"},
    ]}
    entries, warnings = figo.parse_upstream_policy(config)
    assert len(entries) == 1
    assert len(warnings) == 1


# --- What an assertion covers, and what it does not -------------------------

def test_the_address_it_was_recorded_for(figo):
    entries, _ = figo.parse_upstream_policy(policy())
    assert figo.upstream_constraints(entries, "160.80.105.43", "tcp", [22])


def test_and_not_its_neighbour(figo):
    """The one that matters: .87 answered on 22 from outside on 2026-08-26."""
    entries, _ = figo.parse_upstream_policy(policy())
    assert figo.upstream_constraints(entries, "160.80.105.87", "tcp", [22]) == []


def test_and_not_another_port_of_the_same_address(figo):
    entries, _ = figo.parse_upstream_policy(policy())
    assert figo.upstream_constraints(entries, "160.80.105.43", "tcp", [80]) == []


def test_a_range_covers_the_addresses_inside_it(figo):
    entries, _ = figo.parse_upstream_policy(
        policy(scope={"public_range": "160.80.105.0/24"}))
    assert figo.upstream_constraints(entries, "160.80.105.87", "tcp", [22])
    assert figo.upstream_constraints(entries, "160.80.223.5", "tcp", [22]) == []


def test_only_the_ports_that_actually_match_are_reported(figo):
    entries, _ = figo.parse_upstream_policy(policy(ports=[22, 3389]))
    matches = figo.upstream_constraints(entries, "160.80.105.43", "tcp", [22, 80, 3389])
    assert matches[0][1] == [22, 3389]


def test_icmp_needs_no_ports_to_match(figo):
    entries, _ = figo.parse_upstream_policy(
        policy(scope={"public_range": "160.80.105.0/24"}, protocol="icmp",
               ports=None, direction="inbound"))
    matches = figo.upstream_constraints(entries, "160.80.105.36", "icmp")
    assert matches and matches[0][1] == []


def test_a_protocol_says_nothing_about_another(figo):
    entries, _ = figo.parse_upstream_policy(policy())
    assert figo.upstream_constraints(entries, "160.80.105.43", "udp", [22]) == []


# --- The warning has to be judgeable ----------------------------------------

def test_the_warning_names_the_source_the_date_and_the_age(figo):
    entries, _ = figo.parse_upstream_policy(policy())
    message = figo.format_upstream_warning(entries[0], [22], today=TODAY)
    assert "tcp/22" in message
    assert "160.80.105.43" in message
    assert "CDC" in message
    assert "2026-08-26" in message
    assert "3 days ago" in message


def test_declared_says_nobody_tested_it(figo):
    entries, _ = figo.parse_upstream_policy(policy())
    assert "never tested" in figo.format_upstream_warning(entries[0], [22], today=TODAY)


def test_verified_says_something_different(figo):
    """The three levels change what figo is entitled to say, not just a label."""
    entries, _ = figo.parse_upstream_policy(policy(confidence="verified"))
    message = figo.format_upstream_warning(entries[0], [22], today=TODAY)
    assert "measured from outside" in message
    assert "never tested" not in message


def test_a_note_is_carried_into_the_warning(figo):
    entries, _ = figo.parse_upstream_policy(policy(note="reason .43 is disabled"))
    assert "reason .43 is disabled" in figo.format_upstream_warning(
        entries[0], [22], today=TODAY)
