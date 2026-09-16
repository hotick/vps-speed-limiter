import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

os.makedirs(BACKUP_DIR, exist_ok=True)


def _load_or_create_secret_key():
    """优先用环境变量；否则读取/生成持久化随机密钥，避免公开默认值与重启失效"""
    secret = os.environ.get('SECRET_KEY')
    if secret:
        return secret

    key_path = os.path.join(DATA_DIR, 'secret_key')
    if os.path.exists(key_path):
        with open(key_path, 'r', encoding='utf-8') as f:
            key = f.read().strip()
            if key:
                return key

    key = secrets.token_hex(32)
    with open(key_path, 'w', encoding='utf-8') as f:
        f.write(key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


class Config:
    SECRET_KEY = _load_or_create_secret_key()
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(DATA_DIR, "app.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEFAULT_CONFIG = {
        # 必须修改：填入你的两个公网IP
        'public_ip_a': '1.1.1.1',              # ← 公网A（限速目标）
        'public_ip_b': '8.8.8.8',              # ← 公网B（完全放行）

        # 按需修改：预留开放端口（逗号分隔）
        'reserved_ports': '80,8080,443',  # ← 加上你自己的端口

        # 按需修改：SSH端口
        'ssh_port': 22,                       # ← 如果改过SSH端口，改成实际值

        # 限速规则
        'allowed_region_code': '440000',      # ← 放行地域码（默认广东 440000，北京 110000 等）
        'allowed_region_mode': 'allow',       # 放行地域：allow=完全放行, limit=限速, block=拒绝
        'allowed_region_limit_kbps': 100,
        'other_cn_mode': 'block',             # 其他国内（不在放行地域内）：block=拒绝
        'other_cn_limit_kbps': 50,
        'foreign_mode': 'allow',              # 境外：allow=完全放行
        'foreign_limit_kbps': 0,
        'burst_packets': 200,
    }

    WEB_MANAGE_PORT = 9999

    # 被拦截IP日志
    LOG_FILE = '/var/log/speed-limiter.log'
    BLOCKED_DB = os.path.join(DATA_DIR, 'blocked.db')
    LOG_RETENTION_DAYS = 60

    # ipset 集合名
    IPSET_ALLOWED = 'allowed_ips'   # 配置的放行地域
    IPSET_CN = 'cn_ips'             # 全中国

    # 数据文件（位于 data/ 目录下）
    ALLOWED_IP_FILE = 'allowed_ips.txt'
    CN_IP_FILE = 'cn_ips.txt'

    # 数据源（metowolf/iplist，基于纯真数据库）
    # 主源: raw.githubusercontent.com（境外可直连）
    # 备源: metowolf.github.io CDN
    CN_IP_URL = 'https://raw.githubusercontent.com/metowolf/iplist/master/data/country/CN.txt'
    CN_IP_URL_ALT = 'https://metowolf.github.io/iplist/data/country/CN.txt'
    # 放行地域下载模板 {code} -> 省份编码
    ALLOWED_IP_URL = 'https://raw.githubusercontent.com/metowolf/iplist/master/data/cncity/{code}.txt'
    ALLOWED_IP_URL_ALT = 'https://metowolf.github.io/iplist/data/cncity/{code}.txt'

    # 区域码映射（用于界面显示）
    REGION_CODES = {
        '440000': '广东',
        '110000': '北京',
        '120000': '天津',
        '310000': '上海',
        '500000': '重庆',
        '130000': '河北',
        '140000': '山西',
        '150000': '内蒙古',
        '210000': '辽宁',
        '220000': '吉林',
        '230000': '黑龙江',
        '320000': '江苏',
        '330000': '浙江',
        '340000': '安徽',
        '350000': '福建',
        '360000': '江西',
        '370000': '山东',
        '410000': '河南',
        '420000': '湖北',
        '430000': '湖南',
        '450000': '广西',
        '460000': '海南',
        '510000': '四川',
        '520000': '贵州',
        '530000': '云南',
        '540000': '西藏',
        '610000': '陕西',
        '620000': '甘肃',
        '630000': '青海',
        '640000': '宁夏',
        '650000': '新疆',
    }


# 模块级别名（供 utils 与脚本直接导入）
IPSET_ALLOWED = Config.IPSET_ALLOWED
IPSET_CN = Config.IPSET_CN
ALLOWED_IP_FILE = Config.ALLOWED_IP_FILE
CN_IP_FILE = Config.CN_IP_FILE
ALLOWED_IP_URL = Config.ALLOWED_IP_URL
ALLOWED_IP_URL_ALT = Config.ALLOWED_IP_URL_ALT
CN_IP_URL = Config.CN_IP_URL
CN_IP_URL_ALT = Config.CN_IP_URL_ALT
REGION_CODES = Config.REGION_CODES