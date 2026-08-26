"""Unit tests for the per-card view of `figo gpu status` (Section 5.3).

Two pure functions carry the redesign: `classify_gpu_profile`, which reads a
profile from its device rather than from its name (Section 2.2), and
`build_gpu_status_rows`, which merges the three sources -- the offer, the
physical inventory, the usage -- into one row per card. The interesting cases
are the ones where the three disagree, which is exactly what the old aggregate
counters could not show.
"""


def cnt_profile(index, pci):
    return {index: (pci, f"gpu-cnt-{index}-{pci.replace(':', '').replace('.', '')[:5]}")}


# --- Reading one profile ----------------------------------------------------

def test_a_profile_not_named_gpu_is_not_our_business(figo):
    kind, index, pci, warning = figo.classify_gpu_profile(
        "instance-medium", {"root": {"type": "disk"}}
    )
    assert (kind, index, pci, warning) == (None, None, None, None)


def test_canonical_container_profile(figo):
    kind, index, pci, warning = figo.classify_gpu_profile(
        "gpu-cnt-1-06000",
        {"gpu-device1": {"type": "gpu", "gputype": "physical", "pci": "06:00.0"}},
    )
    assert (kind, index, pci) == ("cnt", 1, "06:00.0")
    assert warning is None


def test_canonical_vm_profile_with_a_domain_in_the_address(figo):
    kind, index, pci, warning = figo.classify_gpu_profile(
        "gpu-vm-2-07000",
        {"gpu-device1": {"type": "gpu", "pci": "0000:07:00.0"}},
    )
    assert (kind, index, pci) == ("vm", 2, "07:00.0")
    assert warning is None


def test_profile_named_like_a_gpu_but_carrying_none(figo):
    kind, index, pci, warning = figo.classify_gpu_profile(
        "gpu-cnt-1-06000", {"eth0": {"type": "nic"}}
    )
    assert kind is None
    assert "no usable GPU device" in warning


def test_profile_assigning_two_cards_is_not_part_of_the_offer(figo):
    kind, index, pci, warning = figo.classify_gpu_profile(
        "gpu-cnt-1-06000",
        {
            "a": {"type": "gpu", "pci": "06:00.0"},
            "b": {"type": "gpu", "pci": "07:00.0"},
        },
    )
    assert kind is None
    assert "more than one GPU" in warning


def test_legacy_profile_is_reported_with_the_card_it_assigns(figo):
    """`gpu-1-21000` predates the convention: seen, named, but not in the offer."""
    kind, index, pci, warning = figo.classify_gpu_profile(
        "gpu-1-21000", {"gpu-device1": {"type": "gpu", "pci": "21:00.0"}}
    )
    assert kind is None
    assert pci == "21:00.0"
    assert "convention" in warning


# --- Merging the three sources ---------------------------------------------

FOUR_CARD_OFFER = {
    "cnt": {
        1: ("06:00.0", "gpu-cnt-1-06000"),
        2: ("07:00.0", "gpu-cnt-2-07000"),
        3: ("08:00.0", "gpu-cnt-3-08000"),
        4: ("09:00.0", "gpu-cnt-4-09000"),
    },
    "vm": {
        1: ("06:00.0", "gpu-vm-1-06000"),
        2: ("07:00.0", "gpu-vm-2-07000"),
        4: ("09:00.0", "gpu-vm-4-09000"),
    },
}
FOUR_CARDS = ["06:00.0", "07:00.0", "08:00.0", "09:00.0"]


def test_the_table_of_the_model(figo):
    """The worked example of Section 5.3, rebuilt from its three sources."""
    usage = {
        "06:00.0": [
            ("figo-a", "a-usman-test", "Running", "container"),
            ("figo-d", "d-comet-test", "Running", "container"),
            ("default", "llm-test", "Running", "container"),
            ("default", "test-cuda", "Stopped", "container"),
        ],
        "07:00.0": [("figo-me", "ollama", "Running", "container")],
        "09:00.0": [("figo-x", "x", "Running", "vm")],
    }
    rows, notes = figo.build_gpu_status_rows(FOUR_CARD_OFFER, FOUR_CARDS, usage)

    assert notes == []
    assert [row.card_index for row in rows] == [1, 2, 3, 4]

    first = rows[0]
    assert (first.pci, first.cnt_profile, first.vm_profile) == (
        "06:00.0", "gpu-cnt-1-06000", "gpu-vm-1-06000"
    )
    assert (first.running, first.assigned, first.held_by, first.note) == (3, 4, "-", "")

    third = rows[2]
    assert (third.cnt_profile, third.vm_profile) == ("gpu-cnt-3-08000", "-")
    assert (third.running, third.assigned) == (0, 0)

    fourth = rows[3]
    assert fourth.held_by == "VM 'x' (figo-x, vfio)"
    assert (fourth.running, fourth.assigned) == (0, 1)


def test_running_counts_containers_only_the_vm_is_the_holder(figo):
    """A running VM is reported in HELD BY, not counted among the sharers."""
    usage = {"06:00.0": [
        ("figo-x", "vm-a", "Running", "vm"),
        ("figo-y", "cnt-a", "Running", "container"),
        ("figo-z", "cnt-b", "Stopped", "container"),
    ]}
    rows, _ = figo.build_gpu_status_rows(
        {"cnt": cnt_profile(1, "06:00.0"), "vm": {}}, ["06:00.0"], usage
    )
    assert (rows[0].running, rows[0].assigned) == (1, 3)
    assert rows[0].held_by == "VM 'vm-a' (figo-x, vfio)"


def test_card_present_but_not_offered_gets_a_row_marked_as_such(figo):
    """A card assigned by hand, or reserved: visible, outside the offer."""
    rows, _ = figo.build_gpu_status_rows(
        {"cnt": cnt_profile(1, "06:00.0"), "vm": {}}, ["06:00.0", "0a:00.0"], {}
    )
    assert [row.card_index for row in rows] == [1, None]
    outside = rows[1]
    assert (outside.pci, outside.cnt_profile, outside.vm_profile) == ("0a:00.0", "-", "-")
    assert outside.note == "not offered"


def test_card_offered_but_absent_from_lspci_is_flagged(figo):
    """A profile left behind after a hardware change: the row says the card is gone."""
    rows, _ = figo.build_gpu_status_rows(
        {"cnt": cnt_profile(1, "06:00.0"), "vm": {}}, [], {}
    )
    assert rows[0].note == "not in lspci"


def test_unknown_inventory_flags_nothing(figo):
    """On an L1 host lspci does not work yet: absence of proof is not absence."""
    rows, _ = figo.build_gpu_status_rows(
        {"cnt": cnt_profile(1, "06:00.0"), "vm": {}}, None, {}
    )
    assert rows[0].note == ""


def test_a_card_known_only_through_a_running_instance_still_appears(figo):
    """Usage is the truth: a card nobody offered, held by an instance, is a row."""
    usage = {"0b:00.0": [("figo-x", "direct", "Running", "container")]}
    rows, _ = figo.build_gpu_status_rows({"cnt": {}, "vm": {}}, None, usage)
    assert len(rows) == 1
    assert (rows[0].card_index, rows[0].pci, rows[0].running) == (None, "0b:00.0", 1)
    assert rows[0].note == "not offered"


def test_twin_profiles_disagreeing_on_the_index_is_reported(figo):
    offer = {
        "cnt": {1: ("06:00.0", "gpu-cnt-1-06000")},
        "vm": {5: ("06:00.0", "gpu-vm-5-06000")},
    }
    rows, notes = figo.build_gpu_status_rows(offer, ["06:00.0"], {})
    assert len(rows) == 1
    assert any("two different card indexes" in note for note in notes)


def test_one_index_naming_two_cards_is_reported(figo):
    offer = {
        "cnt": {1: ("06:00.0", "gpu-cnt-1-06000")},
        "vm": {1: ("07:00.0", "gpu-vm-1-07000")},
    }
    rows, notes = figo.build_gpu_status_rows(offer, ["06:00.0", "07:00.0"], {})
    assert any("two different GPUs" in note for note in notes)
    assert len(rows) == 2


def test_offered_cards_come_first_then_the_others_by_pci(figo):
    offer = {"cnt": {2: ("07:00.0", "gpu-cnt-2-07000")}, "vm": {}}
    rows, _ = figo.build_gpu_status_rows(offer, ["0c:00.0", "07:00.0", "0a:00.0"], {})
    assert [row.pci for row in rows] == ["07:00.0", "0a:00.0", "0c:00.0"]


def test_nothing_anywhere_is_an_empty_table_not_a_crash(figo):
    rows, notes = figo.build_gpu_status_rows({"cnt": {}, "vm": {}}, [], {})
    assert rows == []
    assert notes == []


# --- The -i listing ---------------------------------------------------------

def test_instance_listing_puts_running_first(figo):
    usage = {"06:00.0": [
        ("default", "test-cuda", "Stopped", "container"),
        ("figo-d", "d-comet-test", "Running", "container"),
        ("figo-a", "a-usman-test", "Running", "container"),
    ]}
    rows, _ = figo.build_gpu_status_rows(
        {"cnt": cnt_profile(1, "06:00.0"), "vm": {}}, ["06:00.0"], usage
    )
    assert figo.format_gpu_card_instances(rows[0], usage) == (
        "CARD 1 (06:00.0):  a-usman-test (figo-a, RUNNING), "
        "d-comet-test (figo-d, RUNNING), test-cuda (default, STOPPED)"
    )


def test_instance_listing_of_an_unused_card(figo):
    rows, _ = figo.build_gpu_status_rows(
        {"cnt": cnt_profile(3, "08:00.0"), "vm": {}}, ["08:00.0"], {}
    )
    assert figo.format_gpu_card_instances(rows[0], {}) == "CARD 3 (08:00.0):  -"


def test_instance_listing_of_a_card_outside_the_offer(figo):
    usage = {"0b:00.0": [("figo-x", "direct", "Running", "container")]}
    rows, _ = figo.build_gpu_status_rows({"cnt": {}, "vm": {}}, None, usage)
    assert figo.format_gpu_card_instances(rows[0], usage) == (
        "CARD - (0b:00.0):  direct (figo-x, RUNNING)"
    )
