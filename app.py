import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config as AppConfig
from models import db, User, Config, Backup
from utils.iptables import IPTablesManager
from utils.ipdata import IPDataManager
from utils.auth import load_user
from utils import blocked_db


def create_app():
    app = Flask(__name__)
    app.config.from_object(AppConfig)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.user_loader(load_user)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()

            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('用户名或密码错误', 'error')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/')
    @login_required
    def dashboard():
        config = Config.query.first()
        return render_template('dashboard.html', config=config.to_dict() if config else AppConfig.DEFAULT_CONFIG, region_codes=AppConfig.REGION_CODES)

    @app.route('/api/config', methods=['GET', 'POST'])
    @login_required
    def api_config():
        config = Config.query.first()
        if not config:
            config = Config(**AppConfig.DEFAULT_CONFIG)
            db.session.add(config)

        if request.method == 'POST':
            data = request.get_json()
            for key in AppConfig.DEFAULT_CONFIG.keys():
                if key in data:
                    setattr(config, key, data[key])
            db.session.commit()
            return jsonify({'success': True, 'message': '配置已保存'})

        return jsonify(config.to_dict())

    @app.route('/api/preview', methods=['POST'])
    @login_required
    def api_preview():
        data = request.get_json()
        try:
            script = IPTablesManager.generate_rules(data)
            return jsonify({'success': True, 'script': script})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/api/apply', methods=['POST'])
    @login_required
    def api_apply():
        data = request.get_json()
        try:
            config = Config.query.first()
            if not config:
                config = Config(**AppConfig.DEFAULT_CONFIG)
                db.session.add(config)

            for key in AppConfig.DEFAULT_CONFIG.keys():
                if key in data:
                    setattr(config, key, data[key])
            db.session.commit()

            # 确保IP数据与当前选择的地域一致（重新下载+装载）
            region_code = data.get('allowed_region_code', config.allowed_region_code or '440000')
            IPDataManager.update_all(region_code)
            IPDataManager.load_all(region_code)

            success, msg, script = IPTablesManager.apply_rules(data)
            return jsonify({'success': success, 'message': msg, 'script': script})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/api/backup', methods=['POST'])
    @login_required
    def api_backup():
        try:
            data = request.get_json() or {}
            name = data.get('name')
            path = IPTablesManager.backup_rules(name)
            return jsonify({'success': True, 'message': f'备份成功: {os.path.basename(path)}'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/api/restore', methods=['POST'])
    @login_required
    def api_restore():
        try:
            data = request.get_json()
            filename = data.get('filename')
            if not filename:
                return jsonify({'success': False, 'message': '请指定备份文件'})
            IPTablesManager.restore_rules(filename[:-6])
            return jsonify({'success': True, 'message': '恢复成功'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/api/backups', methods=['GET'])
    @login_required
    def api_backups():
        backups = IPTablesManager.list_backups()
        return jsonify({'backups': backups})

    @app.route('/api/status', methods=['GET'])
    @login_required
    def api_status():
        try:
            rules = IPTablesManager.get_current_rules()
            ipdata = IPDataManager.get_status()
            return jsonify({
                'success': True,
                'rules': rules,
                'ipdata': ipdata
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/api/update_ipdata', methods=['POST'])
    @login_required
    def api_update_ipdata():
        try:
            data = request.get_json() or {}
            region_code = data.get('region_code', '440000')
            results = IPDataManager.update_all(region_code)
            # 重新装载 ipset
            IPDataManager.ensure_ipsets()
            IPDataManager.load_all(region_code)
            return jsonify({
                'success': True,
                'message': 'IP数据已更新',
                'counts': {
                    'cn': results['cn'][1] if results['cn'] else 0,
                    'allowed': results['allowed'][1] if results['allowed'] else 0
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/api/change_password', methods=['POST'])
    @login_required
    def api_change_password():
        data = request.get_json()
        old_pwd = data.get('old_password')
        new_pwd = data.get('new_password')

        user = User.query.get(current_user.id)
        if not check_password_hash(user.password_hash, old_pwd):
            return jsonify({'success': False, 'message': '原密码错误'})

        user.password_hash = generate_password_hash(new_pwd)
        db.session.commit()
        return jsonify({'success': True, 'message': '密码已修改'})

    @app.route('/api/blocked', methods=['GET'])
    @login_required
    def api_blocked():
        ip = request.args.get('ip')
        action = request.args.get('action')
        region = request.args.get('region')
        limit = min(int(request.args.get('limit', 200)), 1000)
        offset = int(request.args.get('offset', 0))
        rows = blocked_db.query(ip=ip, action=action, region=region, limit=limit, offset=offset)
        return jsonify({'success': True, 'records': rows})

    @app.route('/api/blocked/stats', methods=['GET'])
    @login_required
    def api_blocked_stats():
        s = blocked_db.stats()
        return jsonify({'success': True, 'stats': s})

    @app.route('/api/blocked/clear', methods=['POST'])
    @login_required
    def api_blocked_clear():
        blocked_db.clear()
        return jsonify({'success': True, 'message': '日志已清空'})

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9999, debug=False)