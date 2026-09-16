#!/bin/bash
# VPS地域限速管理器 - 一键部署脚本 (ipset 方案)
# Web管理端口: 9999 (永久放行，不受限速影响)

set -e

echo "=== VPS地域限速管理器 部署脚本 ==="
echo "Web管理端口: 9999"
echo ""

echo "[1/8] 安装系统依赖..."
export DEBIAN_FRONTEND=noninteractive
apt update
apt install -y python3 python3-pip python3-venv ipset iptables-persistent curl

echo "[2/8] 创建项目目录..."
PROJECT_DIR="/opt/vps-speed-limiter"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

echo "[3/8] 安装Python依赖..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/8] 初始化数据库..."
# 可通过环境变量 ADMIN_PASSWORD 指定初始密码；未指定则随机生成（print 输出）
python init_db.py

if [ -n "$ADMIN_PASSWORD" ]; then
    echo "登录密码: 已通过环境变量设置"
else
    echo "登录密码: 见上方 init_db.py 打印的随机值，请立即保存并在登录后修改"
fi

echo "[5/8] 下载IP段数据并装载ipset..."
python -c "
from utils.ipdata import IPDataManager
from config import Config as AppConfig
IPDataManager.ensure_ipsets()
region_code = AppConfig.DEFAULT_CONFIG.get('allowed_region_code', '440000')
result = IPDataManager.update_all(region_code)
print('  全中国IP段: {} 条'.format(result['cn'][1]))
print('  放行地域({})IP段: {} 条'.format(region_code, result['allowed'][1]))
IPDataManager.load_all(region_code)
print('  ipset 装载完成')
"

echo "[6/8] 创建系统服务..."
cat > /etc/systemd/system/vps-speed-limiter.service << EOF
[Unit]
Description=VPS Speed Limiter Web UI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=$PROJECT_DIR/venv/bin/gunicorn -w 2 -b 0.0.0.0:9999 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 被拦截IP日志监听服务
cat > /etc/systemd/system/speed-limiter-log.service << EOF
[Unit]
Description=VPS Speed Limiter Log Watcher
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=$PROJECT_DIR/venv/bin/python3 utils/log_watcher.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vps-speed-limiter
systemctl start vps-speed-limiter
systemctl enable speed-limiter-log
systemctl start speed-limiter-log

echo "[7/8] 配置日志系统..."
# rsyslog: 将 iptables LOG (SPL_ 前缀) 写入独立日志文件
mkdir -p /var/log
cat > /etc/rsyslog.d/speed-limiter.conf << 'EOFLOG'
:msg, contains, "SPL_" /var/log/speed-limiter.log
& stop
EOFLOG
systemctl restart rsyslog 2>/dev/null || true

# logrotate: 每天轮转，保留60天
cat > /etc/logrotate.d/speed-limiter << 'EOFROTATE'
/var/log/speed-limiter.log {
    daily
    rotate 60
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
}
EOFROTATE

touch /var/log/speed-limiter.log
chmod 644 /var/log/speed-limiter.log

# 初始化被拦截IP数据库
cd $PROJECT_DIR && source venv/bin/activate
python -c "from utils import blocked_db; blocked_db.init_db()"

echo "[8/8] 启动自检..."
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9999/login || echo "000")
echo "本地访问 /login 状态码: $HTTP_CODE"
if [ "$HTTP_CODE" = "200" ]; then
    echo "服务已正常启动"
else
    echo "警告: 服务未正常响应，请运行 systemctl status vps-speed-limiter 查看日志"
fi

echo ""
echo "=== 部署完成 ==="
PUBLIC_IP=$(curl -4 -s ifconfig.me || curl -4 -s ipinfo.io/ip || echo "YOUR_VPS_IP")
echo "访问地址: http://${PUBLIC_IP}:9999"
echo "默认账号: admin"
echo "初始密码: 见上方 [4/8] 的输出（随机生成或环境变量 ADMIN_PASSWORD）"
echo ""
echo "重要提醒:"
echo "  1. 请立即登录后修改初始密码"
echo "  2. 9999 端口已永久放行，不受地域限速影响"
echo "  3. 请在界面中配置您的公网A/B IP和端口"
echo "  4. 地域判定基于 ipset (放行地域段 + 全中国段，数据源自纯真数据库，可在界面选择省份)"
echo ""
echo "服务管理命令:"
echo "  systemctl status vps-speed-limiter   # 查看Web UI状态"
echo "  systemctl restart vps-speed-limiter  # 重启Web UI"
echo "  systemctl status speed-limiter-log   # 查看日志监听状态"
echo "  systemctl restart speed-limiter-log  # 重启日志监听"
echo "  journalctl -u vps-speed-limiter -f   # 查看Web UI日志"