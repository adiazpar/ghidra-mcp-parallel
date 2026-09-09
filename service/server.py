import asyncio
import contextlib
import hmac
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import time
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import uvicorn
from .config import ROOT, LOCAL, read_config
from .supervisor import Supervisor


class LocalAuth:
    def __init__(self, app, config):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            headers = dict(scope.get('headers', []))
            auth = headers.get(b'authorization', b'').decode('latin1')
            expected = 'Bearer ' + self.config['token']
            host = headers.get(b'host', b'').decode('latin1')
            length = headers.get(b'content-length', b'0')
            try:
                oversized = int(length) > 300000
            except ValueError:
                oversized = True
            if (not hmac.compare_digest(auth, expected) or b'origin' in headers or
                host != f"127.0.0.1:{self.config['port']}" or oversized):
                await send({'type': 'http.response.start', 'status': 403, 'headers': []})
                await send({'type': 'http.response.body', 'body': b'Request rejected'})
                return
            total = 0
            original_receive = receive
            async def bounded_receive():
                nonlocal total
                message = await original_receive()
                total += len(message.get('body', b''))
                if total > 300000:
                    raise ValueError('Request size limit exceeded')
                return message
            receive = bounded_receive
        await self.app(scope, receive, send)


def main():
    config = read_config()
    runtime = LOCAL / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.WARNING, force=True, handlers=[
        RotatingFileHandler(runtime / 'supervisor.log', maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')])
    ownership = open(runtime / 'supervisor.lock', 'a+b')
    ownership.seek(0)
    if os.name == 'nt':
        import msvcrt
        ownership.write(b'0')
        ownership.flush()
        ownership.seek(0)
        msvcrt.locking(ownership.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(ownership.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    supervisor = Supervisor(config)
    mcp = FastMCP('shared-ghidra', host=config['host'], port=config['port'],
                  stateless_http=True, json_response=True,
                  transport_security=TransportSecuritySettings(
                      enable_dns_rebinding_protection=True,
                      allowed_hosts=[f"127.0.0.1:{config['port']}"], allowed_origins=[]))

    @mcp.tool()
    def service_health() -> dict[str, Any]:
        """Owner, generation, queue, process memory, and recovery state."""
        return supervisor.health()

    @mcp.tool()
    def session_open(label: str = '') -> dict[str, Any]:
        """Open a lightweight analysis session. All sessions share program changes."""
        return supervisor.new_session(label)

    @mcp.tool()
    def session_close(session: str) -> dict[str, Any]:
        """Cancel this session's outstanding jobs and release retained output."""
        return supervisor.close_session(session)

    @mcp.tool()
    def job_submit(session: str, operation: str, arguments: dict, timeout_seconds: float = 60) -> dict[str, Any]:
        """Submit a bounded asynchronous job. Use capabilities to discover operations.

        Program jobs require arguments.program. Mutations additionally require
        expected_version from the last job's program identity. Edits save by default;
        save:false explicitly leaves changes volatile. Job timeout includes queue time.
        """
        return supervisor.submit(session, operation, arguments, timeout_seconds)

    @mcp.tool()
    def job_status(session: str, job: str) -> dict[str, Any]:
        """Inspect job state, revision and timing without fetching output."""
        return supervisor.get(session, job, False)

    @mcp.tool()
    def job_result(session: str, job: str) -> dict[str, Any]:
        """Fetch frozen output and evidence. Poll until a terminal state."""
        return supervisor.get(session, job, True)

    @mcp.tool()
    def job_cancel(session: str, job: str) -> dict[str, Any]:
        """Request cooperative cancellation. An uncooperative job can trigger engine recovery."""
        return supervisor.cancel(session, job)

    @mcp.tool()
    def engine_restart() -> dict[str, Any]:
        """Restart the shared engine, interrupting work and discarding unsaved changes.

        Recovery opens the last durable state; uncertain writes and scripts are never replayed.
        """
        supervisor.recover_async('Explicit engine restart')
        return {'recovery_requested': True}

    @mcp.tool()
    def service_stop() -> dict[str, Any]:
        """Stop this service and its owned engine. Save volatile programs before stopping."""
        threading.Timer(.25, lambda: setattr(server, 'should_exit', True)).start()
        return {'stopping': True}

    server = uvicorn.Server(uvicorn.Config(LocalAuth(mcp.streamable_http_app(), config),
                                           host=config['host'], port=config['port'],
                                           log_level='warning', limit_concurrency=64,
                                           timeout_graceful_shutdown=20))
    try:
        server.run()
    finally:
        supervisor.shutdown()
        ownership.close()


if __name__ == '__main__':
    main()
