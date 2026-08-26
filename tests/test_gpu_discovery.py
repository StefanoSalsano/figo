"""Unit tests for GPU discovery: the four outcomes of Section 7.

`no GPU`, `unreachable`, `not configured` and a genuine `error` used to collapse
into one ERROR + None. They have different meanings and different reactions --
in particular `not configured` is the ordinary state of a nested (L1) host until
req 13, and reading it as a failure is what made L1 hosts look broken.

The classification is a pure function of what the command returned, so all four
are tested without a host to run them on.
"""

import pytest


# --- PCI address normalization ---------------------------------------------

def test_normalize_drops_the_default_domain(figo):
    assert figo.normalize_pci_address("0000:06:00.0") == "06:00.0"


def test_normalize_keeps_a_non_default_domain(figo):
    """A card outside domain 0000 is only named by its full address."""
    assert figo.normalize_pci_address("0001:06:00.0") == "0001:06:00.0"


def test_normalize_is_idempotent_and_trims(figo):
    assert figo.normalize_pci_address("06:00.0") == "06:00.0"
    assert figo.normalize_pci_address("  06:00.0 ") == "06:00.0"


def test_normalize_passes_empty_values_through(figo):
    assert figo.normalize_pci_address("") == ""
    assert figo.normalize_pci_address(None) is None


# --- lspci parsing ----------------------------------------------------------

def test_parse_lspci_reads_the_first_field(figo):
    stdout = (
        "06:00.0 3D controller: NVIDIA Corporation AD102GL [L40S] (rev a1)\n"
        "07:00.0 3D controller: NVIDIA Corporation AD102GL [L40S] (rev a1)\n"
    )
    assert figo.parse_lspci_nvidia(stdout) == ["06:00.0", "07:00.0"]


def test_parse_lspci_ignores_lines_that_are_not_cards(figo):
    """ssh banners and warnings share this output: none of them is a card."""
    stdout = (
        "Warning: Permanently added 'jeeg' to the list of known hosts.\n"
        "06:00.0 3D controller: NVIDIA Corporation AD102GL [L40S]\n"
        "\n"
    )
    assert figo.parse_lspci_nvidia(stdout) == ["06:00.0"]


def test_parse_lspci_normalizes_deduplicates_and_sorts(figo):
    stdout = "0000:07:00.0 3D controller: NVIDIA\n06:00.0 3D controller: NVIDIA\n07:00.0 x\n"
    assert figo.parse_lspci_nvidia(stdout) == ["06:00.0", "07:00.0"]


def test_parse_lspci_of_nothing(figo):
    assert figo.parse_lspci_nvidia("") == []
    assert figo.parse_lspci_nvidia(None) == []


# --- The four outcomes ------------------------------------------------------

def test_ok_lists_the_cards(figo):
    discovery = figo.classify_gpu_discovery(
        "jeeg", True, 0, "06:00.0 3D controller: NVIDIA\n", ""
    )
    assert discovery.outcome == figo.GPU_DISCOVERY_OK
    assert discovery.pci_addresses == ["06:00.0"]


def test_grep_found_nothing_is_not_an_error(figo):
    """grep exits 1 with no stderr: the command worked, the host has no card."""
    discovery = figo.classify_gpu_discovery("blade3", True, 1, "", "")
    assert discovery.outcome == figo.GPU_DISCOVERY_NO_GPU
    assert discovery.pci_addresses == []
    assert "No NVIDIA card" in discovery.detail


def test_command_succeeded_with_no_usable_line_is_also_no_gpu(figo):
    discovery = figo.classify_gpu_discovery("blade3", True, 0, "\n", "")
    assert discovery.outcome == figo.GPU_DISCOVERY_NO_GPU


def test_ssh_failure_is_unreachable_and_names_the_host(figo):
    discovery = figo.classify_gpu_discovery(
        "eln_cloud", True, figo.SSH_FAILURE_RETURNCODE, "", "ssh: connect to host ... : No route to host"
    )
    assert discovery.outcome == figo.GPU_DISCOVERY_UNREACHABLE
    assert "eln_cloud" in discovery.detail
    assert "No route to host" in discovery.detail


def test_missing_ssh_information_is_not_configured_not_a_failure(figo):
    """The L1 case: figo cannot reach the host yet, which is not the host's fault."""
    discovery = figo.classify_gpu_discovery("l1-gpuserv-l0-jeeg", False, None, "", "")
    assert discovery.outcome == figo.GPU_DISCOVERY_NOT_CONFIGURED
    assert "REMOTE_TO_IP_INFO_MAP" in discovery.detail
    assert discovery.pci_addresses == []


def test_a_real_failure_keeps_stderr(figo):
    discovery = figo.classify_gpu_discovery(
        "jeeg", True, 127, "", "bash: line 1: lspci: command not found"
    )
    assert discovery.outcome == figo.GPU_DISCOVERY_ERROR
    assert "lspci: command not found" in discovery.detail


def test_exit_one_with_stderr_is_a_failure_not_an_empty_result(figo):
    """Exit 1 only means 'no card' when nothing was written to stderr."""
    discovery = figo.classify_gpu_discovery(
        "jeeg", True, 1, "", "lspci: Cannot open /sys/bus/pci/devices"
    )
    assert discovery.outcome == figo.GPU_DISCOVERY_ERROR


@pytest.mark.parametrize("outcome_attribute", [
    "GPU_DISCOVERY_OK", "GPU_DISCOVERY_NO_GPU", "GPU_DISCOVERY_UNREACHABLE",
    "GPU_DISCOVERY_NOT_CONFIGURED", "GPU_DISCOVERY_ERROR",
])
def test_every_outcome_carries_a_message(figo, outcome_attribute):
    """No outcome may be silent: the message is the whole point of the taxonomy."""
    cases = {
        "GPU_DISCOVERY_OK": ("jeeg", True, 0, "06:00.0 NVIDIA\n", ""),
        "GPU_DISCOVERY_NO_GPU": ("jeeg", True, 1, "", ""),
        "GPU_DISCOVERY_UNREACHABLE": ("jeeg", True, figo.SSH_FAILURE_RETURNCODE, "", "boom"),
        "GPU_DISCOVERY_NOT_CONFIGURED": ("l1", False, None, "", ""),
        "GPU_DISCOVERY_ERROR": ("jeeg", True, 127, "", "boom"),
    }
    discovery = figo.classify_gpu_discovery(*cases[outcome_attribute])
    assert discovery.outcome == getattr(figo, outcome_attribute)
    assert discovery.detail.strip()
