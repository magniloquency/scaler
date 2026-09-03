"""Deferred access to the IBM Spectrum Symphony ``soamapi`` module.

This module is not ``soamapi`` itself, it is how the rest of the package reaches it. The stub that
describes the real API is ``stubs/soamapi.pyi``, which is unrelated to this file.

``soamapi`` is not installable from PyPI. It ships with the Symphony product and is put on
``PYTHONPATH`` from ``$SOAM_HOME/$VERSION_NUM/$EGO_MACHINE_TYPE/lib64/pythonapi_<python-version>``.

The import is deferred to call time so that this package stays importable, and its
Symphony-independent logic stays unit testable, on hosts without a Symphony installation.
"""

import types

SOAMAPI_MISSING_MESSAGE = (
    "IBM Spectrum Symphony API (soamapi) not found. It is not installable from PyPI, it ships with the "
    "Symphony product. Add $SOAM_HOME/$VERSION_NUM/$EGO_MACHINE_TYPE/lib64/pythonapi_<python-version> to "
    "PYTHONPATH."
)


def load_soamapi() -> types.ModuleType:
    """Return the ``soamapi`` module, raising a descriptive ``ImportError`` when it is unavailable."""
    try:
        import soamapi
    except ImportError as error:
        raise ImportError(SOAMAPI_MISSING_MESSAGE) from error

    return soamapi
