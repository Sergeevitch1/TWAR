from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
def index():
    """Главная страница - лендинг"""
    # Если уже залогинен — можно сразу редиректить на форум (опционально)
    # if current_user.is_authenticated:
    #     return redirect(url_for('forum.index'))
    return render_template('core/index.html')