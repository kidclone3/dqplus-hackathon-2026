"""Spindle — the domain-agnostic agent data platform core.

Apps declare a manifest (``app.yaml``) + a plugin module; the platform loads them
into in-memory saga DAGs and AgentSpecs. No deal-flow strings live in this package.
"""
