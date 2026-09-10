# VPS 地域限速管理器

> © 2026 hotick · 基于 **CC BY-NC 4.0** 许可发布（禁止商业用途，详见 [LICENSE](LICENSE)）

基于 **ipset + 省份 IP 段** 的 Web 管理工具，用来对 3x-ui 等代理节点的入口端口按地域做「放行 / 拒绝 / 限速」控制。

同时适配 **单公网 IP** 与**双公网 IP** 的 VPS：双 IP 时一个做地域限速（公网A）、另一个完全放行（公网B）；单 IP 时按下文配置同样可用。

本手册适用多台 VPS：**每台独立部署、互不影响**。请逐台按「四、部署」执行，每台只需改各自的 IP 和端口。

---

## 一、项目简介

### 功能逻辑（重要，先看这个）

VPS 使用两个公网 IP：

| 公网IP | 作用 |
|--------|------|
| **公网A** | 地域限速目标：**预留端口完全放行**；**非预留端口**（3x-ui 入口节点所在端口）按地域规则处理 |
| **公网B** | 完全放行，不受任何限制 |

- **预留端口**（如 80,8080,443）和 SSH(22)、Web管理(9999) 一样，**公网A/B 都永久放行**，不受地域限制
- **非预留端口** 上的流量按地域判定：放行地域 / 其他国内 / 境外，各自可设「完全放行 / 拒绝访问 / 限速 KB/s」
- SSH 22 与 Web 管理 9999 永久放行，最高优先级

### 地域判定原理

用 ipset（内核哈希集合）装载两个 IP 段列表：

| 集合 | 内容 | 数据来源 |
|------|------|----------|
| `allowed_ips` | 用户选择的放行地域 IP 段（如广东 440000、北京 110000 等） | 见「七、数据源与许可」 |
| `cn_ips` | 全中国 IP 段 | 同上 |

- 匹配基于精确 IP 段，可精确到**省级**，比 GeoIP 国家匹配更细
- **无需编译任何内核模块**（ipset 是 Ubuntu 内核自带能力）
- 数据源实测：全国 **5645 条**、广东 **1949 条**、北京 **652 条** CIDR（2026-09 快照，可随时在界面更新）

### 功能清单

| 功能 | 说明 |
|------|------|
| 登录认证 | 单一管理员账号 admin，密码为部署时生成或环境变量指定（见「四、部署」） |
| 基础配置 | 公网A/B IP、预留开放端口（SSH 固定 22，见 5.1） |
| 地域规则 | 放行地域（用户选择省份）/ 其他国内 / 境外，各可选「完全放行 / 拒绝访问 / 限速 KB/s」 |
| 突发流量 | 令牌桶突发包数，建议 100-500 |
| IP 数据管理 | 下载/更新 全国+放行地域 IP 段，一键装载 ipset |
| 预览规则 | 生成 iptables 脚本，确认后再执行 |
| 应用规则 | 自动下载并装载数据 + 自动备份 + 执行 |
| 备份恢复 | 自动/手动备份，列表选择恢复 |
| 状态查看 | 实时查看 iptables 规则与 ipset 装载状态 |
| 修改密码 | 导航栏「改密」，支持修改管理员密码 |

---

## ⭐ 支持与捐赠

如果这个项目对你有帮助，欢迎打赏支持，后续会继续做更多实用工具。

| 支付宝 | 微信 |
|--------|------|
| <img src="static/img/Alipay-qr.jpg" width="180" alt="支付宝收款码"> | <img src="static/img/WeChat_Pay-qr.jpg" width="180" alt="微信收款码"> |

---

## 二、部署前提（逐台核对）

| 项目 | 要求 | 说明 |
|------|------|------|
| 操作系统 | Ubuntu 20.04 / 22.04 / 24.04（Debian 系亦可） | |
| 权限 | root | deploy.sh 需要 root |
| 公网 IP | **公网A**：地域限速（可填不存在的 IP，用于限制特定来源）。**公网B**：完全放行（填 VPS 的实际公网 IP）。 | 单 IP 的 VPS 只需填公网B 即可 |
| 云防火墙 | 放行 **22** 和 **9999** 入方向 | **云厂商安全组先于 iptables 生效**，iptables 拦不住安全组 |
| 网络 | VPS 能访问 `raw.githubusercontent.com` | 数据源；不通则用「七、数据源」的手动方案 |
| Python | 3.8+ | Ubuntu 自带 |

> ⚠️ **重要说明：公网A/公网B 填同一个 IP 时，公网B 的完全放行会先命中，地域限速不生效。**
> **单公网 IP 的 VPS**：公网B 填你的实际 IP（完全放行），公网A 随便填个不存在的 IP（不会被访问到）。这样整台 VPS 完全放行，不受限速影响；若要在单 IP 上做限速，需将公网A 填成实际 IP、公网B 清空并自行调整规则。

---

## 三、准备安装包（在本机执行一次）

每台 VPS 用同一个安装包，区别只在后面改配置。

```powershell
# Windows PowerShell
cd F:\AI\opencode
tar -czf vps-speed-limiter.tar.gz vps-speed-limiter
```

---

## 四、部署到一台 VPS（逐台执行）

### 步骤1：上传并解压

在**本机**上传（Windows 自带 scp）：

```powershell
scp F:\AI\opencode\vps-speed-limiter.tar.gz root@你的VPS地址:/root/
```

在 VPS 上：

```bash
cd /opt
tar -xzf /root/vps-speed-limiter.tar.gz
cd /opt/vps-speed-limiter
```

### 步骤2：修改本机默认配置（每台必做）

```bash
nano config.py
```

只需要改 `DEFAULT_CONFIG` 里的公网IP与预留端口（其余可留默认，登录 Web 后再调整）：

```python
DEFAULT_CONFIG = {
    'public_ip_a': '地域限速的公网IP',    # ← 地域限速目标（单IP的VPS随便填个不存在的）
    'public_ip_b': '你的VPS实际公网IP',   # ← 完全放行（必填正确）
    'reserved_ports': '80,8080,443',  # ← 必改，加上你实际跑的3x-ui端口
    ...
}
```

保存：`Ctrl+O` 回车，`Ctrl+X`。

### 步骤3：一键部署

```bash
chmod +x deploy.sh
./deploy.sh
```

脚本自动完成：
1. 安装系统依赖（python3、**ipset**、iptables-persistent、curl）
2. 建 Python 虚拟环境并装依赖
3. 初始化 SQLite 数据库（创建 admin 账号；密码为环境变量 `ADMIN_PASSWORD` 或随机生成并在终端打印）
4. **下载 全国+放行地域 IP 段并装载进 ipset**
5. 创建 systemd 服务并启动，本地自检 `/login`

> 如需指定初始密码，运行部署前先 `export ADMIN_PASSWORD=你的密码` 再执行 `./deploy.sh`。

### 步骤4：验证

```bash
systemctl status vps-speed-limiter     # 应为 active (running)
ss -tlnp | grep 9999                   # 应监听 0.0.0.0:9999

# ipset 数据
ipset -t list allowed_ips | grep -i entries  # 放行地域条目
ipset -t list cn_ips | grep -i entries       # 应约 5645

# 首次使用：登录前防火墙仍放行
iptables -L INPUT -n | head
```

### 步骤5：登录并应用规则

浏览器打开 `http://你的VPS地址:9999`（若防火墙只放行 22，请先放行 9999）。

1. 登录 `admin`（密码见部署时 [4/7] 的输出）
2. 核对「IP 地址数据」卡片：两个集合已装载、条目数正常
3. 核对「基础配置」公网A/B 与预留端口
4. 核对「地域规则」预期
5. 点「预览规则」→ 确认 → 点「应用规则」

> **规则是内存态，重启会丢**。确认规则正确后执行一次保存：
> ```bash
> netfilter-persistent save
> ```
> 之后若重启，iptables 与 ipset 都会清空，登录界面重新点一次「应用规则」即恢复（会自动重载数据+规则）。

---

## 五、界面操作说明

### 5.1 基础配置

| 字段 | 说明 |
|------|------|
| 公网A IP | 地域限速目标 |
| 公网B IP | 完全放行（填 VPS 实际 IP） |
| 预留开放端口 | 逗号分隔，如 `80,8080,443`；这些端口与 SSH 一样公网A/B 均完全放行，不受地域限制 |

> **SSH 端口固定为 22**（界面无输入框，前端提交时写死）。若你的 SSH 不是 22，需同时改 `config.py` 的 `ssh_port` 和 `templates/dashboard.html` 中 `getFormData()` 里的 `ssh_port`。

### 5.2 IP 地址数据

| 项 | 说明 |
|----|------|
| 全中国 IP 段 | `cn_ips.txt`，实测约 5645 条 |
| 放行地域 IP 段 | `allowed_ips.txt`（用户选择的省份，如广东 440000 约 1949 条、北京 110000 约 652 条） |
| 刷新状态 | 重读文件信息与装载状态 |
| 更新 IP 数据 | 重新下载两份并装载（建议每月一次） |

### 5.3 地域规则（针对公网A 的**非预留端口**）

| 区域 | 选项 | 默认 |
|------|------|------|
| 放行地域 | 完全放行 / 拒绝访问 / 限速KB/S | 完全放行 |
| 其他国内 | 完全放行 / 拒绝访问 / 限速KB/S | 拒绝访问 |
| 境外 | 完全放行 / 拒绝访问 / 限速KB/S | 完全放行 |
| 突发流量 | 突发包数 | 200（建议 100-500） |

### 5.4 操作按钮

| 按钮 | 功能 |
|------|------|
| 预览规则 | 只生成脚本展示，不执行 |
| 应用规则 | 下载并装载数据 → 备份当前规则 → 执行 |
| 备份 / 恢复 | iptables 规则备份与回滚 |
| 刷新状态 | 显示 INPUT 链规则 + ipset 状态 |

---

## 六、工作原理

### 6.1 规则逻辑（生成顺序）

```
1. 清空 INPUT 链和自定义链 SPEED_LIMIT
2. ESTABLISHED,RELATED 放行；lo 放行
3. ★ 9999 永久放行（最高优先级）
4. 公网B 全部放行
5. 公网A SSH(22) 放行
6. 公网A 预留端口 完全放行（和 SSH 一样，不受地域限制）
7. 公网A 其余流量（非预留端口，即 3x-ui 入口节点所在端口）→ 跳转 SPEED_LIMIT 链：
   SPEED_LIMIT 链内规则（每条只匹配一个 ipset，规避 nf_tables 多 --match-set 限制）：
   a. allowed_ips 命中（放行地域） → 完全放行 / 拒绝 / 限速
   b. cn_ips 命中（国内非放行地域）→ 完全放行 / 拒绝 / 限速
   c. 兜底（境外）               → 完全放行 / 拒绝 / 限速
   d. 限速模式：超限包 → DROP
8. 其他所有 → DROP
```

### 6.2 匹配顺序

`放行地域 → 放行`，之后命中 `cn_ips` 的必为非放行地域国内，最后 `! cn_ips` 即境外。空集合的风险：若装载失败而规则照常应用，全国会被当成境外（方向相反），所以**数据装载失败时应用会报错而非带病放行**。

### 6.3 限速机制

- `iptables limit` 令牌桶：`--limit N/second --limit-burst M`
- KB/s→pps 换算 `pps = KB/s × 1024 / 1000`（按平均包 1000B）
- 实际吞吐受浏览器并发/包大小影响，误差以实测为准

---

## 七、数据源与许可

### 下载地址

本项目**运行时从 metowolf/iplist 项目下载 IP 段列表**，不内置数据文件。双地址自动降级：先主源，失败切备用。均失败时界面报错、不写坏旧数据。

| 文件 | 主源 |
|------|------|
| 全中国 | `https://raw.githubusercontent.com/metowolf/iplist/master/data/country/CN.txt` |
| 放行地域 | `https://raw.githubusercontent.com/metowolf/iplist/master/data/cncity/{region_code}.txt` |

备用（CDN）：`https://metowolf.github.io/iplist/data/...`（同路径）。

### 许可说明（重要）

- **metowolf/iplist** 仓库**未声明明确 LICENSE**，其数据整理自 OpenIPDB、IPIP.net、纯真（CZ88）等免费 IP 库，属第三方整理的 IP 段列表。
- **纯真社区版 IP 库**：官方声明按 **CC BY-SA 4.0** 公开发布，要求使用方**展示纯真署名**以获得继续使用与更新的授权（如「IP地址位置数据由 纯真CZ88 提供支持」）。历史上老版本曾限制商业用途。
- 本项目**不打包、不分发任何第三方 IP 数据文件**，仅运行时从上游下载，故不会把数据带入 GitHub 仓库；但使用方应自行遵守上游数据源的许可要求（如保留署名）。

### 国外源不通（如 VPS 在中国大陆）时的手动方案

本机下载：

```powershell
# Windows PowerShell（以广东 440000 为例，其他省份替换行政区划代码）
curl.exe -o cn_ips.txt https://raw.githubusercontent.com/metowolf/iplist/master/data/country/CN.txt
curl.exe -o allowed_ips.txt https://raw.githubusercontent.com/metowolf/iplist/master/data/cncity/440000.txt
```

macOS/Linux：用 `curl -o ...` 或 `wget -O ...`。

手动上传到 VPS：

```bash
scp cn_ips.txt allowed_ips.txt root@你的VPS地址:/opt/vps-speed-limiter/data/
```

然后在 VPS 装载：

```bash
cd /opt/vps-speed-limiter
source venv/bin/activate
python -c "from utils.ipdata import IPDataManager; IPDataManager.load_all(); print('装载完成')"
```

> 手动方案可绕过部署脚本的下载步骤：先上传两个 txt，再 `./deploy.sh`。

---

## 八、常见问题

### Q1 手机用户被误判地域？
IP 库按归属地定位：目标省份卡在外地→判为放行地域（误放行）；外地卡在目标省份→判为外地（误限速）。建议放行地域设「完全放行」。

### Q2 规则被清空/重启丢失？
立即放行：
```bash
iptables -F INPUT
iptables -A INPUT -j ACCEPT
```
高可用：登录 →「应用规则」（自动重载+重装）→ `netfilter-persistent save`。

### Q3 如何自定义放行地域 IP 段？
编辑 `data/allowed_ips.txt`（每行 CIDR，`#` 注释），再「刷新状态」或命令 `IPDataManager.load_all()`。

### Q4 多台 VPS 如何管理？
每台独立。重复「四、部署」，每台只改各自 IP/端口。备份互不共享。

### Q5 部署脚本中途失败？
- `apt` 或 pip 阶段：国内镜像或云加速后重跑（`./deploy.sh` 幂等）。
- 数据下载失败：用「七、数据源」的手动方案先放好两个 txt 再重跑。

### Q6 如何卸载？

```bash
systemctl stop vps-speed-limiter && systemctl disable vps-speed-limiter
iptables -F INPUT; iptables -A INPUT -j ACCEPT
ipset destroy allowed_ips 2>/dev/null; ipset destroy cn_ips 2>/dev/null
netfilter-persistent save
rm -rf /opt/vps-speed-limiter /etc/systemd/system/vps-speed-limiter.service
systemctl daemon-reload
```

---

## 九、运维命令

```bash
systemctl status vps-speed-limiter    # 状态
journalctl -u vps-speed-limiter -f    # 日志
iptables -L INPUT -n --line-numbers -v
ipset -t list allowed_ips             # 放行地域段条目
ipset -t list cn_ips                  # 全国段条目
```

重置管理员密码（sqlite3 需先 `apt install -y sqlite3`）：

```bash
cd /opt/vps-speed-limiter
source venv/bin/activate
python -c "
from app import app, db
from models import User
from werkzeug.security import generate_password_hash
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    u.password_hash = generate_password_hash('新密码')
    db.session.commit()
    print('密码已修改')
"
```

---

## 十、安全建议

1. 首登改密码（导航栏「改密」）
2. 生产用 gunicorn（已默认），勿用 `python app.py`
3. **发布到 GitHub 前**：首次启动自动生成随机密钥并保存到 `data/secret_key`（该目录已被 gitignore，不会入库）；也可用环境变量 `SECRET_KEY` 覆盖。不要在公开仓库里提交 `data/`（含 app.db、数据文件、备份、密钥）、`venv/`、`__pycache__/`
4. 9999 只对管理员来源放行（云防火墙细化为你的 IP）
5. 定期「更新 IP 数据」（每月）
6. 规则应用后 `netfilter-persistent save`
7. 建议 HTTPS 前置（nginx 反代）

---

## 十一、回滚

```bash
systemctl stop vps-speed-limiter
iptables -F INPUT; iptables -A INPUT -j ACCEPT
netfilter-persistent save
```

确认 SSH 正常后，再按 Q6 卸载。

---

## 十二、技术栈

| 组件 | 版本 |
|------|------|
| Python / Flask | 3.8+ / 3.0.3 |
| Flask-SQLAlchemy / Flask-Login | 3.1.1 / 0.6.3 |
| SQLite | 内置 |
| Gunicorn | 22.0.0（4 worker，端口 9999） |
| ipset | 内核功能 + 命令行 |
| IP 数据 | 运行时下载（metowolf/iplist） |
| Bootstrap | 5.3.2 (CDN) |

---

## 十三、许可证

本项目基于 **CC BY-NC 4.0**（署名-非商业使用 4.0 国际）授权，详见 [LICENSE](LICENSE)。

- ✅ 允许：个人学习、研究、非商业使用、修改与分发（需署名并注明修改）
- ❌ **禁止商业用途**（含用于商业代理服务等盈利场景）
- ⚠️ **免责声明**：软件按现状提供，作者不对使用本软件造成的任何直接或间接损失承担责任

本工具涉及 iptables 防火墙规则，误用可能导致网络中断，请先在测试环境验证后再投入使用。