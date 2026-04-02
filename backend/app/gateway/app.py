import asyncio
import logging
import os
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.gateway.config import get_gateway_config
from app.gateway.routers import (
    agents,
    artifacts,
    channels,
    mcp,
    memory,
    models,
    skills,
    suggestions,
    threads,
    uploads,
)
from deerflow.config.app_config import get_app_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# IM channels (Feishu, etc.) run on a dedicated thread with its own asyncio loop.
# Never use asyncio.run(start_channel_service()) there: asyncio.run() closes the loop when
# start() returns, which cancels ChannelManager._dispatch_loop and breaks inbound handling.
_channel_worker_thread: threading.Thread | None = None
_channel_worker_stop_event: threading.Event | None = None


def _channel_worker_main(stop_event: threading.Event) -> None:
    """Run ChannelService on a long-lived event loop (separate from Uvicorn)."""
    import asyncio as aio

    logger.info(
        "[feishu-worker] IM channel worker thread starting (pid=%s, thread=%s)",
        os.getpid(),
        threading.current_thread().name,
    )
    loop = aio.new_event_loop()
    aio.set_event_loop(loop)

    async def _runner() -> None:
        from app.channels.service import get_channel_service, start_channel_service, stop_channel_service

        await start_channel_service()
        svc = get_channel_service()
        logger.info("Channel service started: %s", svc.get_status() if svc else {})
        await aio.to_thread(stop_event.wait)
        await stop_channel_service()

    try:
        loop.run_until_complete(_runner())
    except Exception:
        logger.exception("Channel worker loop failed")
    finally:
        try:
            if not loop.is_closed():
                loop.close()
        except Exception:
            logger.exception("Error closing channel worker event loop")


def _spawn_channel_worker(stop_event: threading.Event) -> threading.Thread:
    t = threading.Thread(
        target=_channel_worker_main,
        args=(stop_event,),
        name="deerflow-channels",
        daemon=True,
    )
    t.start()
    return t


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""

    # Load config and check necessary environment variables at startup
    try:
        get_app_config()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        error_msg = f"Failed to load configuration during gateway startup: {e}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from e
    config = get_gateway_config()
    logger.info(f"Starting API Gateway on {config.host}:{config.port}")

    # NOTE: MCP tools initialization is NOT done here because:
    # 1. Gateway doesn't use MCP tools - they are used by Agents in the LangGraph Server
    # 2. Gateway and LangGraph Server are separate processes with independent caches
    # MCP tools are lazily initialized in LangGraph Server when first needed

    # IM channels can block the event loop for a long time (e.g. Feishu handshake). If we
    # asyncio.create_task() them and then yield, the task may run before Starlette sends
    # lifespan.startup.complete — blocking the loop and delaying listen(). Schedule the
    # task on the next loop iteration so startup.complete and uvicorn bind happen first.
    channel_task: asyncio.Task[None] | None = None
    global _channel_worker_thread, _channel_worker_stop_event
    try:

        async def _start_channels() -> None:
            global _channel_worker_thread, _channel_worker_stop_event
            try:
                _channel_worker_stop_event = threading.Event()
                _channel_worker_thread = await asyncio.to_thread(
                    _spawn_channel_worker,
                    _channel_worker_stop_event,
                )
            except Exception:
                logger.exception("No IM channels configured or channel service failed to start")

        loop = asyncio.get_running_loop()

        def _schedule_channel_start() -> None:
            nonlocal channel_task
            channel_task = asyncio.create_task(_start_channels())

        loop.call_soon(_schedule_channel_start)
    except Exception:
        logger.exception("Failed to schedule IM channel service startup")

    yield

    worker = _channel_worker_thread
    if _channel_worker_stop_event is not None:
        _channel_worker_stop_event.set()
    if worker is not None and worker.is_alive():

        def _join_worker() -> None:
            worker.join(timeout=60.0)

        await asyncio.to_thread(_join_worker)
    _channel_worker_thread = None
    _channel_worker_stop_event = None

    if channel_task is not None and not channel_task.done():
        channel_task.cancel()
        try:
            await channel_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutting down API Gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """

    app = FastAPI(
        title="DeerFlow API Gateway",
        description="""
## DeerFlow API Gateway

API Gateway for DeerFlow - A LangGraph-based AI agent backend with sandbox execution capabilities.

### Features

- **Models Management**: Query and retrieve available AI models
- **MCP Configuration**: Manage Model Context Protocol (MCP) server configurations
- **Memory Management**: Access and manage global memory data for personalized conversations
- **Skills Management**: Query and manage skills and their enabled status
- **Artifacts**: Access thread artifacts and generated files
- **Health Monitoring**: System health check endpoints

### Architecture

LangGraph requests are handled by nginx reverse proxy.
This gateway provides custom endpoints for models, MCP configuration, skills, and artifacts.
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "models",
                "description": "Operations for querying available AI models and their configurations",
            },
            {
                "name": "mcp",
                "description": "Manage Model Context Protocol (MCP) server configurations",
            },
            {
                "name": "memory",
                "description": "Access and manage global memory data for personalized conversations",
            },
            {
                "name": "skills",
                "description": "Manage skills and their configurations",
            },
            {
                "name": "artifacts",
                "description": "Access and download thread artifacts and generated files",
            },
            {
                "name": "uploads",
                "description": "Upload and manage user files for threads",
            },
            {
                "name": "threads",
                "description": "Manage DeerFlow thread-local filesystem data",
            },
            {
                "name": "agents",
                "description": "Create and manage custom agents with per-agent config and prompts",
            },
            {
                "name": "suggestions",
                "description": "Generate follow-up question suggestions for conversations",
            },
            {
                "name": "channels",
                "description": "Manage IM channel integrations (Feishu, Slack, Telegram)",
            },
            {
                "name": "health",
                "description": "Health check and system status endpoints",
            },
        ],
    )

    # CORS is handled by nginx - no need for FastAPI middleware

    # Include routers
    # Models API is mounted at /api/models
    app.include_router(models.router)

    # MCP API is mounted at /api/mcp
    app.include_router(mcp.router)

    # Memory API is mounted at /api/memory
    app.include_router(memory.router)

    # Skills API is mounted at /api/skills
    app.include_router(skills.router)

    # Artifacts API is mounted at /api/threads/{thread_id}/artifacts
    app.include_router(artifacts.router)

    # Uploads API is mounted at /api/threads/{thread_id}/uploads
    app.include_router(uploads.router)

    # Thread cleanup API is mounted at /api/threads/{thread_id}
    app.include_router(threads.router)

    # Agents API is mounted at /api/agents
    app.include_router(agents.router)

    # Suggestions API is mounted at /api/threads/{thread_id}/suggestions
    app.include_router(suggestions.router)

    # Channels API is mounted at /api/channels
    app.include_router(channels.router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint.

        Returns:
            Service health status information.
        """
        return {"status": "healthy", "service": "deer-flow-gateway"}

    return app


# Create app instance for uvicorn
app = create_app()
