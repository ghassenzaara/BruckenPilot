"""Supabase client factory.

Uses the service-role key, so the batch has full write access (no RLS in the
batch path). The frontend will later use the anon key with read-only RLS.
"""
from functools import lru_cache

from supabase import Client, create_client

from backend import config


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return a cached Supabase client, or fail loudly if config is missing."""
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env "
            "(project root). Copy .env.example to .env and fill them in."
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
