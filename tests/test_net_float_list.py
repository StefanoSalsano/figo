"""Unit tests for the floating-IP join and the default-gateway invariant.

Two things are checked here. The join: the mappings a gateway holds against the
instances figo knows, including the case nobody wants to think about — a mapping
whose private address belongs to no instance. And the invariant of Section 3.3:
an instance reached through a floating IP must have the serving gw-float as its
default gateway, or the return path never passes through the gateway and the
mapping cannot work.

The invariant is read per instance and never deduced from the subnet: measured
on 2026-08-26, instances on the same subnet differ depending on whether they
hold a floating IP.
"""

import pytest


GW = "10.202.9.254"


def instance(name, project, addresses, status="Running", additional=()):
    return {
        "name": name,
        "project": project,
        "scope": f"blade3:{project}.{name}",
        "status": status,
        "type": "container",
        "addresses": list(addresses),
        "additional": list(additional),
    }


RECORDS = [
    instance("f-patri", "figo-f-patri", ["10.202.9.210/25"]),
    instance("g-alci", "figo-g-alci", ["10.202.9.211/25"]),
    instance("n-cloud", "figo-n-cloud", ["10.202.9.212/25"]),
    instance("c-ricci", "figo-c-ricci", ["10.202.9.213/25"]),
]


def mapping(public, private, enabled=True, active=True):
    return {"public": public, "private": private, "enabled": enabled, "active": active,
            "mode": "whitelist", "tcp": [(443, 443)], "udp": [], "icmp": ["echo-reply"]}


# --- Reading the default route ----------------------------------------------

def test_parse_default_gateway(figo):
    assert figo.parse_default_gateways(
        "default via 10.202.9.254 dev enp5s0 proto static\n"
    ) == ["10.202.9.254"]


def test_parse_ignores_non_default_routes(figo):
    assert figo.parse_default_gateways(
        "10.202.9.128/25 dev enp5s0 proto kernel scope link src 10.202.9.210\n"
    ) == []


def test_parse_reports_every_default_route(figo):
    """More than one default route is unusual, and worth showing rather than hiding."""
    assert figo.parse_default_gateways(
        "default via 10.202.9.254 dev enp5s0\ndefault via 10.202.9.129 dev enp6s0\n"
    ) == ["10.202.9.254", "10.202.9.129"]


def test_parse_of_nothing(figo):
    assert figo.parse_default_gateways("") == []
    assert figo.parse_default_gateways(None) == []


def test_read_of_a_stopped_instance_is_unavailable_not_an_error(figo):
    read = figo.classify_default_gateway_read(
        "blade3:figo-x.i", 1, "", "Error: Instance is not running"
    )
    assert read.outcome == figo.GATEWAY_READ_UNAVAILABLE


def test_read_failure_keeps_stderr(figo):
    read = figo.classify_default_gateway_read("blade3:figo-x.i", 127, "", "boom")
    assert read.outcome == figo.GATEWAY_READ_ERROR
    assert "boom" in read.detail


# --- Indexing instances by the addresses they hold --------------------------

def test_index_strips_the_prefix(figo):
    index, warnings = figo.index_instances_by_address(RECORDS)
    assert warnings == []
    assert index["10.202.9.210"][0]["name"] == "f-patri"


def test_index_includes_additional_addresses(figo):
    """A floating IP can point at an address held for a nested VM."""
    records = [instance("host-vm", "figo-x", ["10.202.9.220/25"],
                        additional=["10.202.9.221"])]
    index, _ = figo.index_instances_by_address(records)
    assert index["10.202.9.221"][0]["name"] == "host-vm"


def test_duplicate_address_is_reported(figo):
    records = RECORDS + [instance("clone", "figo-y", ["10.202.9.210/25"])]
    index, warnings = figo.index_instances_by_address(records)
    assert len(index["10.202.9.210"]) == 2
    assert any("more than one instance" in warning for warning in warnings)


# --- The join ---------------------------------------------------------------

def test_join_finds_the_holder(figo):
    index, _ = figo.index_instances_by_address(RECORDS)
    rows = figo.build_float_rows([mapping("160.80.105.35", "10.202.9.210")], index)
    assert rows[0]["instance"]["name"] == "f-patri"
    assert rows[0]["public"] == "160.80.105.35"


def test_an_orphaned_mapping_still_produces_a_row(figo):
    """The disabled .43 points into another subnet: no holder here, but it exists."""
    index, _ = figo.index_instances_by_address(RECORDS)
    rows = figo.build_float_rows(
        [mapping("160.80.105.43", "10.202.8.141", enabled=False, active=False)], index
    )
    assert len(rows) == 1
    assert rows[0]["instance"] is None


def test_instances_without_a_mapping_do_not_appear(figo):
    index, _ = figo.index_instances_by_address(RECORDS)
    rows = figo.build_float_rows([mapping("160.80.105.35", "10.202.9.210")], index)
    assert [row["public"] for row in rows] == ["160.80.105.35"]


# --- The invariant ----------------------------------------------------------

def test_invariant_satisfied(figo):
    read = figo.DefaultGatewayRead(figo.GATEWAY_READ_OK, [GW], "")
    status, detail = figo.float_invariant_status(
        mapping("160.80.105.35", "10.202.9.210"), RECORDS[0], read, GW
    )
    assert status == figo.FLOAT_INVARIANT_OK


def test_invariant_violated_by_a_different_gateway(figo):
    """The constructed case: on the real system every mapping currently complies.

    c-ricci routes via .129 and holds no floating IP, which is correct; give it a
    mapping and the same route becomes a violation. Waiting for a real one to
    appear is not a test.
    """
    read = figo.DefaultGatewayRead(figo.GATEWAY_READ_OK, ["10.202.9.129"], "")
    status, detail = figo.float_invariant_status(
        mapping("160.80.105.38", "10.202.9.213"), RECORDS[3], read, GW
    )
    assert status == figo.FLOAT_INVARIANT_VIOLATED
    assert "10.202.9.129" in detail
    assert GW in detail
    assert "return path" in detail


def test_instance_with_no_default_route_violates(figo):
    read = figo.DefaultGatewayRead(figo.GATEWAY_READ_OK, [], "")
    status, detail = figo.float_invariant_status(
        mapping("160.80.105.35", "10.202.9.210"), RECORDS[0], read, GW
    )
    assert status == figo.FLOAT_INVARIANT_VIOLATED
    assert "no default route" in detail


def test_several_default_routes_including_the_right_one_is_accepted(figo):
    read = figo.DefaultGatewayRead(figo.GATEWAY_READ_OK, ["10.202.9.129", GW], "")
    status, _ = figo.float_invariant_status(
        mapping("160.80.105.35", "10.202.9.210"), RECORDS[0], read, GW
    )
    assert status == figo.FLOAT_INVARIANT_OK


def test_unreadable_route_is_unknown_not_violated(figo):
    """A stopped instance is not a misconfigured one: false alarms teach people
    to ignore alarms."""
    read = figo.DefaultGatewayRead(figo.GATEWAY_READ_UNAVAILABLE, [], "not running")
    status, detail = figo.float_invariant_status(
        mapping("160.80.105.35", "10.202.9.210"), RECORDS[0], read, GW
    )
    assert status == figo.FLOAT_INVARIANT_UNKNOWN


def test_mapping_with_no_holder_is_unknown(figo):
    status, detail = figo.float_invariant_status(
        mapping("160.80.105.43", "10.202.8.141"), None, None, GW
    )
    assert status == figo.FLOAT_INVARIANT_UNKNOWN
    assert "10.202.8.141" in detail


def test_a_mapping_that_is_off_is_not_checked(figo):
    status, detail = figo.float_invariant_status(
        mapping("160.80.105.43", "10.202.8.141", enabled=False, active=False),
        None, None, GW,
    )
    assert status == figo.FLOAT_INVARIANT_NOT_CHECKED


def test_enabled_but_not_active_is_still_checked(figo):
    """Half-on is exactly when the invariant matters: it is about to be applied."""
    read = figo.DefaultGatewayRead(figo.GATEWAY_READ_OK, ["10.202.9.129"], "")
    status, _ = figo.float_invariant_status(
        mapping("160.80.105.35", "10.202.9.210", enabled=True, active=False),
        RECORDS[0], read, GW,
    )
    assert status == figo.FLOAT_INVARIANT_VIOLATED


@pytest.mark.parametrize("status_attribute", [
    "FLOAT_INVARIANT_OK", "FLOAT_INVARIANT_VIOLATED",
    "FLOAT_INVARIANT_UNKNOWN", "FLOAT_INVARIANT_NOT_CHECKED",
])
def test_every_verdict_explains_itself(figo, status_attribute):
    cases = {
        "FLOAT_INVARIANT_OK": (
            mapping("160.80.105.35", "10.202.9.210"), RECORDS[0],
            figo.DefaultGatewayRead(figo.GATEWAY_READ_OK, [GW], "")),
        "FLOAT_INVARIANT_VIOLATED": (
            mapping("160.80.105.35", "10.202.9.210"), RECORDS[0],
            figo.DefaultGatewayRead(figo.GATEWAY_READ_OK, ["10.202.9.129"], "")),
        "FLOAT_INVARIANT_UNKNOWN": (
            mapping("160.80.105.35", "10.202.9.210"), RECORDS[0],
            figo.DefaultGatewayRead(figo.GATEWAY_READ_ERROR, [], "boom")),
        "FLOAT_INVARIANT_NOT_CHECKED": (
            mapping("160.80.105.43", "10.202.8.141", enabled=False, active=False),
            None, None),
    }
    map_, record, read = cases[status_attribute]
    status, detail = figo.float_invariant_status(map_, record, read, GW)
    assert status == getattr(figo, status_attribute)
    assert detail.strip()
