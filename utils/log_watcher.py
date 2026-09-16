#!/usr/bin/env python3
import re
import time
import signal
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import blocked_db

LOG_FILE = '/var/log/speed-limiter.log'
POLL_INTERVAL = 2
CLEANUP_INTERVAL = 3600 * 12

PREFIX_MAP = {
    'SPL_BLOCK_AL': ('block', 'allowed'),
    'SPL_LIMIT_AL': ('limit', 'allowed'),
    'SPL_BLOCK_CN': ('block', 'cn'),
    'SPL_LIMIT_CN': ('limit', 'cn'),
    'SPL_BLOCK_FW': ('block', 'foreign'),
    'SPL_LIMIT_FW': ('limit', 'foreign'),
}

LINE_RE = re.compile(
    r'(?P<prefix>SPL_(?:BLOCK|LIMIT)_(?:AL|CN|FW)):.*?'
    r'SRC=(?P<src>\d+\.\d+\.\d+\.\d+).*?'
    r'(?:PROTO=(?P<proto>\S+))?.*?'
    r'(?:SPT=(?P<spt>\d+))?.*?'
    r'(?:DPT=(?P<dpt>\d+))?',
    re.DOTALL
)

_running = True


def _handle_signal(sig, frame):
    global _running
    _running = False


def tail_log(path):
    if not os.path.exists(path):
        open(path, 'a').close()
    f = open(path, 'r')
    f.seek(0, 2)
    inode = os.fstat(f.fileno()).st_ino
    while _running:
        line = f.readline()
        if line:
            yield line.strip()
        else:
            try:
                current_inode = os.stat(path).st_ino
                if current_inode != inode:
                    f.close()
                    f = open(path, 'r')
                    inode = current_inode
            except FileNotFoundError:
                pass
            time.sleep(POLL_INTERVAL)
    f.close()


def parse_line(line):
    m = LINE_RE.search(line)
    if not m:
        return None
    prefix = m.group('prefix')
    if prefix not in PREFIX_MAP:
        return None
    action, region = PREFIX_MAP[prefix]
    ip = m.group('src')
    proto = m.group('proto')
    dpt = m.group('dpt')
    port = int(dpt) if dpt and dpt.isdigit() else None
    return ip, action, region, port, proto


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    blocked_db.init_db()
    last_cleanup = time.time()

    for line in tail_log(LOG_FILE):
        parsed = parse_line(line)
        if parsed:
            ip, action, region, port, proto = parsed
            blocked_db.insert(ip, action, region, port, proto)

        now = time.time()
        if now - last_cleanup > CLEANUP_INTERVAL:
            blocked_db.cleanup_old(days=60)
            last_cleanup = now


if __name__ == '__main__':
    main()
