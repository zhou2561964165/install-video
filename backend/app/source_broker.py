"""python -m app.source_broker --socket /run/install-video-source/broker.sock"""
import argparse
import sys

from .config import settings
from .services import child_isolation
from .services.source_broker import Broker


def main(argv=None):
    parser = argparse.ArgumentParser(description='Isolated source metadata broker')
    parser.add_argument('--socket', required=True)
    parser.add_argument('--api-user', default='video-demo')
    args = parser.parse_args(argv)
    try:
        import pwd
        account = pwd.getpwnam(args.api_user)
        config = child_isolation.from_settings(settings)
        if config is None:
            raise ValueError
        Broker(config, api_uid=account.pw_uid, api_gid=account.pw_gid).serve(args.socket)
    except Exception:
        # Fixed code only; no URL, cookies, proxy, path or traceback in logs.
        print('source_broker_unavailable', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
