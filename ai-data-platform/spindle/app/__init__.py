"""Composition root — supervisor wiring, plugin/port dispatch (spec §E).

The generic, manifest-driven supervisor lives here. It imports the pure ``core``
(saga/DAG/reconcile) and the ``adapters`` at the edge; it holds no deal-flow
strings — every stage name, saga shape, and retry edge is data the manifest
declares and the plugin registry resolves.
"""
