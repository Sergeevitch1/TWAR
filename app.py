# app.py
import os
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, redirect, url_for, flash, render_template
from dotenv import load_dotenv
from config import Config
from extensions import db, login_manager

# Импортируем конфиги рангов и флагов (для шаблонов)
from core.roles import RANKS, FLAGS

# ✅ ИМПОРТЫ СИСТЕМЫ ПРАВ ДОСТУПА
from core.permissions import can, get_permission_info, ALL_PERMISSIONS, PermissionCategory, user_has_permission
from core.helpers import get_permission_categories, get_permissions_for_role

# Загружаем переменные из .env ПЕРЕД созданием приложения
load_dotenv()

def create_app():
    # Создаём экземпляр Flask
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # === FIX ДЛЯ WINDOWS: Гарантируем существование папки instance ===
    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    
    # Если БД не задана вручную — строим правильный путь к instance/forum.db
    if not app.config.get('SQLALCHEMY_DATABASE_URI') or 'sqlite:///' in app.config['SQLALCHEMY_DATABASE_URI']:
        db_path = instance_path / 'forum.db'
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    # ================================================================

    # === 🔐 ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ БЕЗОПАСНОСТИ ===
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        USE_X_SENDFILE=False
    )
    
    # Настройки для email (Flask-Mail)
    if os.environ.get('MAIL_USERNAME'):
        app.config.update(
            MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
            MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
            MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'True') == 'True',
            MAIL_USE_SSL=os.environ.get('MAIL_USE_SSL', 'False') == 'True',
            MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
            MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
            MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@tw-forum.com')
        )

    # Инициализируем расширения
    db.init_app(app)
    login_manager.init_app(app)
    
    # Настройка Flask-Login
    login_manager.login_view = 'auth.login_steam'
    login_manager.login_message = 'Для доступа необходимо войти через Steam.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'

    # === ✅ ПРОВЕРКА ПРАВ АДМИНА (для шаблонов) ===
    def is_admin(user):
        """Проверяет, есть ли у пользователя права админа"""
        if not user or not user.is_authenticated:
            return False
        if user.role in ['owner', 's_owner', 'main_admin', 'admin']:
            return True
        if hasattr(user, 'has_flag'):
            if user.has_flag('admin') or user.has_flag('moderator'):
                return True
        return False

    # === КОНТЕКСТ-ПРОЦЕССОР: Глобальные переменные для шаблонов ===
    @app.context_processor
    def inject_globals():
        """
        Делает datetime, timedelta, RANKS, FLAGS, Notification, Setting, permissions доступными во всех шаблонах.
        """
        # ✅ ИМПОРТИРУЕМ МОДЕЛИ (включая PostLike для лайков)
        from forum.models import Notification, Setting, CategorySubscription, TopicSubscription, PostLike
        from flask_login import current_user
        
        def get_unread_notifications():
            if current_user.is_authenticated:
                return Notification.get_unread_count(current_user.id)
            return 0
        
        def get_user_agent_info():
            if not request.user_agent:
                return {'browser': 'Unknown', 'os': 'Unknown', 'device': 'Unknown'}
            ua = request.user_agent.string.lower() if request.user_agent.string else ''
            if 'firefox' in ua:
                browser = 'Firefox'
            elif 'chrome' in ua and 'edg' not in ua:
                browser = 'Chrome'
            elif 'safari' in ua and 'chrome' not in ua:
                browser = 'Safari'
            elif 'edg' in ua:
                browser = 'Edge'
            elif 'opera' in ua or 'opr' in ua:
                browser = 'Opera'
            else:
                browser = 'Unknown'
            if 'windows' in ua:
                os_name = 'Windows'
            elif 'mac' in ua:
                os_name = 'macOS'
            elif 'linux' in ua:
                os_name = 'Linux'
            elif 'android' in ua:
                os_name = 'Android'
            elif 'iphone' in ua or 'ipad' in ua:
                os_name = 'iOS'
            else:
                os_name = 'Unknown'
            if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
                device = 'Mobile'
            elif 'tablet' in ua or 'ipad' in ua:
                device = 'Tablet'
            else:
                device = 'Desktop'
            return {'browser': browser, 'os': os_name, 'device': device}
        
        # ✅ ВОЗВРАЩАЕМ ВСЕ ПЕРЕМЕННЫЕ, ВКЛЮЧАЯ МОДЕЛЬ ЛАЙКОВ
        return dict(
            datetime=datetime, 
            timedelta=timedelta,
            RANKS=RANKS,
            FLAGS=FLAGS,
            Notification=Notification,
            Setting=Setting,
            get_unread_notifications=get_unread_notifications,
            get_user_agent_info=get_user_agent_info,
            is_admin=is_admin,
            
            # ✅ СИСТЕМА ПРАВ ДОСТУПА
            can=can,
            get_permission_info=get_permission_info,
            ALL_PERMISSIONS=ALL_PERMISSIONS,
            PermissionCategory=PermissionCategory,
            get_permission_categories=get_permission_categories,
            get_permissions_for_role=get_permissions_for_role,
            user_has_permission=user_has_permission,
            
            # ✅ МОДЕЛИ (теперь доступны во ВСЕХ шаблонах)
            CategorySubscription=CategorySubscription,
            TopicSubscription=TopicSubscription,
            PostLike=PostLike  # ✅ НОВОЕ: для проверки лайков в шаблонах
        )
    # ===============================================================

    # === ✅ ДЕКОРАТОР ДЛЯ ЗАЩИТЫ АДМИН-РОУТОВ ===
    def admin_required(f):
        """Декоратор: доступ только для админов"""
        from functools import wraps
        from flask_login import current_user
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not is_admin(current_user):
                flash('❌ Доступ запрещён', 'error')
                return redirect(url_for('core.index'))
            return f(*args, **kwargs)
        return decorated_function

    # === ОБРАБОТЧИК ОШИБОК 404/500 ===
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    # === РЕГИСТРАЦИЯ BLUEPRINTS (МОДУЛЕЙ) ===
    from core.routes import core_bp
    from auth.routes import auth_bp
    from forum.routes import forum_bp
    from user.routes import user_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(forum_bp)
    app.register_blueprint(user_bp)
    
    # ✅ РЕГИСТРАЦИЯ АДМИН-ПАНЕЛИ
    try:
        from admin.routes import admin_bp
        app.register_blueprint(admin_bp, url_prefix='/admin')
    except ImportError:
        pass
    # =======================================

    # === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
    with app.app_context():
        # Создаёт все таблицы, если их нет
        db.create_all()
        
        # Импортируем модели ПОСЛЕ db.create_all(), чтобы SQLAlchemy их увидел
        from auth import models as auth_models
        from forum import models as forum_models
        
        # ✅ ИНИЦИАЛИЗАЦИЯ НАСТРОЕК ПО УМОЛЧАНИЮ
        from forum.models import init_default_settings
        init_default_settings()
        
        # ✅ ИНИЦИАЛИЗАЦИЯ ПРАВ ДОСТУПА ПО УМОЛЧАНИЮ
        from core.permissions import RolePermissionRecord
        RolePermissionRecord.init_default_permissions()
    # ===================================

        return app

# 👇 ГЛОБАЛЬНО (для gunicorn)
app = create_app()

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.environ.get('FLASK_DEBUG', '0') == '1'
    )
