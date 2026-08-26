"""Test fixtures for the figo suite.

figo is a single module, `figo.py`, that imports third-party packages at the
top level (pylxd, paramiko, argcomplete, ...). None of them is needed by the
pure decision functions this suite exercises, so requiring them would make the
tests unrunnable exactly where they are most useful: a bare checkout and a CI
runner with nothing installed.

The module is therefore loaded by path as `figo_cli`, with a meta-path finder
that fabricates empty stand-in modules for the third-party packages that are
*not* installed. Packages that are installed are imported for real, so the
stubs never hide a genuine import error on a developer machine.

The suite must never open a client, a socket or a file: everything under test
receives facts and returns a verdict.
"""

import importlib.abc
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIGO_PY = REPO_ROOT / "figo.py"

# Top-level packages figo.py imports and this suite does not need.
THIRD_PARTY = ("argcomplete", "pylxd", "paramiko", "cryptography", "yaml")


class _StubModule(types.ModuleType):
    """A module that answers any attribute access with another stub.

    Enough for `import x.y.z` and for module-level `x.y` lookups; anything a
    test actually calls would return a stub and fail loudly, which is the
    intended outcome -- these tests are not supposed to reach third-party code.
    """

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        child = _StubModule(f"{self.__name__}.{name}")
        sys.modules[child.__name__] = child
        setattr(self, name, child)
        return child


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        pass


class _StubFinder(importlib.abc.MetaPathFinder):
    """Fabricates the listed packages, and only those, with their subpackages."""

    def __init__(self, names):
        self._names = set(names)

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in self._names:
            return None
        return importlib.util.spec_from_loader(fullname, _StubLoader(), is_package=True)


def _missing_packages(names):
    missing = []
    for name in names:
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)
    return missing


def _load_figo():
    missing = _missing_packages(THIRD_PARTY)
    finder = _StubFinder(missing) if missing else None
    if finder:
        sys.meta_path.insert(0, finder)
    try:
        spec = importlib.util.spec_from_file_location("figo_cli", FIGO_PY)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {FIGO_PY}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["figo_cli"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if finder:
            sys.meta_path.remove(finder)


@pytest.fixture(scope="session")
def figo():
    """The figo.py module, imported once per session with no side effects."""
    return _load_figo()
