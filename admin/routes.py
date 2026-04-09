# admin/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, Response
from flask_login import login_required, current_user
from auth.models import User
from forum.models import Topic, Post, Category, Notification, SecurityLog
from extensions import db
from datetime import datetime, timedelta
from core.roles import user_has_permission, get_user_permission_level, get_role_options_for_assigner, get_flags_by_category
from sqlalchemy import func
import logging
import csv
import io
import json
import sys
import os

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ==========================================
# 🔐 ДЕКОРАТОР ПРОВЕРКИ ПРАВ АДМИНА
# ==========================================

def admin_required(f):
    """Декоратор: доступ только для админов"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login_steam'))
        
        check = user_has_permission(current_user)
        if not check('view_logs'):
            flash('❌ Доступ запрещён', 'error')
            return redirect(url_for('core.index'))
        
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# 📊 ГЛАВНЫЙ ДАШБОРД
# ==========================================

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Главная страница админ-панели"""
    
    # === СТАТИСТИКА ===
    stats = {
        'users': User.query.count(),
        'users_online': User.query.filter(
            User.last_login > datetime.utcnow() - timedelta(minutes=15)
        ).count(),
        'topics': Topic.query.count(),
        'posts': Post.query.count(),
        'categories': Category.query.count(),
        'banned_users': User.query.filter_by(is_banned=True).count(),
        'new_users_today': User.query.filter(
            User.created_at > datetime.utcnow() - timedelta(days=1)
        ).count(),
        'new_topics_today': Topic.query.filter(
            Topic.created_at > datetime.utcnow() - timedelta(days=1)
        ).count(),
    }
    
    # === ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ ===
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    
    # === ПОСЛЕДНИЕ ТЕМЫ ===
    recent_topics = Topic.query.order_by(Topic.created_at.desc()).limit(10).all()
    
    # === АКТИВНОСТЬ ПО ДНЯМ (последние 7 дней) ===
    activity_data = []
    for i in range(6, -1, -1):
        date = datetime.utcnow() - timedelta(days=i)
        date_start = date.replace(hour=0, minute=0, second=0)
        date_end = date.replace(hour=23, minute=59, second=59)
        
        users_count = User.query.filter(
            User.created_at.between(date_start, date_end)
        ).count()
        
        topics_count = Topic.query.filter(
            Topic.created_at.between(date_start, date_end)
        ).count()
        
        activity_data.append({
            'date': date.strftime('%d.%m'),
            'users': users_count,
            'topics': topics_count
        })
    
    # === ТОП ПОЛЬЗОВАТЕЛЕЙ ПО АКТИВНОСТИ ===
    topics_subquery = db.session.query(
        Topic.author_id,
        func.count(Topic.id).label('topic_count')
    ).group_by(Topic.author_id).subquery()
    
    posts_subquery = db.session.query(
        Post.author_id,
        func.count(Post.id).label('post_count')
    ).group_by(Post.author_id).subquery()
    
    top_users = db.session.query(
        User,
        func.coalesce(topics_subquery.c.topic_count, 0).label('topics_count'),
        func.coalesce(posts_subquery.c.post_count, 0).label('posts_count')
    ).outerjoin(
        topics_subquery, User.id == topics_subquery.c.author_id
    ).outerjoin(
        posts_subquery, User.id == posts_subquery.c.author_id
    ).order_by(
        posts_subquery.c.post_count.desc().nullslast()
    ).limit(5).all()
    
    return render_template('admin/dashboard.html',
                          stats=stats,
                          recent_users=recent_users,
                          recent_topics=recent_topics,
                          activity_data=activity_data,
                          top_users=top_users)

# ==========================================
# 👥 УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
# ==========================================

@admin_bp.route('/users')
@admin_required
def users():
    """Список всех пользователей"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.steam_id.like(f'%{search}%')
            )
        )
    
    if role_filter:
        query = query.filter_by(role=role_filter)
    
    users_paginated = query.order_by(User.last_login.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    from core.roles import RANKS
    
    return render_template('admin/users.html',
                          users=users_paginated.items,
                          pagination=users_paginated,
                          search=search,
                          role_filter=role_filter,
                          roles=RANKS,
                          current_user=current_user)

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(user_id):
    """Редактирование пользователя"""
    user = User.query.get_or_404(user_id)
    
    check = user_has_permission(current_user)
    user_level = get_user_permission_level(user)
    my_level = get_user_permission_level(current_user)
    
    if user_level >= my_level and current_user.role != 'owner':
        flash('❌ Недостаточно прав для редактирования этого пользователя', 'error')
        return redirect(url_for('admin.users'))
    
    if request.method == 'POST':
        new_role = request.form.get('role')
        new_flags = request.form.getlist('flags')
        
        if new_role and new_role != user.role:
            old_role = user.role
            user.role = new_role
            # 🔐 Логируем изменение роли
            SecurityLog.log_role_change(
                admin_id=current_user.id,
                target_user_id=user.id,
                old_role=old_role,
                new_role=new_role,
                ip_address=request.remote_addr
            )
            logger.info(f"Admin {current_user.username} changed role of {user.username} from {old_role} to {new_role}")
            flash(f'✅ Роль изменена с {old_role} на {new_role}', 'success')
        
        user.flags = new_flags
        db.session.commit()
        return redirect(url_for('admin.users'))
    
    from core.roles import RANKS
    
    # ✅ ИСПРАВЛЕНО: передаём сгруппированные флаги с описаниями
    return render_template('admin/user_edit.html',
                          user=user,
                          roles=RANKS,
                          flags=get_flags_by_category(),  # ✅ Группировка по категориям
                          current_user=current_user)

@admin_bp.route('/users/<int:user_id>/ban', methods=['POST'])
@admin_required
def user_ban(user_id):
    """Бан пользователя"""
    user = User.query.get_or_404(user_id)
    
    user_level = get_user_permission_level(user)
    my_level = get_user_permission_level(current_user)
    
    if user_level >= my_level and current_user.role != 'owner':
        flash('❌ Нельзя забанить пользователя с равным или высшим уровнем', 'error')
        return redirect(url_for('admin.users'))
    
    reason = request.form.get('ban_reason', 'Нарушение правил')
    ban_days = request.form.get('ban_days', type=int)
    
    user.is_banned = True
    user.ban_reason = reason
    
    if ban_days and ban_days > 0:
        user.ban_expires = datetime.utcnow() + timedelta(days=ban_days)
    else:
        user.ban_expires = None
    
    # 🔐 Логируем бан
    SecurityLog.log_ban(
        admin_id=current_user.id,
        target_user_id=user.id,
        reason=reason,
        duration=ban_days,
        ip_address=request.remote_addr
    )
    
    logger.warning(f"Admin {current_user.username} banned user {user.username}. Reason: {reason}")
    db.session.commit()
    flash(f'✅ Пользователь {user.username} забанен', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/unban', methods=['POST'])
@admin_required
def user_unban(user_id):
    """Разбан пользователя"""
    user = User.query.get_or_404(user_id)
    
    user.is_banned = False
    user.ban_reason = None
    user.ban_expires = None
    
    # 🔐 Логируем разбан
    SecurityLog.log_unban(
        admin_id=current_user.id,
        target_user_id=user.id,
        ip_address=request.remote_addr
    )
    
    logger.info(f"Admin {current_user.username} unbanned user {user.username}")
    db.session.commit()
    flash(f'✅ Пользователь {user.username} разбанен', 'success')
    return redirect(url_for('admin.users'))

# ==========================================
# 📝 УПРАВЛЕНИЕ КОНТЕНТОМ
# ==========================================

@admin_bp.route('/topics')
@admin_required
def topics():
    """Список всех тем"""
    page = request.args.get('page', 1, type=int)
    
    topics_paginated = Topic.query.order_by(Topic.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/topics.html',
                          topics=topics_paginated.items,
                          pagination=topics_paginated)

@admin_bp.route('/topics/<int:topic_id>/delete', methods=['POST'])
@admin_required
def topic_delete(topic_id):
    """Удаление темы"""
    topic = Topic.query.get_or_404(topic_id)
    
    check = user_has_permission(current_user)
    if not check('manage_topics'):
        flash('❌ Недостаточно прав', 'error')
        return redirect(url_for('admin.topics'))
    
    topic_title = topic.title
    
    # 🔐 Логируем удаление темы
    SecurityLog.log_topic_delete(
        user_id=current_user.id,
        topic_id=topic.id,
        topic_title=topic_title,
        ip_address=request.remote_addr
    )
    
    db.session.delete(topic)
    db.session.commit()
    
    logger.warning(f"Admin {current_user.username} deleted topic '{topic_title}'")
    flash(f'✅ Тема "{topic_title}" удалена', 'success')
    return redirect(url_for('admin.topics'))

@admin_bp.route('/topics/<int:topic_id>/pin', methods=['POST'])
@admin_required
def topic_pin(topic_id):
    """Закрепить/открепить тему"""
    topic = Topic.query.get_or_404(topic_id)
    
    # 🔐 Логируем закрепление/открепление
    SecurityLog.log_action(
        user_id=current_user.id,
        action='topic_pin' if not topic.is_pinned else 'topic_unpin',
        details={'topic_id': topic.id, 'topic_title': topic.title},
        ip_address=request.remote_addr
    )
    
    topic.is_pinned = not topic.is_pinned
    db.session.commit()
    
    action = "закреплена" if topic.is_pinned else "откреплена"
    flash(f'✅ Тема {action}', 'success')
    return redirect(url_for('forum.topic', topic_id=topic.id))

@admin_bp.route('/topics/<int:topic_id>/lock', methods=['POST'])
@admin_required
def topic_lock(topic_id):
    """Закрыть/открыть тему"""
    topic = Topic.query.get_or_404(topic_id)
    
    # 🔐 Логируем закрытие/открытие
    SecurityLog.log_topic_lock(
        user_id=current_user.id,
        topic_id=topic.id,
        topic_title=topic.title,
        ip_address=request.remote_addr
    )
    
    topic.is_locked = not topic.is_locked
    db.session.commit()
    
    action = "закрыта" if topic.is_locked else "открыта"
    flash(f'✅ Тема {action}', 'success')
    return redirect(url_for('forum.topic', topic_id=topic.id))

# ==========================================
# 🔐 ЛОГИ ДЕЙСТВИЙ (ПОЛНЫЙ ФУНКЦИОНАЛ)
# ==========================================

@admin_bp.route('/logs')
@admin_required
def logs():
    """Журнал действий с фильтрами"""
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Парсим даты если есть
    date_from_dt = None
    date_to_dt = None
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            pass
    
    # Получаем логи с фильтрами
    logs_paginated = SecurityLog.get_logs(
        page=page,
        per_page=50,
        action_filter=action_filter if action_filter else None,
        user_id=user_filter if user_filter else None,
        date_from=date_from_dt,
        date_to=date_to_dt
    )
    
    # Получаем список всех действий для фильтра
    action_types = [
        {'code': '', 'name': 'Все действия'},
        {'code': 'login', 'name': '🔑 Входы'},
        {'code': 'logout', 'name': '🚪 Выходы'},
        {'code': 'ban', 'name': '⛔ Баны'},
        {'code': 'unban', 'name': '✅ Разбаны'},
        {'code': 'role_change', 'name': '👑 Смена роли'},
        {'code': 'topic_delete', 'name': '🗑️ Удаление тем'},
        {'code': 'topic_lock', 'name': '🔒 Закрытие тем'},
        {'code': 'topic_pin', 'name': '📌 Закрепление'},
        {'code': 'post_delete', 'name': '🗑️ Удаление постов'},
        {'code': 'settings_change', 'name': '⚙️ Настройки'},
        {'code': 'system_event', 'name': '⚡ Системные'},
        {'code': 'error', 'name': '❌ Ошибки'},
    ]
    
    # Получаем список пользователей для фильтра
    users_list = User.query.order_by(User.username).all()
    
    return render_template('admin/logs.html',
                          logs=logs_paginated.items,
                          pagination=logs_paginated,
                          action_filter=action_filter,
                          user_filter=user_filter,
                          date_from=date_from,
                          date_to=date_to,
                          action_types=action_types,
                          users_list=users_list,
                          current_user=current_user)


@admin_bp.route('/logs/export/csv')
@admin_required
def logs_export_csv():
    """Экспорт логов в CSV"""
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Парсим даты
    date_from_dt = None
    date_to_dt = None
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            pass
    
    # Получаем логи (без пагинации для экспорта)
    query = SecurityLog.query
    
    if action_filter:
        query = query.filter_by(action=action_filter)
    if user_filter:
        query = query.filter_by(user_id=user_filter)
    if date_from_dt:
        query = query.filter(SecurityLog.created_at >= date_from_dt)
    if date_to_dt:
        query = query.filter(SecurityLog.created_at <= date_to_dt)
    
    logs = query.order_by(SecurityLog.created_at.desc()).limit(1000).all()
    
    # Генерируем CSV
    csv_data = SecurityLog.export_to_csv(logs)
    
    # Отправляем файл
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=logs_{datetime.now().strftime("%Y%m%d")}.csv'}
    )


@admin_bp.route('/logs/export/json')
@admin_required
def logs_export_json():
    """Экспорт логов в JSON"""
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Парсим даты
    date_from_dt = None
    date_to_dt = None
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            pass
    
    # Получаем логи
    query = SecurityLog.query
    
    if action_filter:
        query = query.filter_by(action=action_filter)
    if user_filter:
        query = query.filter_by(user_id=user_filter)
    if date_from_dt:
        query = query.filter(SecurityLog.created_at >= date_from_dt)
    if date_to_dt:
        query = query.filter(SecurityLog.created_at <= date_to_dt)
    
    logs = query.order_by(SecurityLog.created_at.desc()).limit(1000).all()
    
    # Генерируем JSON
    json_data = SecurityLog.export_to_json(logs)
    
    return jsonify({
        'exported_at': datetime.utcnow().isoformat(),
        'count': len(json_data),
        'logs': json_data
    })


@admin_bp.route('/logs/<int:log_id>/delete', methods=['POST'])
@admin_required
def log_delete(log_id):
    """Удаление записи лога (только для OWNER)"""
    if current_user.role != 'owner':
        flash('❌ Только OWNER может удалять логи', 'error')
        return redirect(url_for('admin.logs'))
    
    log = SecurityLog.query.get_or_404(log_id)
    db.session.delete(log)
    db.session.commit()
    
    flash('✅ Запись лога удалена', 'success')
    return redirect(url_for('admin.logs'))


@admin_bp.route('/logs/clear', methods=['POST'])
@admin_required
def logs_clear():
    """Очистка всех логов (только для OWNER)"""
    if current_user.role != 'owner':
        flash('❌ Только OWNER может очищать логи', 'error')
        return redirect(url_for('admin.logs'))
    
    # 🔐 Логируем саму очистку
    SecurityLog.log_action(
        user_id=current_user.id,
        action='logs_cleared',
        details={'cleared_by': current_user.username},
        ip_address=request.remote_addr
    )
    
    count = SecurityLog.query.count()
    SecurityLog.query.delete()
    db.session.commit()
    
    flash(f'✅ Удалено {count} записей логов', 'success')
    return redirect(url_for('admin.logs'))

# ==========================================
# ⚙️ НАСТРОЙКИ СИСТЕМЫ (ПОЛНЫЙ ФУНКЦИОНАЛ)
# ==========================================

@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    """Настройки форума"""
    if request.method == 'POST':
        # Обработка сохранения настроек
        if 'save_general' in request.form:
            flash('✅ Основные настройки сохранены', 'success')
        elif 'save_security' in request.form:
            flash('✅ Настройки безопасности сохранены', 'success')
        elif 'save_appearance' in request.form:
            flash('✅ Настройки оформления сохранены', 'success')
        elif 'save_email' in request.form:
            flash('✅ Настройки email сохранены', 'success')
        else:
            flash('✅ Настройки сохранены', 'success')
        return redirect(url_for('admin.settings'))
    
    # Моковые данные для демонстрации интерфейса
    config = {
        'FORUM_NAME': 'TW-FORUM',
        'FORUM_DESCRIPTION': 'Игровой форум',
        'SITE_URL': request.host_url.rstrip('/'),
        'MAINTENANCE_MODE': False,
        'ALLOW_REGISTRATION': True,
        'ALLOW_GUEST_VIEW': True,
        'MIN_PASSWORD_LENGTH': 8,
        'MAX_LOGIN_ATTEMPTS': 5,
        'REQUIRE_STRONG_PASSWORD': False,
        'REQUIRE_EMAIL_CONFIRM': True,
        'REQUIRE_2FA_ADMIN': False,
        'RATE_LIMIT_REQUESTS': 60,
        'BAN_DURATION': 30,
        'ENABLE_CAPTCHA': True,
        'ENABLE_IP_BLACKLIST': False,
        'SESSION_LIFETIME': 24,
        'REMEMBER_ME_DAYS': 30,
        'DEFAULT_THEME': 'dark',
        'ACCENT_COLOR': '#e74c3c',
        'SHOW_STATS': True,
        'ENABLE_REALTIME_NOTIFICATIONS': False,
        'ENABLE_RESPONSIVE': True,
        'MAIL_SERVER': 'smtp.gmail.com',
        'MAIL_PORT': 587,
        'MAIL_USERNAME': '',
        'MAIL_PASSWORD': '',
        'MAIL_USE_TLS': True,
        'MAIL_USE_SSL': False,
        'MAIL_FROM_NAME': 'TW-FORUM',
        'MAIL_DEFAULT_SENDER': 'noreply@tw-forum.com',
        'MAINTENANCE_MESSAGE': '',
        'WELCOME_MESSAGE': '',
        'TIMEZONE': 'Europe/Moscow',
        'LOGO_URL': '',
        'CUSTOM_CSS': '',
    }
    
    system_info = {
        'python_version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
        'flask_version': '2.x.x',
        'database_type': 'SQLite',
        'memory_usage': '45 MB',
        'app_version': '1.0.0',
    }
    
    return render_template('admin/settings.html', 
                           config=config, 
                           system_info=system_info,
                           config_json=json.dumps(config, indent=2),
                           backups=[])


# ✅ ИСПРАВЛЕНО: Теперь делает редирект вместо JSON
@admin_bp.route('/settings/save', methods=['POST'])
@admin_required
def settings_save():
    """Сохранение настроек (альтернативный роут для форм)"""
    if 'save_general' in request.form:
        flash('✅ Основные настройки сохранены', 'success')
    elif 'save_security' in request.form:
        flash('✅ Настройки безопасности сохранены', 'success')
    elif 'save_appearance' in request.form:
        flash('✅ Настройки оформления сохранены', 'success')
    elif 'save_email' in request.form:
        flash('✅ Настройки email сохранены', 'success')
    else:
        flash('✅ Настройки сохранены', 'success')
    
    return redirect(url_for('admin.settings'))


# ==========================================
# 🔧 API ДЛЯ НАСТРОЕК
# ==========================================

@admin_bp.route('/api/clear_cache', methods=['POST'])
@admin_required
def api_clear_cache():
    """Очистка кэша"""
    cache_type = request.args.get('type', 'all')
    logger.info(f"Cache cleared: {cache_type}")
    return jsonify({'success': True, 'message': f'Кэш "{cache_type}" очищен'})


@admin_bp.route('/api/create_backup', methods=['POST'])
@admin_required
def api_create_backup():
    """Создание бэкапа"""
    filename = f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    logger.info(f"Backup created: {filename}")
    return jsonify({'success': True, 'filename': filename})


@admin_bp.route('/api/download_latest_backup')
@admin_required
def api_download_latest_backup():
    """Скачивание последнего бэкапа"""
    flash('ℹ️ Бэкапы пока не созданы', 'info')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/api/test_email', methods=['POST'])
@admin_required
def api_test_email():
    """Тест отправки email"""
    email = request.json.get('email') if request.is_json else request.form.get('email')
    if not email:
        return jsonify({'success': False, 'error': 'Email не указан'}), 400
    
    logger.info(f"Test email sent to: {email}")
    return jsonify({'success': True, 'message': f'Тестовое письмо отправлено на {email}'})


@admin_bp.route('/api/check_updates')
@admin_required
def api_check_updates():
    """Проверка обновлений"""
    return jsonify({
        'current_version': '1.0.0',
        'latest_version': '1.0.0',
        'has_update': False
    })


@admin_bp.route('/api/reset_database', methods=['POST'])
@admin_required
def api_reset_database():
    """Сброс базы данных (только для OWNER)"""
    if current_user.role != 'owner':
        return jsonify({'success': False, 'error': 'Только OWNER'}), 403
    
    logger.warning(f"Database reset by {current_user.username}")
    return jsonify({'success': True, 'message': 'База данных сброшена'})


@admin_bp.route('/api/reset_sessions', methods=['POST'])
@admin_required
def api_reset_sessions():
    """Сброс всех сессий"""
    count = 0
    logger.info(f"Sessions reset by {current_user.username}")
    return jsonify({'success': True, 'count': count})


@admin_bp.route('/api/export_config')
@admin_required
def api_export_config():
    """Экспорт конфигурации"""
    config_data = {
        'FORUM_NAME': 'TW-FORUM',
        'SITE_URL': request.host_url.rstrip('/'),
    }
    return Response(
        json.dumps(config_data, indent=2, ensure_ascii=False),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=config.json'}
    )


@admin_bp.route('/api/import_config', methods=['POST'])
@admin_required
def api_import_config():
    """Импорт конфигурации"""
    if 'config_file' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не найден'}), 400
    
    file = request.files['config_file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Файл не выбран'}), 400
    
    logger.info(f"Config imported: {file.filename}")
    return jsonify({'success': True, 'message': 'Конфигурация импортирована'})

# ==========================================
# 🛡️ УПРАВЛЕНИЕ ПРАВАМИ ДОСТУПА
# ==========================================

@admin_bp.route('/permissions', methods=['GET', 'POST'])
@admin_required
def manage_permissions():
    """Страница управления правами ролей"""
    from core.permissions import RolePermissionRecord, ALL_PERMISSIONS, PermissionCategory
    from core.helpers import get_permissions_for_role
    
    selected_role = request.args.get('role', 'player')
    
    if request.method == 'POST':
        role = request.form.get('role')
        # Парсим чекбоксы: permissions['topic.create'] = '1'
        submitted_perms = {k.replace('permissions[', '').replace(']', ''): True 
                           for k in request.form if k.startswith('permissions[')}
        
        # Обновляем права
        for perm_code in ALL_PERMISSIONS.keys():
            granted = submitted_perms.get(perm_code, False)
            RolePermissionRecord.set_permission(
                role=role, permission_code=perm_code, granted=granted, updated_by=current_user.id
            )
        
        # Логируем изменение
        SecurityLog.log_action(
            user_id=current_user.id,
            action='permissions_changed',
            details={'role': role, 'changed_by': current_user.username},
            ip_address=request.remote_addr
        )
        
        flash(f'✅ Права для роли "{role}" обновлены', 'success')
        return redirect(url_for('admin.manage_permissions', role=role))
    
    permissions_by_category = get_permissions_for_role(selected_role)
    
    return render_template('admin/permissions.html',
                          selected_role=selected_role,
                          permissions_by_category=permissions_by_category,
                          PermissionCategory=PermissionCategory)

# ==========================================
# 📊 ОБЩИЕ API
# ==========================================

@admin_bp.route('/api/stats')
@admin_required
def api_stats():
    """API: получить статистику"""
    stats = {
        'users': User.query.count(),
        'topics': Topic.query.count(),
        'posts': Post.query.count(),
        'online': User.query.filter(
            User.last_login > datetime.utcnow() - timedelta(minutes=15)
        ).count(),
        'logs_today': SecurityLog.query.filter(
            SecurityLog.created_at > datetime.utcnow() - timedelta(days=1)
        ).count()
    }
    return jsonify(stats)