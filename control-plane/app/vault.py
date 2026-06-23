"""Secure key vault for the Control Plane.

Implements the "secure vault for storing API keys" Phase 1 milestone
(docs/06-roadmap.md). Security choices for the MVP:

- Secrets live in memory only and are NEVER written to disk or returned over the
  API. Callers can only see whether a key is set and a masked preview.
- Secrets may be seeded from the environment at startup via the BYI_KEY_<NAME>
  convention (e.g. BYI_KEY_ANTHROPIC -> key name "ANTHROPIC").

This is a deliberately small stand-in for a managed secret manager (AWS Secrets
Manager / Vault), which later phases adopt.
"""

from __future__ import annotations

import os
import threading

from .models import VaultKeyInfo

ENV_PREFIX = "BYI_KEY_"


def _mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


class Vault:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._secrets: dict[str, str] = {}

    def seed_from_env(self, environ: dict[str, str] | None = None) -> None:
        environ = environ if environ is not None else dict(os.environ)
        for env_name, value in environ.items():
            if env_name.startswith(ENV_PREFIX) and value:
                self.set_key(env_name[len(ENV_PREFIX) :], value)

    def set_key(self, name: str, value: str) -> None:
        with self._lock:
            self._secrets[name] = value

    def has_key(self, name: str) -> bool:
        return name in self._secrets

    def get_secret(self, name: str) -> str | None:
        """Return the raw secret. Internal use only (e.g. by an LLM provider)."""
        return self._secrets.get(name)

    def info(self, name: str) -> VaultKeyInfo:
        secret = self._secrets.get(name, "")
        return VaultKeyInfo(name=name, is_set=bool(secret), preview=_mask(secret))

    def list_keys(self) -> list[VaultKeyInfo]:
        with self._lock:
            return [self.info(name) for name in sorted(self._secrets)]
