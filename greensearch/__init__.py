"""Legacy name for the Arboris package (renamed from GreenSearch in 0.9.0).

``import greensearch`` and ``from greensearch.footprint import ...`` keep
working for one release: every ``greensearch.<module>`` name points at the
same module object as ``arboris.<module>``, so patches and state are
shared. New code should import ``arboris``. This shim will be removed in
the release after 0.9.0.
"""

import importlib
import sys
import warnings

import arboris as _arboris

_SUBMODULES = (
    "brevity", "cache", "cascade", "cli", "footprint", "local_calc",
    "long_input", "providers", "router", "scorer", "session", "shrink",
    "task_router", "tokenizer", "tokens",
)

for _name in _SUBMODULES:
    _module = importlib.import_module(f"arboris.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module

__version__ = _arboris.__version__

warnings.warn(
    "The 'greensearch' package is now 'arboris'; import arboris instead. "
    "The greensearch name will be removed after 0.9.0.",
    DeprecationWarning,
    stacklevel=2,
)
