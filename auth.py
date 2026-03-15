# ShortCraft - User Authentication

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin

db           = SQLAlchemy()
login_manager = LoginManager()

# ─── USER MODEL ───────────────────
class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    email    = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name     = db.Column(db.String(150), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
