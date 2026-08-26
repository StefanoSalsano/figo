"""Unit tests for `gpu_start_decision`, the start-time GPU verdict.

The function is a pure mapping from (requested cards, current holders,
instance type) to (blocked, shared): the four-row table of Section 4 of
`figo-gpu-resource-model.md`. It is tested with plain dictionaries -- no
client, no remote, no Incus.

Cards are keyed by PCI address, and a holder is a (project, instance name)
couple, as produced by `gpu_holders`.
"""

CARD_A = "06:00.0"
CARD_B = "07:00.0"
CARD_C = "08:00.0"

VM_HOLDER = ("figo-x", "some-vm")
CNT_HOLDER = ("figo-y", "a-usman-test")
OTHER_CNT_HOLDER = ("figo-z", "d-comet-test")


# --- Section 4, row by row --------------------------------------------------

def test_vm_blocked_by_running_vm(figo):
    """VM start, card held by a running VM: refused, passthrough cannot share."""
    blocked, shared = figo.gpu_start_decision(
        {CARD_A}, {CARD_A: [VM_HOLDER]}, {}, "vm"
    )
    assert blocked == [(CARD_A, "vm", [VM_HOLDER])]
    assert shared == []


def test_vm_blocked_by_running_container(figo):
    """VM start, card used by a container: refused, never unbind under a live container."""
    blocked, shared = figo.gpu_start_decision(
        {CARD_A}, {}, {CARD_A: [CNT_HOLDER]}, "vm"
    )
    assert blocked == [(CARD_A, "container", [CNT_HOLDER])]
    assert shared == []


def test_container_blocked_by_running_vm(figo):
    """Container start, card held by a VM: refused, the card is absent from the host."""
    blocked, shared = figo.gpu_start_decision(
        {CARD_A}, {CARD_A: [VM_HOLDER]}, {}, "container"
    )
    assert blocked == [(CARD_A, "vm", [VM_HOLDER])]
    assert shared == []


def test_container_shares_card_with_other_containers(figo):
    """Container start on a card other containers use: allowed, and reported as shared.

    This is the case that the ollama container on jeeg depends on: time-slicing
    between containers is normal operation, not an error.
    """
    holders = [CNT_HOLDER, OTHER_CNT_HOLDER]
    blocked, shared = figo.gpu_start_decision(
        {CARD_A}, {}, {CARD_A: holders}, "container"
    )
    assert blocked == []
    assert shared == [(CARD_A, holders)]


# --- Free cards, no requests ------------------------------------------------

def test_free_card_is_neither_blocked_nor_shared(figo):
    for instance_type in ("vm", "container"):
        blocked, shared = figo.gpu_start_decision({CARD_A}, {}, {}, instance_type)
        assert blocked == []
        assert shared == []


def test_instance_without_gpus_is_never_blocked(figo):
    blocked, shared = figo.gpu_start_decision(
        set(), {CARD_A: [VM_HOLDER]}, {CARD_B: [CNT_HOLDER]}, "vm"
    )
    assert blocked == []
    assert shared == []


def test_holders_of_other_cards_are_irrelevant(figo):
    """Only the requested cards are examined: a busy neighbour card blocks nothing."""
    blocked, shared = figo.gpu_start_decision(
        {CARD_A}, {CARD_B: [VM_HOLDER]}, {CARD_C: [CNT_HOLDER]}, "container"
    )
    assert blocked == []
    assert shared == []


# --- All-or-nothing over several cards --------------------------------------

def test_multi_card_lists_every_contended_card(figo):
    """A start that wants three cards reports all the contended ones, not the first."""
    blocked, shared = figo.gpu_start_decision(
        {CARD_A, CARD_B, CARD_C},
        {CARD_C: [VM_HOLDER]},
        {CARD_A: [CNT_HOLDER]},
        "vm",
    )
    assert blocked == [
        (CARD_A, "container", [CNT_HOLDER]),
        (CARD_C, "vm", [VM_HOLDER]),
    ]
    assert shared == []


def test_multi_card_container_mixes_blocked_and_shared(figo):
    """A container can be refused on one card while it would have shared another."""
    blocked, shared = figo.gpu_start_decision(
        {CARD_A, CARD_B},
        {CARD_B: [VM_HOLDER]},
        {CARD_A: [CNT_HOLDER]},
        "container",
    )
    assert blocked == [(CARD_B, "vm", [VM_HOLDER])]
    assert shared == [(CARD_A, [CNT_HOLDER])]


def test_blocked_cards_are_reported_in_pci_order(figo):
    """The order is the sorted PCI address, so the refusal message is stable."""
    blocked, _ = figo.gpu_start_decision(
        {CARD_C, CARD_A, CARD_B},
        {CARD_A: [VM_HOLDER], CARD_B: [VM_HOLDER], CARD_C: [VM_HOLDER]},
        {},
        "container",
    )
    assert [pci for pci, _kind, _holders in blocked] == [CARD_A, CARD_B, CARD_C]


# --- Precedence -------------------------------------------------------------

def test_vm_holder_wins_over_container_holder_in_the_reason(figo):
    """A card held by a VM *and* a container is reported as held by the VM.

    The VM is the stronger fact: the card is in vfio, so the reason given to the
    administrator has to be the passthrough, not the time-slicing.
    """
    blocked, shared = figo.gpu_start_decision(
        {CARD_A}, {CARD_A: [VM_HOLDER]}, {CARD_A: [CNT_HOLDER]}, "container"
    )
    assert blocked == [(CARD_A, "vm", [VM_HOLDER])]
    assert shared == []


def test_empty_holder_lists_do_not_block(figo):
    """A card whose holder list is empty is free: a stopped instance holds nothing."""
    blocked, shared = figo.gpu_start_decision(
        {CARD_A}, {CARD_A: []}, {CARD_A: []}, "vm"
    )
    assert blocked == []
    assert shared == []
