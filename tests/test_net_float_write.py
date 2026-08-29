"""Unit tests for the write verbs of 'figo net float' (network model 3.6, 7.3).

The rule these tests exist to hold in place is the asymmetry: figo refuses a
write that starts serving traffic when a precondition it can check itself does
not hold, and never refuses one that stops it. 'disable' is one of the remedies
for a broken mapping, so refusing it because the mapping is broken would take
the remedy away from the person applying it.

Nothing here runs a command: the decision and the command line are pure
functions, and the I/O half only carries their result to the gateway.
"""

import pytest


GATEWAYS = {
    "10.202.9.128/25": {"scope": "blade3:default.gw-float", "address": "10.202.9.254"},
    "10.202.8.128/25": {"scope": "goldrake:default.gw-float", "address": "10.202.8.254"},
}


def row(public="160.80.105.43", private="10.202.8.141", enabled=False, active=False):
    return {"public": public, "private": private, "enabled": enabled, "active": active,
            "mode": "whitelist", "tcp": [(22, 22)], "udp": [], "icmp": [],
            "icmp_all": False, "label": None, "note": None, "drift": None}


# --- The command line that reaches the container ----------------------------

def test_the_verb_becomes_an_incus_command_line(figo):
    assert figo.floating_ip_write_argv(
        "blade3:default.gw-float", "enable", "160.80.105.43"
    ) == [
        "incus", "exec", "blade3:gw-float", "--project", "default", "--",
        "floating-ip", "enable", "160.80.105.43",
    ]


def test_a_note_travels_as_one_argument(figo):
    """No shell is involved, so a note with spaces needs no quoting -- and must
    not be split, or the gateway would read the first word as the whole note."""
    argv = figo.floating_ip_write_argv(
        "blade3:default.gw-float", "disable", "160.80.105.43",
        note="upstream has not allowed 22"
    )
    assert argv[-2:] == ["--note", "upstream has not allowed 22"]


def test_only_disable_takes_a_note(figo):
    """The gateway accepts --note nowhere else; building it would fail there."""
    with pytest.raises(ValueError):
        figo.floating_ip_write_argv(
            "blade3:default.gw-float", "enable", "160.80.105.43", note="why"
        )


# --- Which gateway a write acts on ------------------------------------------

def test_the_gateway_of_a_remote_is_the_one_that_serves_its_subnet(figo):
    subnet, gateway, warnings = figo.select_gateway_for_remote(GATEWAYS, "blade3")
    assert gateway["scope"] == "blade3:default.gw-float"
    assert subnet == "10.202.9.128/25"
    assert warnings == []


def test_a_remote_without_a_gateway_says_where_to_declare_one(figo):
    subnet, gateway, warnings = figo.select_gateway_for_remote(GATEWAYS, "eln_cloud")
    assert (subnet, gateway) == (None, None)
    assert warnings and "float_gateways" in warnings[0]


def test_more_than_one_gateway_is_reported_not_hidden(figo):
    gateways = dict(GATEWAYS)
    gateways["10.202.9.0/25"] = {"scope": "blade3:default.gw-float-2",
                                 "address": "10.202.9.126"}
    subnet, gateway, warnings = figo.select_gateway_for_remote(gateways, "blade3")
    assert gateway["scope"] == "blade3:default.gw-float-2"
    assert warnings and "more than one gateway" in warnings[0]


# --- The decision -----------------------------------------------------------

def test_a_mapping_the_gateway_does_not_hold_is_refused(figo):
    refusals, warnings = figo.float_write_decision("enable", "160.80.105.99", None)
    assert refusals and "add" in refusals[0]
    assert warnings == []


def test_enabling_over_a_violated_invariant_is_refused(figo):
    """The mapping would look right in every listing and drop the return traffic."""
    refusals, warnings = figo.float_write_decision(
        "enable", "160.80.105.43", row(),
        figo.FLOAT_INVARIANT_VIOLATED,
        "'x' routes by default via 10.202.9.129, not via the gateway 10.202.9.254."
    )
    assert len(refusals) == 1
    assert "10.202.9.129" in refusals[0]
    assert warnings == []


def test_disabling_over_a_violated_invariant_is_allowed(figo):
    """The asymmetry, and the reason for it: disable is a remedy, not a risk."""
    refusals, warnings = figo.float_write_decision(
        "disable", "160.80.105.43", row(enabled=True, active=True),
        figo.FLOAT_INVARIANT_VIOLATED, "whatever the invariant says"
    )
    assert refusals == []


def test_an_invariant_that_could_not_be_read_warns_and_lets_it_through(figo):
    """Section 7.3: refuse what figo verified, warn about what it could not."""
    refusals, warnings = figo.float_write_decision(
        "enable", "160.80.105.43", row(),
        figo.FLOAT_INVARIANT_UNKNOWN,
        "Cannot tell whether 'x' satisfies the invariant: the instance is stopped."
    )
    assert refusals == []
    assert len(warnings) == 1
    assert "cannot verify" in warnings[0]


def test_a_satisfied_invariant_is_silent(figo):
    refusals, warnings = figo.float_write_decision(
        "enable", "160.80.105.43", row(), figo.FLOAT_INVARIANT_OK, "all good"
    )
    assert (refusals, warnings) == ([], [])


# --- The port verbs ---------------------------------------------------------

def test_the_options_reach_the_container_as_separate_arguments(figo):
    argv = figo.floating_ip_write_argv(
        "blade3:default.gw-float", "open", "160.80.105.36",
        options=["--tcp", "8080,8443:443"]
    )
    assert argv[-5:] == [
        "floating-ip", "open", "160.80.105.36", "--tcp", "8080,8443:443",
    ]


def test_the_protocol_options_keep_a_stable_order(figo):
    assert figo.float_port_options("80,443", None, "echo-request") == [
        "--tcp", "80,443", "--icmp", "echo-request"
    ]


def test_no_protocol_at_all_is_no_options(figo):
    """The dispatcher turns this into a refusal: a verb with nothing to change."""
    assert figo.float_port_options(None, None, None) == []


def test_opening_a_port_on_a_serving_mapping_is_gated(figo):
    """More traffic through a mapping whose return path is wrong is more traffic
    that does not arrive."""
    refusals, _ = figo.float_write_decision(
        "open", "160.80.105.36", row(enabled=True, active=True),
        figo.FLOAT_INVARIANT_VIOLATED, "'x' routes by default via 10.202.9.129."
    )
    assert len(refusals) == 1


def test_opening_a_port_on_a_mapping_that_is_off_is_not_gated(figo):
    """Nothing is served yet, so nothing can be served wrongly: the check belongs
    to the moment the mapping is turned on, and that moment has its own verb."""
    refusals, warnings = figo.float_write_decision(
        "open", "160.80.105.36", row(enabled=False, active=False),
        figo.FLOAT_INVARIANT_VIOLATED, "'x' routes by default via 10.202.9.129."
    )
    assert (refusals, warnings) == ([], [])


def test_closing_a_port_is_never_gated(figo):
    refusals, _ = figo.float_write_decision(
        "close", "160.80.105.36", row(enabled=True, active=True),
        figo.FLOAT_INVARIANT_VIOLATED, "'x' routes by default via 10.202.9.129."
    )
    assert refusals == []


def test_replace_is_gated_like_open(figo):
    refusals, _ = figo.float_write_decision(
        "replace", "160.80.105.36", row(enabled=True, active=True),
        figo.FLOAT_INVARIANT_VIOLATED, "'x' routes by default via 10.202.9.129."
    )
    assert len(refusals) == 1


# --- What figo can tell is a no-op, and what it deliberately cannot ----------

def test_enable_on_an_enabled_mapping_changes_nothing(figo):
    assert figo.float_write_is_noop("enable", row(enabled=True)) is True
    assert figo.float_write_is_noop("disable", row(enabled=False)) is True


def test_a_note_is_always_a_change(figo):
    assert figo.float_write_is_noop("disable", row(enabled=False), note="why") is False


def test_a_port_verb_is_never_declared_a_noop_here(figo):
    """Deciding it would mean re-implementing the gateway's port semantics in a
    second place; the gateway says 'nothing changed' itself when that is true."""
    assert figo.float_write_is_noop("open", row(enabled=True)) is False


# --- Reporting what a mapping allows, after the write -----------------------

def test_a_remapped_port_is_rendered_as_such(figo):
    assert figo.format_allow(
        {"mode": "whitelist", "tcp": [(80, 80), (8443, 443)], "udp": [], "icmp": []}
    ) == "tcp 80, 8443:443"


def test_icmp_all_is_not_printed_as_an_empty_list(figo):
    assert figo.format_allow(
        {"mode": "whitelist", "tcp": [], "udp": [], "icmp": [], "icmp_all": True}
    ) == "icmp all"


def test_a_mapping_with_no_allow_says_everything(figo):
    """'open mode' and 'a whitelist that happens to be empty' are opposites, and
    the report must not print them the same way."""
    assert figo.format_allow({"mode": "open"}) == "everything (no allow)"
    assert figo.format_allow(
        {"mode": "whitelist", "tcp": [], "udp": [], "icmp": []}) == "nothing"
