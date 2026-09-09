"""Stdio forwarding adapter to the one running MCP service; never launches an engine."""
import json
import sys
from service.client import Client


def main():
    client = Client()
    for line in sys.stdin:
        message = None
        try:
            message = json.loads(line)
            if 'id' not in message:
                continue
            result = client.rpc(message['method'], message.get('params', {}))
            response = {'jsonrpc': '2.0', 'id': message['id'], 'result': result}
        except Exception as exc:
            response = {'jsonrpc': '2.0', 'id': message.get('id') if isinstance(message, dict) else None,
                        'error': {'code': -32603, 'message': str(exc)}}
        print(json.dumps(response), flush=True)


if __name__ == '__main__':
    main()
