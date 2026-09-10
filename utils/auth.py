from flask_login import UserMixin
from models import User

class AuthUser(UserMixin):
    def __init__(self, user):
        self.id = user.id
        self.username = user.username

def load_user(user_id):
    user = User.query.get(int(user_id))
    return AuthUser(user) if user else None