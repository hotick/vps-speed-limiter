import os
import subprocess
import urllib.request
from datetime import datetime

from config import DATA_DIR, IPSET_ALLOWED, IPSET_CN, ALLOWED_IP_FILE, CN_IP_FILE
from config import ALLOWED_IP_URL, ALLOWED_IP_URL_ALT, CN_IP_URL, CN_IP_URL_ALT

_SYSTEM_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


class IPDataManager:
    """IP 地址段数据下载与 ipset 装载管理"""

    @staticmethod
    def _run(cmd, stdin_data=None, check=True):
        try:
            env = os.environ.copy()
            env['PATH'] = _SYSTEM_PATH + ':' + env.get('PATH', '')
            result = subprocess.run(
                cmd, shell=True, input=stdin_data, capture_output=True,
                text=True, timeout=120, env=env
            )
            if check and result.returncode != 0:
                raise Exception(f"命令执行失败: {result.stderr}")
            return result
        except subprocess.TimeoutExpired:
            raise Exception("命令执行超时")

    # ---------- 数据下载 ----------

    @staticmethod
    def _download(url, dest_path):
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/8.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
        with open(dest_path, 'w', encoding='utf-8') as f:
            f.write(data)
        return data

    @staticmethod
    def download_cn():
        """下载全中国 IP 段（metowolf/iplist，基于纯真数据库）"""
        os.makedirs(DATA_DIR, exist_ok=True)
        dest = os.path.join(DATA_DIR, CN_IP_FILE)
        errors = []
        for url in [CN_IP_URL, CN_IP_URL_ALT]:
            try:
                IPDataManager._download(url, dest)
                count = IPDataManager.count_cidr(dest)
                if count == 0:
                    raise Exception("文件内容为空")
                return dest, count
            except Exception as e:
                errors.append(f"{url}: {e}")
        raise Exception("CN 数据下载失败: " + " | ".join(errors))

    @staticmethod
    def download_allowed_region(region_code):
        """下载指定地域 IP 段（metowolf/iplist，基于纯真数据库）"""
        os.makedirs(DATA_DIR, exist_ok=True)
        dest = os.path.join(DATA_DIR, ALLOWED_IP_FILE)
        url = ALLOWED_IP_URL.format(code=region_code)
        alt_url = ALLOWED_IP_URL_ALT.format(code=region_code)
        errors = []
        for url in [url, alt_url]:
            try:
                IPDataManager._download(url, dest)
                count = IPDataManager.count_cidr(dest)
                if count == 0:
                    raise Exception("文件内容为空")
                return dest, count
            except Exception as e:
                errors.append(f"{url}: {e}")
        raise Exception(f"地域 {region_code} 数据下载失败: " + " | ".join(errors))

    @staticmethod
    def update_all(region_code=None):
        """下载或更新所有 IP 段数据，返回统计"""
        results = {'cn': None, 'allowed': None}
        results['cn'] = IPDataManager.download_cn()
        results['allowed'] = IPDataManager.download_allowed_region(region_code or '440000')
        return results

    # ---------- 文件工具 ----------

    @staticmethod
    def count_cidr(filepath):
        """统计文本文件中的有效 CIDR 条目数"""
        if not os.path.exists(filepath):
            return 0
        count = 0
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    count += 1
        return count

    @staticmethod
    def file_info(name):
        """返回数据文件信息（存在性、条目数、修改时间）"""
        path = os.path.join(DATA_DIR, name)
        if not os.path.exists(path):
            return {'exists': False, 'count': 0, 'mtime': None}
        stat = os.stat(path)
        return {
            'exists': True,
            'count': IPDataManager.count_cidr(path),
            'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }

    # ---------- ipset 管理 ----------

    @staticmethod
    def ensure_ipsets():
        """确保 allowed_ips / cn_ips 存在（hash:net，幂等，不销毁已有集合）"""
        for name in (IPSET_ALLOWED, IPSET_CN):
            IPDataManager._run(
                f'ipset create {name} hash:net family inet -exist', check=False)

    @staticmethod
    def load_one_ipset(setname, filepath):
        """将 CIDR 文件装载进指定 ipset"""
        if not os.path.exists(filepath):
            raise Exception(f"IP数据文件不存在: {filepath}")
        lines = []
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    lines.append(line)
        if not lines:
            raise Exception(f"IP数据文件为空: {filepath}")

        session_path = os.path.join(DATA_DIR, f'{setname}.session')
        with open(session_path, 'w') as f:
            f.write(f'create {setname} hash:net family inet -exist\n')
            f.write(f'flush {setname}\n')
            for cidr in lines:
                f.write(f'add {setname} {cidr}\n')
        try:
            IPDataManager._run(f'ipset restore -exist < {session_path}')
        finally:
            os.unlink(session_path)
        return len(lines)

    @staticmethod
    def load_all(region_code=None):
        """装载所有 ipset"""
        IPDataManager.ensure_ipsets()
        cn_file = os.path.join(DATA_DIR, CN_IP_FILE)
        allowed_file = os.path.join(DATA_DIR, ALLOWED_IP_FILE)
        cn_count = IPDataManager.load_one_ipset(IPSET_CN, cn_file)
        allowed_count = IPDataManager.load_one_ipset(IPSET_ALLOWED, allowed_file)
        return {'cn_count': cn_count, 'allowed_count': allowed_count}

    @staticmethod
    def ensure_loaded(region_code=None):
        """确保数据文件存在且已装载（应用规则前调用）"""
        cn_file = os.path.join(DATA_DIR, CN_IP_FILE)
        allowed_file = os.path.join(DATA_DIR, ALLOWED_IP_FILE)
        missing = []
        if not os.path.exists(cn_file):
            missing.append('全中国IP段')
        if not os.path.exists(allowed_file):
            missing.append('放行地域IP段')
        if missing:
            IPDataManager.update_all(region_code)
        return IPDataManager.load_all(region_code)

    @staticmethod
    def get_status():
        """返回 ipset 与数据文件状态"""
        ipsets = {}
        for name in (IPSET_ALLOWED, IPSET_CN):
            result = IPDataManager._run(f'ipset list {name}', check=False)
            exists = result.returncode == 0
            count = 0
            if exists:
                for line in result.stdout.splitlines():
                    if line.strip().startswith('Number of entries:'):
                        try:
                            count = int(line.split(':')[1].strip())
                        except (IndexError, ValueError):
                            pass
            ipsets[name] = {'exists': exists, 'count': count}

        return {
            'ipsets': ipsets,
            'allowed_file': IPDataManager.file_info(ALLOWED_IP_FILE),
            'cn_file': IPDataManager.file_info(CN_IP_FILE),
        }