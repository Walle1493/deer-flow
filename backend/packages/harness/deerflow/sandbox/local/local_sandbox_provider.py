import logging
import os
from pathlib import Path

from deerflow.config.app_config import AppConfig, get_app_config
from deerflow.sandbox.local.local_sandbox import LocalSandbox
from deerflow.sandbox.sandbox import Sandbox
from deerflow.sandbox.sandbox_provider import SandboxProvider

logger = logging.getLogger(__name__)

_singleton: LocalSandbox | None = None


def _resolve_sandbox_env_values(env: dict[str, str]) -> dict[str, str]:
    """Resolve sandbox.environment entries; leading ``$`` uses the host env var name (same as AioSandbox)."""
    resolved: dict[str, str] = {}
    for key, value in env.items():
        if isinstance(value, str) and value.startswith("$"):
            resolved[key] = os.environ.get(value[1:], "")
        else:
            resolved[key] = str(value)
    return resolved


class LocalSandboxProvider(SandboxProvider):
    def __init__(self):
        """Initialize the local sandbox provider with path mappings."""
        self._path_mappings = self._setup_path_mappings()
        self._extra_env = self._build_extra_env()

    def _setup_path_mappings(self) -> dict[str, str]:
        """
        Setup path mappings for local sandbox.

        Maps container paths to actual local paths, including skills directory.

        Returns:
            Dictionary of path mappings
        """
        mappings = {}

        # Map skills container path to local skills directory
        try:
            from deerflow.config import get_app_config

            config = get_app_config()
            skills_path = config.skills.get_skills_path()
            container_path = config.skills.container_path

            # Only add mapping if skills directory exists
            if skills_path.exists():
                mappings[container_path] = str(skills_path)
        except Exception as e:
            # Log but don't fail if config loading fails
            logger.warning("Could not setup skills path mapping: %s", e, exc_info=True)

        return mappings

    def _build_extra_env(self) -> dict[str, str]:
        """Env vars merged into host bash. Includes config ``sandbox.environment`` and optional agent-browser auto-config."""
        try:
            cfg = get_app_config()
            merged = _resolve_sandbox_env_values(dict(cfg.sandbox.environment or {}))
        except Exception as e:
            logger.warning("Could not load sandbox.environment for LocalSandboxProvider: %s", e, exc_info=True)
            merged = {}
        try:
            config_path = Path(AppConfig.resolve_config_path())
            root = config_path.parent
            for candidate in (
                root / "config" / "agent-browser.json",
                root / "agent-browser.json",
            ):
                resolved = candidate.resolve()
                if resolved.is_file():
                    merged.setdefault("AGENT_BROWSER_CONFIG", str(resolved))
                    break
        except Exception as e:
            logger.debug("Skipping agent-browser.json auto-config: %s", e)
        return merged

    def acquire(self, thread_id: str | None = None) -> str:
        global _singleton
        if _singleton is None:
            _singleton = LocalSandbox(
                "local",
                path_mappings=self._path_mappings,
                extra_env=self._extra_env,
            )
        return _singleton.id

    def get(self, sandbox_id: str) -> Sandbox | None:
        if sandbox_id == "local":
            if _singleton is None:
                self.acquire()
            return _singleton
        return None

    def release(self, sandbox_id: str) -> None:
        # LocalSandbox uses singleton pattern - no cleanup needed.
        # Note: This method is intentionally not called by SandboxMiddleware
        # to allow sandbox reuse across multiple turns in a thread.
        # For Docker-based providers (e.g., AioSandboxProvider), cleanup
        # happens at application shutdown via the shutdown() method.
        pass
