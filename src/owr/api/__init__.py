"""Phase 4 — FastAPI backend over the simulation engine.

The API is deliberately storage-agnostic: it talks to a small repository interface
(``store.Repository``) with an in-memory implementation, so the whole service runs
and is tested with no database and no external credentials. Swapping in a
PostgreSQL-backed repository (Phase 1 schema) is a later, isolated change.
"""

from owr.api.app import create_app

__all__ = ["create_app"]
