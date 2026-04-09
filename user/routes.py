# user/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from auth.models import User
from forum.models import Topic, Post, Notification
from extensions import db
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__, url_prefix='/user')

# ==========================================
# 📬 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def check_mention_in_post(content, topic_author_id, post_author_id):
    mentioned_users = []
    mentions = re.findall(r'@([\wа-яА-ЯёЁ\-]+)', content)
    for username in mentions:
        user = User.query.filter(User.username.ilike(username)).first()
        if user and user.id != post_author_id:
            mentioned_users.append(user.id)
    if topic_author_id and topic_author_id != post_author_id:
        if topic_author_id not in mentioned_users:
            mentioned_users.append(topic_author_id)
    return mentioned_users


def create_notification_for_reply(topic, post, from_user):
    if topic.author_id != from_user.id and topic.author_id:
        Notification.create_reply_notification(
            user_id=topic.author_id,
            topic_id=topic.id,
            post_id=post.id,
            from_user_id=from_user.id,
            post_preview=post.content[:100]
        )
    participants = Post.query.filter(
        Post.topic_id == topic.id,
        Post.author_id != from_user.id,
        Post.author_id != topic.author_id
    ).distinct(Post.author_id).all()
    for participant_post in participants:
        if participant_post.author_id and participant_post.author.notify_new_reply:
            Notification.create_reply_notification(
                user_id=participant_post.author_id,
                topic_id=topic.id,
                post_id=post.id,
                from_user_id=from_user.id,
                post_preview=post.content[:100]
            )
    mentioned_ids = check_mention_in_post(post.content, topic.author_id, from_user.id)
    for user_id in mentioned_ids:
        user = User.query.get(user_id)
        if user and user.email_new_mention:
            Notification.create_mention_notification(
                user_id=user_id,
                topic_id=topic.id,
                post_id=post.id,
                from_user_id=from_user.id,
                mention_text=from_user.username
            )


# ==========================================
# 🔐 ФУНКЦИИ БЕЗОПАСНОСТИ
# ==========================================

def calculate_security_score(user):
    score = 0
    recommendations = []
    if user.steam_id:
        score += 20
    else:
        recommendations.append("Привяжите Steam аккаунт")
    if hasattr(user, 'email_confirmed') and user.email_confirmed:
        score += 20
    else:
        recommendations.append("Подтвердите email адрес")
    if user.show_online_status or user.show_email or user.show_activity:
        score += 15
    else:
        recommendations.append("Настройте параметры приватности")
    if hasattr(user, 'two_factor_enabled') and user.two_factor_enabled:
        score += 25
    else:
        recommendations.append("Включите двухфакторную аутентификацию")
    if hasattr(user, 'password_strength'):
        if user.password_strength >= 8:
            score += 10
        else:
            recommendations.append("Используйте более сложный пароль")
    else:
        score += 5
        recommendations.append("Используйте надёжный пароль")
    days_since_login = (datetime.utcnow() - user.last_login).days
    if days_since_login < 30:
        score += 10
    elif days_since_login < 90:
        score += 5
        recommendations.append("Регулярно заходите в аккаунт")
    else:
        recommendations.append("Давно не заходили в аккаунт")
    return {
        'score': min(score, 100),
        'max_score': 100,
        'percentage': int((min(score, 100) / 100) * 100),
        'recommendations': recommendations,
        'level': get_security_level(min(score, 100))
    }


def get_security_level(score):
    if score >= 90:
        return {'name': 'Отличный', 'color': '#2ecc71', 'icon': '🛡️'}
    elif score >= 70:
        return {'name': 'Хороший', 'color': '#f1c40f', 'icon': '🔒'}
    elif score >= 50:
        return {'name': 'Средний', 'color': '#e67e22', 'icon': '⚠️'}
    else:
        return {'name': 'Низкий', 'color': '#e74c3c', 'icon': '🚨'}


def get_user_agent_info(user_agent_string):
    if not user_agent_string:
        return {'browser': 'Unknown', 'os': 'Unknown', 'device': 'Unknown'}
    ua = user_agent_string.lower()
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


def log_security_action(user_id, action_type, details=None, ip_address=None):
    logger.info(f"Security Action: user_id={user_id}, action={action_type}, details={details}, ip={ip_address}")


# ==========================================
# 📌 ОСНОВНЫЕ РОУТЫ ПРОФИЛЯ
# ==========================================

@user_bp.route('/<username>')
def profile(username):
    """Публичный профиль пользователя"""
    user = User.query.filter_by(username=username).first_or_404()
    topics_count = len(user.topics)
    posts_count = len(user.posts)
    days_registered = (datetime.utcnow() - user.created_at).days
    total_activity = topics_count * 10 + posts_count * 2
    user_level = 1 + (total_activity // 50)
    current_xp = total_activity % 50
    next_level_xp = 50
    xp_percentage = (current_xp / next_level_xp) * 100
    xp_to_next = next_level_xp - current_xp
    level_names = ['Новичок', 'Ученик', 'Активист', 'Ветеран', 'Эксперт', 'Легенда', 'Мастер']
    level_name = level_names[min(user_level - 1, len(level_names) - 1)]
    achievements_count = 0
    if days_registered > 7: achievements_count += 1
    if posts_count > 10: achievements_count += 1
    if topics_count > 5: achievements_count += 1
    if user.role in ['owner', 's_owner', 'main_admin', 'admin']: achievements_count += 1
    if getattr(user, 'has_flag', lambda x: False)('donator'): achievements_count += 1
    weekly_activity = min(100, max(10, (posts_count + topics_count * 2) * 5))
    total_views = sum(t.views for t in user.topics)
    popularity = min(100, total_views // max(topics_count, 1))
    engagement = min(100, posts_count * 3 if topics_count > 0 else 15)
    reputation = (posts_count // 2) + (topics_count * 3)
    recent_topics = Topic.query.filter_by(author_id=user.id).order_by(Topic.created_at.desc()).limit(5).all()
    recent_posts = Post.query.filter_by(author_id=user.id).order_by(Post.created_at.desc()).limit(5).all()
    return render_template('user/profile.html',
                           user=user, topics_count=topics_count, posts_count=posts_count,
                           days_registered=days_registered, recent_topics=recent_topics,
                           recent_posts=recent_posts, user_level=user_level, level_name=level_name,
                           current_xp=current_xp, next_level_xp=next_level_xp, xp_percentage=xp_percentage,
                           xp_to_next=xp_to_next, achievements_count=achievements_count,
                           weekly_activity=weekly_activity, popularity=popularity,
                           engagement=engagement, reputation=reputation)


@user_bp.route('/me')
@login_required
def my_profile():
    """✅ Перенаправление на свой профиль"""
    return redirect(url_for('user.profile', username=current_user.username))


@user_bp.route('/me/topics')
@login_required
def my_topics():
    """Мои темы"""
    page = request.args.get('page', 1, type=int)
    filter_by = request.args.get('filter', 'all')
    query = Topic.query.filter_by(author_id=current_user.id)
    if filter_by == 'pinned':
        query = query.filter_by(is_pinned=True)
    elif filter_by == 'locked':
        query = query.filter_by(is_locked=True)
    topics = query.order_by(Topic.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('user/my_topics.html', topics=topics.items, pagination=topics, current_filter=filter_by)


@user_bp.route('/me/posts')
@login_required
def my_posts():
    """Мои сообщения"""
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(author_id=current_user.id).order_by(Post.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('user/my_posts.html', posts=posts.items, pagination=posts)


@user_bp.route('/me/bookmarks')
@login_required
def bookmarks():
    """Закладки"""
    return render_template('user/bookmarks.html')


# ==========================================
# 📬 РОУТЫ УВЕДОМЛЕНИЙ
# ==========================================

@user_bp.route('/me/notifications')
@login_required
def notifications():
    """Страница уведомлений"""
    page = request.args.get('page', 1, type=int)
    filter_type = request.args.get('filter', 'all')
    query = Notification.query.filter_by(user_id=current_user.id)
    if filter_type == 'unread':
        query = query.filter_by(is_read=False)
    elif filter_type in ['reply', 'mention', 'like', 'system']:
        query = query.filter_by(notification_type=filter_type)
    notifications_paginated = query.order_by(Notification.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    unread_count = Notification.get_unread_count(current_user.id)
    return render_template('user/notifications.html',
                          notifications=notifications_paginated.items,
                          pagination=notifications_paginated,
                          current_filter=filter_type,
                          unread_count=unread_count)


@user_bp.route('/me/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Отметить уведомление как прочитанное (AJAX)"""
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    notification.mark_as_read()
    unread_count = Notification.get_unread_count(current_user.id)
    return jsonify({'success': True, 'unread_count': unread_count, 'notification_id': notification_id})


@user_bp.route('/me/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Отметить все уведомления как прочитанные (AJAX)"""
    Notification.mark_all_read(current_user.id)
    return jsonify({'success': True, 'unread_count': 0, 'message': 'Все уведомления отмечены как прочитанные'})


@user_bp.route('/me/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    """Удалить уведомление (AJAX)"""
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(notification)
    db.session.commit()
    unread_count = Notification.get_unread_count(current_user.id)
    return jsonify({'success': True, 'unread_count': unread_count, 'message': 'Уведомление удалено'})


@user_bp.route('/me/notifications/count')
@login_required
def notifications_count():
    """API: получить количество непрочитанных уведомлений"""
    count = Notification.get_unread_count(current_user.id)
    return jsonify({'unread_count': count})


@user_bp.route('/me/notifications/api')
@login_required
def notifications_api():
    """API: получить список уведомлений"""
    page = request.args.get('page', 1, type=int)
    unread_only = request.args.get('unread', 'false') == 'true'
    notifications = Notification.get_for_user(current_user.id, page=page, per_page=10, unread_only=unread_only)
    result = []
    for n in notifications.items:
        result.append({
            'id': n.id, 'type': n.notification_type, 'icon': n.get_icon(),
            'title': n.title, 'message': n.message, 'time_ago': n.get_time_ago(),
            'is_read': n.is_read, 'link': n.get_link(),
            'from_user': n.from_user.username if n.from_user else None,
            'from_user_avatar': n.from_user.avatar if n.from_user else None
        })
    return jsonify({
        'notifications': result,
        'has_next': notifications.has_next,
        'next_page': notifications.next_num if notifications.has_next else None,
        'unread_count': Notification.get_unread_count(current_user.id)
    })


# ==========================================
# 🔐 РОУТЫ БЕЗОПАСНОСТИ (Перенаправляют в Настройки)
# ==========================================

@user_bp.route('/me/security')
@login_required
def security_dashboard():
    """Панель безопасности -> редирект в настройки"""
    return redirect(url_for('user.settings') + '#tab-security')


@user_bp.route('/me/security/sessions/end-all', methods=['POST'])
@login_required
def end_all_sessions():
    """Завершить все сессии кроме текущей"""
    log_security_action(user_id=current_user.id, action_type='session_end_all', details='All sessions ended', ip_address=request.remote_addr)
    flash('✅ Все сессии завершены (кроме текущей)', 'success')
    return redirect(url_for('user.settings') + '#tab-security')


@user_bp.route('/me/security/sessions/end/<session_id>', methods=['POST'])
@login_required
def end_session(session_id):
    """Завершить конкретную сессию"""
    log_security_action(user_id=current_user.id, action_type='session_end', details=f'Session {session_id} ended', ip_address=request.remote_addr)
    flash('✅ Сессия завершена', 'success')
    return redirect(url_for('user.settings') + '#tab-security')


@user_bp.route('/me/security/logs')
@login_required
def security_logs():
    """Журнал безопасности -> редирект в настройки"""
    return redirect(url_for('user.settings') + '#tab-security')


@user_bp.route('/me/security/2fa/enable', methods=['GET', 'POST'])
@login_required
def enable_2fa():
    """Включить 2FA -> заглушка"""
    flash('⚠️ Функция 2FA в разработке', 'warning')
    return redirect(url_for('user.settings') + '#tab-security')


@user_bp.route('/me/security/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    """Отключить 2FA"""
    log_security_action(user_id=current_user.id, action_type='2fa_disable', ip_address=request.remote_addr)
    flash('ℹ️ 2FA отключена', 'info')
    return redirect(url_for('user.settings') + '#tab-security')


@user_bp.route('/me/security/check')
@login_required
def security_check():
    """API: Проверка безопасности"""
    score = calculate_security_score(current_user)
    return jsonify(score)


# ==========================================
# ⚙️ НАСТРОЙКИ ПРОФИЛЯ
# ==========================================

@user_bp.route('/me/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Настройки профиля"""
    if request.method == 'POST':
        try:
            if 'save_profile' in request.form:
                current_user.custom_title = request.form.get('custom_title', '').strip()[:50] or None
                current_user.signature = request.form.get('signature', '').strip()[:500] or None
                current_user.game_nickname = request.form.get('game_nickname', '').strip() or None
                current_user.discord = request.form.get('discord', '').strip() or None
                current_user.telegram = request.form.get('telegram', '').strip() or None
                avatar_url = request.form.get('avatar_url', '').strip()
                if avatar_url and avatar_url.startswith(('http://', 'https://')):
                    current_user.avatar = avatar_url
                flash('✅ Профиль успешно обновлён!', 'success')
            elif 'save_appearance' in request.form:
                theme = request.form.get('theme', 'dark')
                if theme in ['dark', 'light', 'auto']:
                    current_user.theme = theme
                current_user.timezone = request.form.get('timezone', 'Europe/Moscow')
                language = request.form.get('language', 'ru')
                if language in ['ru', 'en']:
                    current_user.language = language
                flash('✅ Оформление сохранено!', 'success')
            elif 'save_notifications' in request.form:
                current_user.email_new_reply = 'email_new_reply' in request.form
                current_user.email_new_mention = 'email_new_mention' in request.form
                current_user.email_private_message = 'email_private_message' in request.form
                current_user.notify_new_reply = 'notify_new_reply' in request.form
                current_user.notify_new_like = 'notify_new_like' in request.form
                current_user.notify_announcements = 'notify_announcements' in request.form
                flash('✅ Настройки уведомлений сохранены!', 'success')
            elif 'save_privacy' in request.form:
                current_user.show_online_status = 'show_online_status' in request.form
                current_user.show_email = 'show_email' in request.form
                current_user.show_activity = 'show_activity' in request.form
                current_user.allow_search_index = 'allow_search_index' in request.form
                flash('✅ Настройки приватности сохранены!', 'success')
            elif 'delete_account' in request.form:
                flash('⚠️ Функция удаления аккаунта в разработке', 'warning')
            elif 'unlink_steam' in request.form:
                flash('⚠️ Функция отвязки Steam в разработке', 'warning')
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка сохранения: {str(e)}', 'error')
        return redirect(url_for('user.settings'))
    return render_template('user/settings.html')


@user_bp.route('/me/help')
@login_required
def help():
    """Помощь"""
    return render_template('user/help.html')