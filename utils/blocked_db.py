import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'blocked.db')


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS blocked_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT NOT NULL,
        action TEXT NOT NULL,
        region TEXT NOT NULL,
        port INTEGER,
        protocol TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ip ON blocked_log(ip)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON blocked_log(timestamp)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_action ON blocked_log(action)')
    conn.commit()
    conn.close()


def init_db():
    _ensure_db()


def insert(ip, action, region, port=None, protocol=None):
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO blocked_log (ip, action, region, port, protocol) VALUES (?, ?, ?, ?, ?)',
        (ip, action, region, port, protocol)
    )
    conn.commit()
    conn.close()


def query(ip=None, action=None, region=None, limit=200, offset=0):
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conditions = []
    params = []
    if ip:
        conditions.append('ip LIKE ?')
        params.append(f'%{ip}%')
    if action:
        conditions.append('action = ?')
        params.append(action)
    if region:
        conditions.append('region = ?')
        params.append(region)
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    rows = conn.execute(
        f'SELECT id, ip, action, region, port, protocol, timestamp FROM blocked_log{where} ORDER BY id DESC LIMIT ? OFFSET ?',
        params + [limit, offset]
    ).fetchall()
    conn.close()
    return [
        {'id': r[0], 'ip': r[1], 'action': r[2], 'region': r[3], 'port': r[4], 'protocol': r[5], 'timestamp': r[6]}
        for r in rows
    ]


def stats():
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute('SELECT COUNT(*) FROM blocked_log').fetchone()[0]
    unique_ips = conn.execute('SELECT COUNT(DISTINCT ip) FROM blocked_log').fetchone()[0]
    today = datetime.utcnow().strftime('%Y-%m-%d')
    today_count = conn.execute(
        'SELECT COUNT(*) FROM blocked_log WHERE timestamp >= ?', (today,)
    ).fetchone()[0]
    conn.close()
    return {'total': total, 'unique_ips': unique_ips, 'today': today_count}


def clear():
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM blocked_log')
    conn.commit()
    conn.close()


def cleanup_old(days=60):
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn.execute('DELETE FROM blocked_log WHERE timestamp < ?', (cutoff,))
    conn.commit()
    conn.close()
