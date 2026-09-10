from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    public_ip_a = db.Column(db.String(45), nullable=False)
    public_ip_b = db.Column(db.String(45), nullable=False)
    reserved_ports = db.Column(db.String(255), nullable=False)
    ssh_port = db.Column(db.Integer, nullable=False, default=22)
    
    allowed_region_code = db.Column(db.String(10), nullable=False, default='440000')
    allowed_region_mode = db.Column(db.String(10), nullable=False, default='allow')
    allowed_region_limit_kbps = db.Column(db.Integer, nullable=False, default=100)
    other_cn_mode = db.Column(db.String(10), nullable=False, default='limit')
    other_cn_limit_kbps = db.Column(db.Integer, nullable=False, default=50)
    foreign_mode = db.Column(db.String(10), nullable=False, default='allow')
    foreign_limit_kbps = db.Column(db.Integer, nullable=False, default=0)
    burst_packets = db.Column(db.Integer, nullable=False, default=200)
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'public_ip_a': self.public_ip_a,
            'public_ip_b': self.public_ip_b,
            'reserved_ports': self.reserved_ports,
            'ssh_port': self.ssh_port,
            'allowed_region_code': self.allowed_region_code,
            'allowed_region_mode': self.allowed_region_mode,
            'allowed_region_limit_kbps': self.allowed_region_limit_kbps,
            'other_cn_mode': self.other_cn_mode,
            'other_cn_limit_kbps': self.other_cn_limit_kbps,
            'foreign_mode': self.foreign_mode,
            'foreign_limit_kbps': self.foreign_limit_kbps,
            'burst_packets': self.burst_packets,
        }

class Backup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rules_content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)