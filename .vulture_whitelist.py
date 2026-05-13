"""Vulture allowlist for false positives.

Vulture flags every Protocol method parameter as unused because the body
is `...`. The parameter names are part of the Protocol's public
contract (callers may pass them as kwargs), so we silence those flags
here. Provider-implementation modules that actually use these names
will reference them naturally and lift the warning.
"""

# Protocol method parameter names referenced by name in
# atomicmemory/memory/provider.py.
as_of
reason
instructions
inputs
refs

# Context-manager dunder parameters in atomicmemory/client/memory_client.py.
# Required by the Python protocol; never read in our implementations.
exc_type
tb

# `encrypt` was previously allowlisted as protocol-parity-only but is
# now actively checked in MemoryStorageAdapter / SQLiteStorageAdapter.set
# (raises ConfigError when True), so it is no longer a vulture target.
