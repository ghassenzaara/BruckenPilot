"""Domain knowledge: bounds, mappings, and parsing helpers.

Pure data + small pure functions shared across enrichment. No I/O, no network.
Tunable tables (scoring weights, cost rates, capability map) live here so they
can be adjusted without touching pipeline logic.
"""
