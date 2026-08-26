"""Golden tests for `format_gpu_start_refusal` and its two helpers.

The refusal message is an interface: an administrator whose start is refused
can only react to what the message says. Section 4 of
`figo-gpu-resource-model.md` requires it to state what is in the way, whether
there is room elsewhere, and which commands reassign the instance. Freezing
the exact text is the only way to keep it from silently degrading.

These are golden tests: when the wording is changed on purpose, the expected
strings here are updated in the same commit, deliberately.
"""

import textwrap

CARD_A = "06:00.0"
CARD_B = "07:00.0"

VM_HOLDER = ("figo-x", "some-vm")
CNT_HOLDER = ("figo-y", "a-usman-test")
OTHER_CNT_HOLDER = ("figo-z", "d-comet-test")


def expected(text):
    return textwrap.dedent(text).strip("\n")


# --- Helpers ----------------------------------------------------------------

def test_format_instance_list_without_state(figo):
    assert figo.format_instance_list([CNT_HOLDER, OTHER_CNT_HOLDER]) == (
        "'a-usman-test' (project figo-y), 'd-comet-test' (project figo-z)"
    )


def test_format_instance_list_with_state(figo):
    assert figo.format_instance_list([VM_HOLDER], state="RUNNING") == (
        "'some-vm' (project figo-x, RUNNING)"
    )


def test_plural_gpus_counts(figo):
    assert figo.plural_gpus(0) == "0 GPUs"
    assert figo.plural_gpus(1) == "1 GPU"
    assert figo.plural_gpus(2) == "2 GPUs"


# --- The message ------------------------------------------------------------

def test_container_blocked_by_vm_with_room_elsewhere(figo):
    """The canonical refusal: what blocks, where there is room, how to reassign."""
    message = figo.format_gpu_start_refusal(
        instance_name="my-cnt",
        scope="jeeg:figo-me.my-cnt",
        remote="jeeg",
        instance_type="container",
        blocked=[(CARD_A, "vm", [VM_HOLDER])],
        requested_count=1,
        free_card_indexes=[3, 4],
        offer_size=4,
        counterpart_offer_size=0,
    )
    assert message == expected("""
        Cannot start 'my-cnt': GPU 06:00.0 is held by VM 'some-vm' (project figo-x, RUNNING).
        2 GPUs free for containers on 'jeeg' (cards 3, 4) -- enough for this instance (needs 1).
        To reassign:  figo gpu remove jeeg:figo-me.my-cnt -a
                      figo gpu add jeeg:figo-me.my-cnt
    """)


def test_vm_blocked_by_containers_says_retrying_will_not_help(figo):
    """A VM blocked by containers must be told that the way out is stopping them."""
    message = figo.format_gpu_start_refusal(
        instance_name="my-vm",
        scope="jeeg:figo-me.my-vm",
        remote="jeeg",
        instance_type="vm",
        blocked=[(CARD_A, "container", [CNT_HOLDER, OTHER_CNT_HOLDER])],
        requested_count=2,
        free_card_indexes=[],
        offer_size=4,
        counterpart_offer_size=0,
    )
    assert message == expected("""
        Cannot start 'my-vm': GPU 06:00.0 is in use by running container(s) 'a-usman-test' (project figo-y), 'd-comet-test' (project figo-z).
        Only 0 GPUs free for VMs on 'jeeg' (needs 2): stop or reassign other instances first.
        Passing a card through to a VM would take it away from a running container: stop or reassign those containers, retrying will not help.
        To reassign:  figo gpu remove jeeg:figo-me.my-vm -a
                      figo gpu add jeeg:figo-me.my-vm
    """)


def test_no_profile_for_this_regime_names_the_counterpart(figo):
    """Nothing is offered to VMs, but cards exist: say so, or the count reads as a bug."""
    message = figo.format_gpu_start_refusal(
        instance_name="my-vm",
        scope="jeeg:figo-me.my-vm",
        remote="jeeg",
        instance_type="vm",
        blocked=[(CARD_A, "container", [CNT_HOLDER])],
        requested_count=1,
        free_card_indexes=[],
        offer_size=0,
        counterpart_offer_size=4,
    )
    assert message == expected("""
        Cannot start 'my-vm': GPU 06:00.0 is in use by running container(s) 'a-usman-test' (project figo-y).
        No card on 'jeeg' is offered to VMs: no gpu-vm-* profile exists there, the 4 cards present are offered to containers only.
        Passing a card through to a VM would take it away from a running container: stop or reassign those containers, retrying will not help.
        To reassign:  figo gpu remove jeeg:figo-me.my-vm -a
                      figo gpu add jeeg:figo-me.my-vm
    """)


def test_no_profile_at_all_on_the_remote(figo):
    message = figo.format_gpu_start_refusal(
        instance_name="my-cnt",
        scope="jeeg:figo-me.my-cnt",
        remote="jeeg",
        instance_type="container",
        blocked=[(CARD_A, "vm", [VM_HOLDER])],
        requested_count=1,
        free_card_indexes=[],
        offer_size=0,
        counterpart_offer_size=0,
    )
    assert message == expected("""
        Cannot start 'my-cnt': GPU 06:00.0 is held by VM 'some-vm' (project figo-x, RUNNING).
        No card on 'jeeg' is offered to containers: no gpu-cnt-* profile exists there.
        To reassign:  figo gpu remove jeeg:figo-me.my-cnt -a
                      figo gpu add jeeg:figo-me.my-cnt
    """)


def test_every_contended_card_appears_in_one_sentence(figo):
    """All-or-nothing: the refusal lists every card, not the first one found."""
    message = figo.format_gpu_start_refusal(
        instance_name="my-vm",
        scope="jeeg:figo-me.my-vm",
        remote="jeeg",
        instance_type="vm",
        blocked=[
            (CARD_A, "vm", [VM_HOLDER]),
            (CARD_B, "container", [CNT_HOLDER]),
        ],
        requested_count=2,
        free_card_indexes=[3],
        offer_size=4,
        counterpart_offer_size=4,
    )
    first_line = message.splitlines()[0]
    assert first_line == (
        "Cannot start 'my-vm': GPU 06:00.0 is held by VM 'some-vm' (project figo-x, RUNNING); "
        "GPU 07:00.0 is in use by running container(s) 'a-usman-test' (project figo-y)."
    )
    assert message.splitlines()[1] == (
        "Only 1 GPU free for VMs on 'jeeg' (needs 2): stop or reassign other instances first."
    )


def test_singular_free_card_is_enough_for_a_single_card_instance(figo):
    message = figo.format_gpu_start_refusal(
        instance_name="my-cnt",
        scope="jeeg:figo-me.my-cnt",
        remote="jeeg",
        instance_type="container",
        blocked=[(CARD_A, "vm", [VM_HOLDER])],
        requested_count=1,
        free_card_indexes=[2],
        offer_size=4,
        counterpart_offer_size=0,
    )
    assert message.splitlines()[1] == (
        "1 GPU free for containers on 'jeeg' (cards 2) -- enough for this instance (needs 1)."
    )


def test_message_always_ends_with_the_reassign_commands(figo):
    """The two commands are the actionable part: they must survive every branch."""
    for instance_type, offer_size, free in (
        ("vm", 0, []),
        ("vm", 4, [1, 2]),
        ("container", 0, []),
        ("container", 4, []),
    ):
        message = figo.format_gpu_start_refusal(
            instance_name="i",
            scope="jeeg:figo-me.i",
            remote="jeeg",
            instance_type=instance_type,
            blocked=[(CARD_A, "vm", [VM_HOLDER])],
            requested_count=1,
            free_card_indexes=free,
            offer_size=offer_size,
            counterpart_offer_size=0,
        )
        assert message.splitlines()[-2:] == [
            "To reassign:  figo gpu remove jeeg:figo-me.i -a",
            "              figo gpu add jeeg:figo-me.i",
        ]
