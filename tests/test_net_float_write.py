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


# --- Bookkeeping: the verbs that change no rule -----------------------------

def test_a_text_with_spaces_stays_one_argument(figo):
    argv = figo.floating_ip_write_argv(
        "blade3:default.gw-float", "note", "160.80.105.43",
        options=figo.float_bookkeeping_options("port 22 not allowed upstream yet")
    )
    assert argv[-2:] == ["160.80.105.43", "port 22 not allowed upstream yet"]


def test_clearing_is_its_own_option(figo):
    assert figo.float_bookkeeping_options(clear=True) == ["--clear"]


def test_a_text_and_clear_together_is_an_error(figo):
    """Not a precedence rule: a label cleared by accident is an owner lost."""
    with pytest.raises(ValueError):
        figo.float_bookkeeping_options("web-team", clear=True)


def test_neither_a_text_nor_clear_is_an_error(figo):
    with pytest.raises(ValueError):
        figo.float_bookkeeping_options()


def test_writing_the_label_that_is_already_there_changes_nothing(figo):
    labelled = dict(row(), label="web-team")
    assert figo.float_write_is_noop("label", labelled, text="web-team") is True
    assert figo.float_write_is_noop("label", labelled, text="billing") is False


def test_clearing_a_label_that_is_not_there_changes_nothing(figo):
    assert figo.float_write_is_noop("label", row(), clear=True) is True


def test_clearing_a_label_that_is_there_is_a_change(figo):
    assert figo.float_write_is_noop(
        "label", dict(row(), label="web-team"), clear=True) is False


def test_bookkeeping_is_never_gated_on_the_invariant(figo):
    """These verbs move no packet: gating them would refuse to record why a
    mapping is broken exactly when someone is trying to write it down."""
    refusals, warnings = figo.float_write_decision(
        "note", "160.80.105.43", row(enabled=True, active=True),
        figo.FLOAT_INVARIANT_VIOLATED, "'x' routes by default via 10.202.9.129."
    )
    assert (refusals, warnings) == ([], [])


def test_clearing_is_compared_against_emptiness_not_against_the_text(figo):
    """A surviving mutant found this gap: with --clear, the value figo compares
    the current label against is 'nothing', never the text that came with it.
    The CLI cannot send both today -- float_bookkeeping_options refuses -- but
    the rule belongs to the function that decides, not to its caller.
    """
    labelled = dict(row(), label="web-team")
    assert figo.float_write_is_noop(
        "label", labelled, text="web-team", clear=True) is False


# --- Creating and deleting a whole mapping ----------------------------------

RECORDS_FOR_ADD = [
    {"name": "myinst", "project": "figo-x", "scope": "blade3:figo-x.myinst",
     "status": "Running", "addresses": ["10.202.9.220/25"], "additional": []},
    {"name": "myinst", "project": "figo-y", "scope": "blade3:figo-y.myinst",
     "status": "Running", "addresses": ["10.202.9.221/25"], "additional": []},
    {"name": "alone", "project": "figo-x", "scope": "blade3:figo-x.alone",
     "status": "Stopped", "addresses": ["10.202.9.222/25", "10.202.8.10/25"],
     "additional": []},
]


def test_an_instance_is_found_by_its_bare_name(figo):
    instance, error = figo.find_instance_by_reference(RECORDS_FOR_ADD, "alone")
    assert error is None
    assert instance["scope"] == "blade3:figo-x.alone"


def test_the_same_name_in_two_projects_is_refused_not_guessed(figo):
    """Which instance gets a public address is not a guess figo may make."""
    instance, error = figo.find_instance_by_reference(RECORDS_FOR_ADD, "myinst")
    assert instance is None
    assert "more than one" in error


def test_the_project_disambiguates(figo):
    instance, error = figo.find_instance_by_reference(RECORDS_FOR_ADD, "figo-y.myinst")
    assert error is None
    assert instance["scope"] == "blade3:figo-y.myinst"


def test_an_unknown_instance_says_where_to_look(figo):
    instance, error = figo.find_instance_by_reference(RECORDS_FOR_ADD, "ghost")
    assert instance is None
    assert "instance list" in error


def test_only_the_address_behind_this_gateway_counts(figo):
    """The instance also holds an address on another subnet; a mapping on this
    gateway can only point at the one behind it."""
    assert figo.address_in_subnet(
        ["10.202.9.222/25", "10.202.8.10/25"], "10.202.9.128/25") == ["10.202.9.222"]


def test_an_instance_with_no_address_here_yields_nothing(figo):
    assert figo.address_in_subnet(["10.202.8.10/25"], "10.202.9.128/25") == []


def test_a_malformed_address_is_skipped_not_fatal(figo):
    assert figo.address_in_subnet(
        ["", "not-an-ip", "10.202.9.222/25"], "10.202.9.128/25") == ["10.202.9.222"]


def test_add_needs_a_whitelist_or_all_ports_by_name(figo):
    """A mapping written without 'allow' forwards everything: no instance should
    be opened to the Internet because a flag was forgotten."""
    with pytest.raises(ValueError):
        figo.float_add_options("10.202.9.220")


def test_all_ports_and_a_port_list_together_are_refused(figo):
    with pytest.raises(ValueError):
        figo.float_add_options("10.202.9.220", tcp="80", all_ports=True)


def test_the_options_of_add_carry_the_private_address_first(figo):
    assert figo.float_add_options(
        "10.202.9.220", tcp="80,443", label="billing"
    ) == ["--private", "10.202.9.220", "--tcp", "80,443", "--label", "billing"]


def test_all_ports_is_passed_through_by_name(figo):
    assert figo.float_add_options("10.202.9.220", all_ports=True) == [
        "--private", "10.202.9.220", "--all-ports"]


def test_adding_an_address_the_gateway_already_maps_is_refused(figo):
    """For every other verb an absent mapping is the refusal; for 'add' the
    present one is."""
    refusals, _ = figo.float_write_decision(
        "add", "160.80.105.36", row(public="160.80.105.36", private="10.202.9.211")
    )
    assert len(refusals) == 1
    assert "10.202.9.211" in refusals[0]


def test_adding_over_a_violated_invariant_is_refused(figo):
    refusals, _ = figo.float_write_decision(
        "add", "160.80.105.44", None,
        figo.FLOAT_INVARIANT_VIOLATED, "'myinst' routes by default via 10.202.9.129."
    )
    assert len(refusals) == 1


def test_adding_a_mapping_that_does_not_exist_yet_is_the_normal_case(figo):
    refusals, warnings = figo.float_write_decision(
        "add", "160.80.105.44", None, figo.FLOAT_INVARIANT_OK, "all good"
    )
    assert (refusals, warnings) == ([], [])


def test_removing_a_mapping_the_gateway_does_not_have_is_refused(figo):
    refusals, _ = figo.float_write_decision("remove", "160.80.105.99", None)
    assert refusals and "add" in refusals[0]


def test_removing_is_never_gated_on_the_invariant(figo):
    refusals, _ = figo.float_write_decision(
        "remove", "160.80.105.44", row(enabled=True, active=True),
        figo.FLOAT_INVARIANT_VIOLATED, "'x' routes by default via 10.202.9.129."
    )
    assert refusals == []
