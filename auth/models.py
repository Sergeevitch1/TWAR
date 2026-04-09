# auth/models.py
from datetime import datetime
from extensions import db, login_manager
from flask_login import UserMixin

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    steam_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    username = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.String(255), nullable=True)

    # ==========================================
    # СИСТЕМА РАНГОВ И ФЛАГОВ
    # ==========================================
    role = db.Column(db.String(30), default='player', nullable=False)
    flags = db.Column(db.JSON, default=list)
    custom_title = db.Column(db.String(50), nullable=True)

    # ==========================================
    # НОВЫЕ ПОЛЯ ПРОФИЛЯ (для настроек)
    # ==========================================
    signature = db.Column(db.Text, nullable=True)
    game_nickname = db.Column(db.String(100), nullable=True)
    discord = db.Column(db.String(50), nullable=True)
    telegram = db.Column(db.String(50), nullable=True)

    # ==========================================
    # НАСТРОЙКИ ОФОРМЛЕНИЯ
    # ==========================================
    theme = db.Column(db.String(20), default='dark', nullable=False)
    timezone = db.Column(db.String(50), default='Europe/Moscow', nullable=False)
    language = db.Column(db.String(10), default='ru', nullable=False)

    # ==========================================
    # НАСТРОЙКИ ПРИВАТНОСТИ
    # ==========================================
    show_online_status = db.Column(db.Boolean, default=True)
    show_email = db.Column(db.Boolean, default=False)
    show_activity = db.Column(db.Boolean, default=True)
    allow_search_index = db.Column(db.Boolean, default=False)

    # ==========================================
    # НАСТРОЙКИ УВЕДОМЛЕНИЙ (EMAIL)
    # ==========================================
    email_new_reply = db.Column(db.Boolean, default=True)
    email_new_mention = db.Column(db.Boolean, default=True)
    email_private_message = db.Column(db.Boolean, default=True)

    # ==========================================
    # НАСТРОЙКИ УВЕДОМЛЕНИЙ (НА САЙТЕ)
    # ==========================================
    notify_new_reply = db.Column(db.Boolean, default=True)
    notify_new_like = db.Column(db.Boolean, default=True)
    notify_announcements = db.Column(db.Boolean, default=True)

    # ==========================================
    # МОДЕРАЦИЯ И СТАТУС
    # ==========================================
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    ban_reason = db.Column(db.String(255), nullable=True)
    ban_expires = db.Column(db.DateTime, nullable=True)

    # ==========================================
    # МЕТАДАННЫЕ
    # ==========================================
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ==========================================
    # ✅ МЕТОДЫ ПРОВЕРКИ ПРАВ (для админки)
    # ==========================================
    
    def is_admin(self):
        """Проверяет, есть ли у пользователя права администратора"""
        if self.role in ['owner', 's_owner', 'main_admin', 'admin']:
            return True
        if self.has_flag('admin') or self.has_flag('moderator'):
            return True
        return False
    
    def is_moderator(self):
        """Проверяет права модератора (включая админов)"""
        if self.is_admin():
            return True
        if self.has_flag('moderator'):
            return True
        return False
    
    def can_moderate(self):
        """Может ли пользователь модерировать контент"""
        if self.is_banned:
            return False
        return self.is_moderator()

    # ==========================================
    # ❤️ МЕТОДЫ РЕПУТАЦИИ И ЛАЙКОВ (НОВОЕ)
    # ==========================================

    def get_reputation(self):
        """Получить репутацию пользователя (сколько лайков набрали его посты)"""
        from forum.models import PostLike
        return PostLike.get_user_reputation(self.id)

    def is_popular_author(self):
        """Проверить, является ли пользователь популярным автором (100+ лайков)"""
        return self.get_reputation() >= 100

    def get_reputation_badge(self):
        """Вернуть бейдж репутации в зависимости от количества лайков"""
        rep = self.get_reputation()
        if rep >= 500:
            return {'name': '🌟 Легенда', 'color': '#ffd700', 'desc': '500+ лайков'}
        elif rep >= 200:
            return {'name': '🔥 Эксперт', 'color': '#ff6b6b', 'desc': '200+ лайков'}
        elif rep >= 100:
            return {'name': '⭐ Популярный', 'color': '#4ecdc4', 'desc': '100+ лайков'}
        elif rep >= 50:
            return {'name': '👍 Активный', 'color': '#95a5a6', 'desc': '50+ лайков'}
        elif rep > 0:
            return {'name': '🌱 Новичок', 'color': '#7f8c8d', 'desc': f'{rep} лайков'}
        return None

    # ==========================================
    # МЕТОДЫ ДЛЯ ФЛАГОВ
    # ==========================================

    def _ensure_flags(self):
        """Гарантирует, что flags — это список (защита от None)"""
        if self.flags is None or not isinstance(self.flags, list):
            self.flags = []

    def get_flags(self):
        """Безопасный возврат списка флагов"""
        self._ensure_flags()
        return self.flags

    def has_flag(self, flag_code):
        """Проверка наличия конкретного флага"""
        self._ensure_flags()
        return flag_code in self.flags

    def add_flag(self, flag_code):
        """Добавление флага (автоматически коммитит)"""
        self._ensure_flags()
        if flag_code not in self.flags:
            self.flags.append(flag_code)
            db.session.commit()

    def remove_flag(self, flag_code):
        """Удаление флага (автоматически коммитит)"""
        self._ensure_flags()
        if flag_code in self.flags:
            self.flags.remove(flag_code)
            db.session.commit()

    # ==========================================
    # ПРОВЕРКА ПРАВИЛ ДОСТУПА
    # ==========================================

    def can(self, permission):
        """
        Универсальная проверка прав.
        Работает в связке с core.roles.can_perform().
        OWNER имеет god_mode и проходит любую проверку.
        Забаненный пользователь теряет все права кроме чтения.
        """
        if self.is_banned and permission != 'read_forum':
            return False

        from core.roles import can_perform

        if self.role == 'owner':
            return True

        return can_perform(self.role, permission)

    def __repr__(self):
        return f'<User {self.steam_id} | {self.username} | {self.role}>'


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    if user:
        user._ensure_flags()
    return user