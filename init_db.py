import os
import secrets
from app import create_app, db
from models import User, Config
from config import Config as AppConfig
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    db.create_all()
    
    if not User.query.filter_by(username='admin').first():
        # 优先使用环境变量 ADMIN_PASSWORD；未设置则生成随机密码
        admin_password = os.environ.get('ADMIN_PASSWORD') or secrets.token_urlsafe(16)
        admin = User(
            username='admin',
            password_hash=generate_password_hash(admin_password)
        )
        db.session.add(admin)
        print(f"管理员已创建: admin")
        print(f"登录密码: {admin_password}")
        print("提示: 请登录后立即修改密码")
    
    if not Config.query.first():
        cfg = Config(**AppConfig.DEFAULT_CONFIG)
        db.session.add(cfg)
        print("默认配置已创建")
    
    db.session.commit()
    print("数据库初始化完成")