# forum/models.py
from datetime import datetime
from extensions import db
import json

class Category(db.Model):
    """Категория форума (раздел)"""
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    icon = db.Column(db.String(10), default='📌')
    color = db.Column(db.String(7), default='#4ecdc4')
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    topics = db.relationship('Topic', backref='category', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_stats(self):
        topic_count = self.topics.count()
        post_count = sum(topic.posts.count() for topic in self.topics)
        return {'topics': topic_count, 'posts': post_count}
    
    def get_last_post(self):
        last_topic = self.topics.order_by(Topic.last_post_at.desc()).first()
        if last_topic:
            return {
                'title': last_topic.title,
                'author': last_topic.author.username if last_topic.author else 'Unknown',
                'time': self._format_time(last_topic.last_post_at),
                'avatar': last_topic.author.avatar if last_topic.author else None
            }
        return None
    
    def _format_time(self, dt):
        if not dt:
            return 'никогда'
        diff = (datetime.utcnow() - dt).total_seconds()
        if diff < 60:
            return 'только что'
        elif diff < 3600:
            return f'{int(diff/60)} мин назад'
        elif diff < 86400:
            return f'{int(diff/3600)} ч назад'
        else:
            return f'{int(diff/86400)} дн назад'


class Topic(db.Model):
    """Тема (топик)"""
    __tablename__ = 'topics'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_post_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_pinned = db.Column(db.Boolean, default=False)
    is_locked = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    
    author = db.relationship('User', backref='topics')
    posts = db.relationship('Post', backref='topic', lazy='dynamic', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='topic', lazy='dynamic', cascade='all, delete-orphan')


class Post(db.Model):
    """Сообщение в теме"""
    __tablename__ = 'posts'
    
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_solution = db.Column(db.Boolean, default=False)
    
    author = db.relationship('User', backref='posts')
    notifications = db.relationship('Notification', backref='post', lazy='dynamic', cascade='all, delete-orphan')


class Notification(db.Model):
    """Система уведомлений пользователей"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    notification_type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    message = db.Column(db.Text, nullable=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    extra_data = db.Column(db.JSON, default=dict)
    
    user = db.relationship('User', backref='notifications', foreign_keys=[user_id])
    from_user = db.relationship('User', foreign_keys=[from_user_id])
    
    def mark_as_read(self):
        self.is_read = True
        db.session.commit()
    
    def get_icon(self):
        icons = {
            'reply': '💬', 'mention': '@', 'like': '❤️', 'quote': '📝',
            'pm': '✉️', 'system': '⚙️', 'admin': '👑'
        }
        return icons.get(self.notification_type, '🔔')
    
    def get_link(self):
        if self.topic_id and self.post_id:
            return f'/forum/topic/{self.topic_id}#post-{self.post_id}'
        elif self.topic_id:
            return f'/forum/topic/{self.topic_id}'
        elif self.from_user_id:
            return f'/user/{self.from_user.username}' if self.from_user else '#'
        return '#'
    
    def get_time_ago(self):
        if not self.created_at:
            return 'никогда'
        diff = (datetime.utcnow() - self.created_at).total_seconds()
        if diff < 60:
            return 'только что'
        elif diff < 3600:
            return f'{int(diff/60)} мин назад'
        elif diff < 86400:
            return f'{int(diff/3600)} ч назад'
        else:
            return f'{int(diff/86400)} дн назад'
    
    @staticmethod
    def create_reply_notification(user_id, topic_id, post_id, from_user_id, post_preview=''):
        notification = Notification(
            user_id=user_id, notification_type='reply', title='Новый ответ в теме',
            message=f'Кто-то ответил в теме, где вы участвуете: {post_preview[:100]}...',
            topic_id=topic_id, post_id=post_id, from_user_id=from_user_id,
            extra_data={'post_preview': post_preview[:200]}
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    
    @staticmethod
    def create_mention_notification(user_id, topic_id, post_id, from_user_id, mention_text=''):
        notification = Notification(
            user_id=user_id, notification_type='mention', title='Вас упомянули',
            message=f'@{mention_text} упомянул вас в обсуждении',
            topic_id=topic_id, post_id=post_id, from_user_id=from_user_id,
            extra_data={'mention_text': mention_text}
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    
    @staticmethod
    def create_like_notification(user_id, post_id, from_user_id):
        notification = Notification(
            user_id=user_id, notification_type='like', title='Ваш пост понравился',
            message='Кто-то оценил ваше сообщение', post_id=post_id, from_user_id=from_user_id
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    
    @staticmethod
    def create_system_notification(user_id, title, message, extra_data=None):
        notification = Notification(
            user_id=user_id, notification_type='system', title=title, message=message,
            extra_data=extra_data or {}
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    
    @staticmethod
    def mark_all_read(user_id):
        Notification.query.filter_by(user_id=user_id, is_read=False).update(
            {'is_read': True}, synchronize_session=False
        )
        db.session.commit()
    
    @staticmethod
    def get_unread_count(user_id):
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()
    
    @staticmethod
    def get_for_user(user_id, page=1, per_page=20, unread_only=False):
        query = Notification.query.filter_by(user_id=user_id)
        if unread_only:
            query = query.filter_by(is_read=False)
        return query.order_by(Notification.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    def __repr__(self):
        return f'<Notification {self.id} | {self.notification_type} | user:{self.user_id}>'


class SecurityLog(db.Model):
    """Система логирования действий"""
    __tablename__ = 'security_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    details = db.Column(db.JSON, default=dict)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', backref='security_logs')
    
    def get_action_icon(self):
        icons = {
            'login': '🔑', 'logout': '🚪', 'ban': '⛔', 'unban': '✅',
            'role_change': '👑', 'flag_change': '🏷️', 'topic_delete': '🗑️',
            'topic_lock': '🔒', 'topic_pin': '📌', 'post_delete': '🗑️',
            'settings_change': '⚙️', 'profile_edit': '✏️', 'system_event': '⚡', 'error': '❌'
        }
        return icons.get(self.action, '📋')
    
    def get_action_name(self):
        names = {
            'login': 'Вход в систему', 'logout': 'Выход из системы', 'ban': 'Бан пользователя',
            'unban': 'Разбан пользователя', 'role_change': 'Изменение роли',
            'flag_change': 'Изменение флага', 'topic_delete': 'Удаление темы',
            'topic_lock': 'Закрытие темы', 'topic_pin': 'Закрепление темы',
            'post_delete': 'Удаление сообщения', 'settings_change': 'Изменение настроек',
            'profile_edit': 'Редактирование профиля', 'system_event': 'Системное событие', 'error': 'Ошибка'
        }
        return names.get(self.action, self.action)
    
    def get_time_ago(self):
        if not self.created_at:
            return 'никогда'
        diff = (datetime.utcnow() - self.created_at).total_seconds()
        if diff < 60:
            return 'только что'
        elif diff < 3600:
            return f'{int(diff/60)} мин назад'
        elif diff < 86400:
            return f'{int(diff/3600)} ч назад'
        else:
            return f'{int(diff/86400)} дн назад'
    
    @staticmethod
    def log_action(user_id, action, details=None, ip_address=None, user_agent=None):
        log = SecurityLog(user_id=user_id, action=action, details=details or {},
                         ip_address=ip_address, user_agent=user_agent)
        db.session.add(log)
        db.session.commit()
        return log
    
    @staticmethod
    def log_login(user_id, ip_address=None, user_agent=None):
        return SecurityLog.log_action(user_id, 'login', {'status': 'success'}, ip_address, user_agent)
    
    @staticmethod
    def log_logout(user_id, ip_address=None):
        return SecurityLog.log_action(user_id, 'logout', ip_address=ip_address)
    
    @staticmethod
    def log_ban(admin_id, target_user_id, reason, duration=None, ip_address=None):
        return SecurityLog.log_action(admin_id, 'ban', {
            'target_user_id': target_user_id, 'reason': reason, 'duration_days': duration
        }, ip_address)
    
    @staticmethod
    def log_unban(admin_id, target_user_id, ip_address=None):
        return SecurityLog.log_action(admin_id, 'unban', {'target_user_id': target_user_id}, ip_address)
    
    @staticmethod
    def log_role_change(admin_id, target_user_id, old_role, new_role, ip_address=None):
        return SecurityLog.log_action(admin_id, 'role_change', {
            'target_user_id': target_user_id, 'old_role': old_role, 'new_role': new_role
        }, ip_address)
    
    @staticmethod
    def log_topic_delete(user_id, topic_id, topic_title, ip_address=None):
        return SecurityLog.log_action(user_id, 'topic_delete', {
            'topic_id': topic_id, 'topic_title': topic_title
        }, ip_address)
    
    @staticmethod
    def log_topic_lock(user_id, topic_id, topic_title, ip_address=None):
        return SecurityLog.log_action(user_id, 'topic_lock', {
            'topic_id': topic_id, 'topic_title': topic_title
        }, ip_address)
    
    @staticmethod
    def get_logs(page=1, per_page=50, action_filter=None, user_id=None, date_from=None, date_to=None):
        query = SecurityLog.query
        if action_filter:
            query = query.filter_by(action=action_filter)
        if user_id:
            query = query.filter_by(user_id=user_id)
        if date_from:
            query = query.filter(SecurityLog.created_at >= date_from)
        if date_to:
            query = query.filter(SecurityLog.created_at <= date_to)
        return query.order_by(SecurityLog.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    @staticmethod
    def get_user_actions(user_id, limit=100):
        return SecurityLog.query.filter_by(user_id=user_id)\
            .order_by(SecurityLog.created_at.desc()).limit(limit).all()
    
    @staticmethod
    def export_to_csv(logs):
        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Дата', 'Пользователь', 'Действие', 'IP', 'Детали'])
        for log in logs:
            writer.writerow([
                log.id, log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                log.user.username if log.user else 'System', log.action,
                log.ip_address or '-', str(log.details) if log.details else '-'
            ])
        return output.getvalue()
    
    @staticmethod
    def export_to_json(logs):
        result = []
        for log in logs:
            result.append({
                'id': log.id, 'created_at': log.created_at.isoformat(),
                'user': log.user.username if log.user else 'System',
                'user_id': log.user_id, 'action': log.action,
                'action_name': log.get_action_name(),
                'ip_address': log.ip_address, 'user_agent': log.user_agent,
                'details': log.details
            })
        return result
    
    def __repr__(self):
        return f'<SecurityLog {self.id} | {self.action} | user:{self.user_id}>'


class Setting(db.Model):
    """Хранит настройки форума в формате ключ-значение"""
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.JSON, nullable=True)
    value_type = db.Column(db.String(20), default='str')
    description = db.Column(db.String(255), nullable=True)
    group = db.Column(db.String(50), default='general', index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def get(key, default=None):
        setting = Setting.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set(key, value, value_type='str', description=None, group='general'):
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            setting.value_type = value_type
            if description:
                setting.description = description
            if group:
                setting.group = group
            setting.updated_at = datetime.utcnow()
        else:
            setting = Setting(key=key, value=value, value_type=value_type,
                            description=description, group=group)
            db.session.add(setting)
        db.session.commit()
        return setting
    
    @staticmethod
    def delete(key):
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            db.session.delete(setting)
            db.session.commit()
            return True
        return False
    
    @staticmethod
    def get_all(group=None):
        query = Setting.query
        if group:
            query = query.filter_by(group=group)
        return {s.key: s.value for s in query.all()}
    
    @staticmethod
    def get_group(group):
        return Setting.get_all(group)
    
    @staticmethod
    def bulk_set(settings_dict, group=None):
        for key, value in settings_dict.items():
            Setting.set(key, value, group=group)
        db.session.commit()
    
    @staticmethod
    def export_to_dict():
        settings = Setting.query.all()
        return {
            s.key: {
                'value': s.value, 'type': s.value_type,
                'description': s.description, 'group': s.group,
                'updated_at': s.updated_at.isoformat() if s.updated_at else None
            } for s in settings
        }
    
    @staticmethod
    def import_from_dict(data):
        for key, config in data.items():
            Setting.set(key=key, value=config.get('value'),
                       value_type=config.get('type', 'str'),
                       description=config.get('description'),
                       group=config.get('group', 'general'))
        db.session.commit()
    
    def __repr__(self):
        return f'<Setting {self.key}={self.value}>'


class TopicSubscription(db.Model):
    """Подписки пользователей на темы"""
    __tablename__ = 'topic_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'topic_id', name='_user_topic_uc'),)
    
    user = db.relationship('User', backref='topic_subscriptions')
    topic = db.relationship('Topic', backref='subscribers')
    
    @staticmethod
    def is_subscribed(user_id, topic_id):
        return TopicSubscription.query.filter_by(user_id=user_id, topic_id=topic_id).first() is not None
    
    @staticmethod
    def toggle_subscription(user_id, topic_id):
        existing = TopicSubscription.query.filter_by(user_id=user_id, topic_id=topic_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            return False
        else:
            sub = TopicSubscription(user_id=user_id, topic_id=topic_id)
            db.session.add(sub)
            db.session.commit()
            return True


class CategorySubscription(db.Model):
    """Подписки пользователей на разделы форума"""
    __tablename__ = 'category_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'category_id', name='_user_category_uc'),)
    
    user = db.relationship('User', backref='category_subscriptions')
    category = db.relationship('Category', backref='subscribers')
    
    @staticmethod
    def is_subscribed(user_id, category_id):
        return CategorySubscription.query.filter_by(user_id=user_id, category_id=category_id).first() is not None
    
    @staticmethod
    def subscribe(user_id, category_id):
        if not CategorySubscription.is_subscribed(user_id, category_id):
            sub = CategorySubscription(user_id=user_id, category_id=category_id)
            db.session.add(sub)
            db.session.commit()
            return True
        return False
    
    @staticmethod
    def unsubscribe(user_id, category_id):
        sub = CategorySubscription.query.filter_by(user_id=user_id, category_id=category_id).first()
        if sub:
            db.session.delete(sub)
            db.session.commit()
            return True
        return False
    
    @staticmethod
    def toggle_subscription(user_id, category_id):
        if CategorySubscription.is_subscribed(user_id, category_id):
            CategorySubscription.unsubscribe(user_id, category_id)
            return False
        else:
            CategorySubscription.subscribe(user_id, category_id)
            return True


# ==========================================
# ❤️ МОДЕЛЬ ЛАЙКОВ И РЕПУТАЦИИ (НОВОЕ)
# ==========================================

class PostLike(db.Model):
    """Лайки к постам"""
    __tablename__ = 'post_likes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Один пользователь может лайкнуть пост только один раз
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_like_uc'),)
    
    user = db.relationship('User', backref='given_likes')
    post = db.relationship('Post', backref='likes')
    
    @staticmethod
    def toggle_like(user_id, post_id):
        """Переключить лайк: если есть — убрать, если нет — добавить"""
        existing = PostLike.query.filter_by(user_id=user_id, post_id=post_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            return False, PostLike.get_like_count(post_id)
        else:
            like = PostLike(user_id=user_id, post_id=post_id)
            db.session.add(like)
            db.session.commit()
            return True, PostLike.get_like_count(post_id)
    
    @staticmethod
    def is_liked_by(user_id, post_id):
        """Проверить, лайкнул ли пользователь этот пост"""
        return PostLike.query.filter_by(user_id=user_id, post_id=post_id).first() is not None
    
    @staticmethod
    def get_like_count(post_id):
        """Получить количество лайков у поста"""
        return PostLike.query.filter_by(post_id=post_id).count()
    
    @staticmethod
    def get_user_reputation(user_id):
        """Получить репутацию пользователя (сколько лайков набрали его посты)"""
        return db.session.query(db.func.count(PostLike.id))\
            .join(Post, PostLike.post_id == Post.id)\
            .filter(Post.author_id == user_id)\
            .scalar() or 0
    
    @staticmethod
    def get_popular_authors(limit=10):
        """Получить топ авторов по репутации"""
        return db.session.query(
            User.id, User.username, User.avatar,
            db.func.count(PostLike.id).label('reputation')
        )\
        .join(Post, User.id == Post.author_id)\
        .join(PostLike, Post.id == PostLike.post_id)\
        .group_by(User.id)\
        .order_by(db.desc('reputation'))\
        .limit(limit)\
        .all()


# ==========================================
# 🔄 ИНИЦИАЛИЗАЦИЯ ДЕФОЛТНЫХ НАСТРОЕК
# ==========================================

def init_default_settings():
    """Создать настройки по умолчанию"""
    defaults = [
        ('forum_name', 'TW-FORUM', 'str', 'Название форума', 'general'),
        ('forum_description', 'Игровой форум', 'str', 'Описание для SEO', 'general'),
        ('site_url', '', 'str', 'Полный URL форума', 'general'),
        ('timezone', 'Europe/Moscow', 'str', 'Часовой пояс', 'general'),
        ('maintenance_mode', False, 'bool', 'Режим обслуживания', 'general'),
        ('maintenance_message', '', 'str', 'Сообщение в режиме обслуживания', 'general'),
        ('allow_registration', True, 'bool', 'Разрешить регистрацию', 'general'),
        ('allow_guest_view', True, 'bool', 'Просмотр без входа', 'general'),
        ('welcome_message', '', 'str', 'Приветственное сообщение', 'general'),
        ('min_password_length', 8, 'int', 'Мин. длина пароля', 'security'),
        ('max_login_attempts', 5, 'int', 'Макс. попыток входа', 'security'),
        ('require_strong_password', False, 'bool', 'Требовать сложный пароль', 'security'),
        ('require_email_confirm', True, 'bool', 'Подтверждение email', 'security'),
        ('require_2fa_admin', False, 'bool', '2FA для админов', 'security'),
        ('rate_limit_requests', 60, 'int', 'Лимит запросов/мин', 'security'),
        ('ban_duration', 30, 'int', 'Длительность бана (мин)', 'security'),
        ('enable_captcha', True, 'bool', 'Защита от ботов', 'security'),
        ('enable_ip_blacklist', False, 'bool', 'Чёрный список IP', 'security'),
        ('session_lifetime', 24, 'int', 'Время сессии (часы)', 'security'),
        ('remember_me_days', 30, 'int', '"Запомнить меня" (дни)', 'security'),
        ('default_theme', 'dark', 'str', 'Тема по умолчанию', 'appearance'),
        ('accent_color', '#e74c3c', 'str', 'Акцентный цвет', 'appearance'),
        ('logo_url', '', 'str', 'URL логотипа', 'appearance'),
        ('show_stats', True, 'bool', 'Показывать статистику', 'appearance'),
        ('enable_realtime_notifications', False, 'bool', 'Realtime уведомления', 'appearance'),
        ('enable_responsive', True, 'bool', 'Адаптивный дизайн', 'appearance'),
        ('custom_css', '', 'str', 'Пользовательский CSS', 'appearance'),
        ('mail_server', 'smtp.gmail.com', 'str', 'SMTP сервер', 'email'),
        ('mail_port', 587, 'int', 'SMTP порт', 'email'),
        ('mail_username', '', 'str', 'Email отправителя', 'email'),
        ('mail_password', '', 'str', 'Пароль/ключ', 'email'),
        ('mail_use_tls', True, 'bool', 'Использовать TLS', 'email'),
        ('mail_use_ssl', False, 'bool', 'Использовать SSL', 'email'),
        ('mail_from_name', 'TW-FORUM', 'str', 'Имя отправителя', 'email'),
        ('mail_default_sender', 'noreply@tw-forum.com', 'str', 'Email для отправки', 'email'),
    ]
    
    for key, default_value, value_type, description, group in defaults:
        if Setting.get(key) is None:
            Setting.set(key, default_value, value_type, description, group)
    
    db.session.commit()