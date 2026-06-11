"""atomicmemory.contract — v1 provider-contract wire codec.

Re-exports the public codec functions from :mod:`atomicmemory.contract.v1`.
Import the submodule directly for IDE discoverability:

    from atomicmemory.contract import v1

    page = v1.decode_search_result_page(wire_dict)
    wire = v1.encode_search_result_page(page)

This package is a specialty surface; it is deliberately NOT re-exported from
the ``atomicmemory`` package root to keep the root namespace focused on the
core provider API.
"""

from atomicmemory.contract import v1

__all__ = ["v1"]
