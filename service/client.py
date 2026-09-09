"""Small synchronous client for the single MCP endpoint, including local control commands."""
import json
import time
import urllib.request
import urllib.error
from .config import read_config


class Client:
    def __init__(self, config=None):
        self.config = config or read_config()
        self.sequence = 0

    def rpc(self, method, params=None):
        self.sequence += 1
        body = {'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': params or {}}
        req = urllib.request.Request(f"http://127.0.0.1:{self.config['port']}/mcp",
                                     data=json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer '+self.config['token'],
                                              'Content-Type': 'application/json',
                                              'Accept': 'application/json, text/event-stream'})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.load(response)
        except urllib.error.URLError as exc:
            # Avoid leaking authenticated request headers through urllib's traceback locals.
            raise ConnectionError(f'Local MCP request failed: {exc.reason}') from None
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result['result']

    def call(self, name, **arguments):
        response = self.rpc('tools/call', {'name': name, 'arguments': arguments})
        if response.get('isError'):
            raise RuntimeError(response['content'])
        return response.get('structuredContent') or json.loads(response['content'][0]['text'])

    def wait(self, session, job, timeout=120):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            result = self.call('job_result', session=session, job=job)
            if result['status'] in ('completed', 'failed', 'cancelled', 'timed_out'):
                return result
            time.sleep(.05)
        raise TimeoutError(job)

    def run(self, session, operation, arguments, timeout=120):
        accepted = self.call('job_submit', session=session, operation=operation,
                             arguments=arguments, timeout_seconds=timeout)
        return self.wait(session, accepted['id'], timeout+30)
