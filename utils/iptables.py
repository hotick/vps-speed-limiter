import subprocess
import os
import tempfile
from config import BACKUP_DIR, IPSET_ALLOWED, IPSET_CN
from datetime import datetime

_SYSTEM_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


class IPTablesManager:
    WEB_MANAGE_PORT = 9999

    @staticmethod
    def run_cmd(cmd, check=True):
        try:
            env = os.environ.copy()
            env['PATH'] = _SYSTEM_PATH + ':' + env.get('PATH', '')
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30, env=env
            )
            if check and result.returncode != 0:
                raise Exception(f"命令执行失败: {result.stderr}")
            return result
        except subprocess.TimeoutExpired:
            raise Exception("命令执行超时")

    @staticmethod
    def check_ipset_available():
        """检查 ipset 命令是否可用"""
        result = IPTablesManager.run_cmd("which ipset", check=False)
        return result.returncode == 0

    @staticmethod
    def parse_ports(port_str):
        if not port_str:
            return []
        return [int(p.strip()) for p in port_str.split(',') if p.strip().isdigit()]

    @staticmethod
    def get_current_rules():
        result = IPTablesManager.run_cmd("iptables -L INPUT -n --line-numbers -v", check=False)
        return result.stdout if result.returncode == 0 else "获取失败"

    @staticmethod
    def backup_rules(name=None):
        result = IPTablesManager.run_cmd("iptables-save", check=False)
        if result.returncode != 0:
            raise Exception("备份失败")

        if not name:
            name = f"auto-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        backup_path = f"{BACKUP_DIR}/{name}.rules"
        with open(backup_path, 'w') as f:
            f.write(result.stdout)
        return backup_path

    @staticmethod
    def restore_rules(backup_name):
        backup_path = f"{BACKUP_DIR}/{backup_name}.rules"
        result = IPTablesManager.run_cmd(f"iptables-restore < {backup_path}", check=False)
        if result.returncode != 0:
            raise Exception(f"恢复失败: {result.stderr}")
        return True

    @staticmethod
    def list_backups():
        backups = []
        for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if f.endswith('.rules'):
                path = os.path.join(BACKUP_DIR, f)
                stat = os.stat(path)
                backups.append({
                    'name': f[:-6],
                    'filename': f,
                    'size': stat.st_size,
                    'time': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        return backups

    @staticmethod
    def generate_rules(config):
        ports = IPTablesManager.parse_ports(config['reserved_ports'])
        if not ports:
            raise Exception("预留开放端口不能为空")

        port_list = ','.join(map(str, ports))
        ip_a = config['public_ip_a']
        ip_b = config['public_ip_b']
        ssh_port = config['ssh_port']
        burst = config['burst_packets']
        web_port = IPTablesManager.WEB_MANAGE_PORT

        def kbps_to_pps(kbps):
            return max(1, kbps * 1024 // 1000)

        allowed_pps = kbps_to_pps(config['allowed_region_limit_kbps'])
        other_cn_pps = kbps_to_pps(config['other_cn_limit_kbps'])
        foreign_pps = kbps_to_pps(config['foreign_limit_kbps'])

        rules = []
        rules.append("#!/bin/bash")
        rules.append("")
        rules.append("# 清空INPUT链和自定义链")
        rules.append("iptables -F INPUT")
        rules.append("iptables -N SPEED_LIMIT 2>/dev/null || true")
        rules.append("iptables -F SPEED_LIMIT")
        rules.append("")
        rules.append("# 基础规则")
        rules.append("iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT")
        rules.append("iptables -A INPUT -i lo -j ACCEPT")
        rules.append("")
        rules.append(f"# Web管理端口 {web_port} 永久放行（不受任何地域限制）")
        rules.append(f"iptables -A INPUT -p tcp --dport {web_port} -j ACCEPT")
        rules.append("")
        rules.append(f"# 公网B ({ip_b}) 完全放行")
        rules.append(f"iptables -A INPUT -d {ip_b} -j ACCEPT")
        rules.append("")
        rules.append(f"# 公网A ({ip_a}) SSH放行")
        rules.append(f"iptables -A INPUT -d {ip_a} -p tcp --dport {ssh_port} -j ACCEPT")
        rules.append("")
        rules.append(f"# 公网A ({ip_a}) 预留端口完全放行（和SSH一样，不受地域限制）: {port_list}")
        rules.append(f"iptables -A INPUT -d {ip_a} -p tcp -m multiport --dports {port_list} -j ACCEPT")
        rules.append("")
        rules.append(f"# 公网A ({ip_a}) 非预留端口（3x-ui入口节点所在端口）→ 地域判定链")
        rules.append(f"iptables -A INPUT -d {ip_a} -j SPEED_LIMIT")
        rules.append("")

        # === SPEED_LIMIT 链内规则（每条只匹配一个 set） ===
        rules.append("# --- SPEED_LIMIT 链开始 ---")
        rules.append("# LOG 前缀: SPL_BLOCK_*=拒绝, SPL_LIMIT_*=限速超限; *_AL=放行地域, *_CN=国内其它, *_FW=境外")

        # 放行地域 IP
        mode = config['allowed_region_mode']
        if mode == 'allow':
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_ALLOWED} src -j ACCEPT")
        elif mode == 'block':
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_ALLOWED} src "
                         f"-m limit --limit 10/minute --limit-burst 5 -j LOG --log-prefix \"SPL_BLOCK_AL: \"")
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_ALLOWED} src -j DROP")
        else:  # limit
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_ALLOWED} src "
                         f"-m limit --limit {allowed_pps}/second --limit-burst {burst} -j ACCEPT")
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_ALLOWED} src "
                         f"-m limit --limit 10/minute --limit-burst 5 -j LOG --log-prefix \"SPL_LIMIT_AL: \"")
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_ALLOWED} src -j DROP")

        # 国内 IP（cn_ips 匹配成功说明是国内，且不在 allowed_ips 中因为上面已放行）
        mode = config['other_cn_mode']
        if mode == 'allow':
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_CN} src -j ACCEPT")
        elif mode == 'block':
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_CN} src "
                         f"-m limit --limit 10/minute --limit-burst 5 -j LOG --log-prefix \"SPL_BLOCK_CN: \"")
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_CN} src -j DROP")
        else:  # limit
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_CN} src "
                         f"-m limit --limit {other_cn_pps}/second --limit-burst {burst} -j ACCEPT")
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_CN} src "
                         f"-m limit --limit 10/minute --limit-burst 5 -j LOG --log-prefix \"SPL_LIMIT_CN: \"")
            rules.append(f"iptables -A SPEED_LIMIT -m set --match-set {IPSET_CN} src -j DROP")

        # 境外 IP（非 cn_ips，走到这里说明既不是放行地域也不是国内）
        mode = config['foreign_mode']
        if mode == 'allow':
            rules.append(f"iptables -A SPEED_LIMIT -j ACCEPT")
        elif mode == 'block':
            rules.append(f"iptables -A SPEED_LIMIT "
                         f"-m limit --limit 10/minute --limit-burst 5 -j LOG --log-prefix \"SPL_BLOCK_FW: \"")
            rules.append(f"iptables -A SPEED_LIMIT -j DROP")
        else:  # limit
            rules.append(f"iptables -A SPEED_LIMIT "
                         f"-m limit --limit {foreign_pps}/second --limit-burst {burst} -j ACCEPT")
            rules.append(f"iptables -A SPEED_LIMIT "
                         f"-m limit --limit 10/minute --limit-burst 5 -j LOG --log-prefix \"SPL_LIMIT_FW: \"")
            rules.append(f"iptables -A SPEED_LIMIT -j DROP")

        rules.append("# --- SPEED_LIMIT 链结束 ---")
        rules.append("")
        rules.append("# 拒绝其他所有")
        rules.append("iptables -A INPUT -j DROP")

        return '\n'.join(rules)

    @staticmethod
    def apply_rules(config):
        from utils.ipdata import IPDataManager
        # 应用规则前确保 IP 数据已装载（使用配置的地域码）
        region_code = config.get('allowed_region_code', '440000')
        IPDataManager.ensure_loaded(region_code)

        script = IPTablesManager.generate_rules(config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            IPTablesManager.backup_rules()
            result = IPTablesManager.run_cmd(f"bash {script_path}")
            return True, "规则应用成功", script
        except Exception as e:
            return False, str(e), script
        finally:
            os.unlink(script_path)