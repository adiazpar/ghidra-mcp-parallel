import time
from .client import Client


def wait_ready(timeout=120):
    deadline=time.monotonic()+timeout
    last_error=None
    while time.monotonic()<deadline:
        try:
            health=Client().call('service_health')
            if health['state']=='ready':
                return health
            last_error=health.get('last_error')
        except Exception as exc:
            last_error=str(exc)
        time.sleep(.2)
    raise RuntimeError(f'Service did not become ready; inspect .local/runtime logs: {last_error}')


if __name__=='__main__':
    h=wait_ready()
    print(f"Service ready: owner PID {h['engine_pid']}, workers {h['workers']}")
