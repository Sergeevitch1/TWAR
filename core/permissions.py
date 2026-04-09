# core/permissions.py
from enum import Enum, auto
from typing import List, Dict, Optional, Union
from dataclasses import dataclass, field
from flask_login import current_user
from extensions import db
from datetime import datetime

class PermissionCategory(Enum):
    """Категории прав для группировки в админке"""
    FORUM = ("forum", "💬 Форум")
    TOPICS = ("topics", "📝 Темы")
    POSTS = ("posts", "💬 Сообщения")
    USERS = ("users", "👥 Пользователи")
    MODERATION = ("moderation", "⚖️ Модерация")
    ADMIN = ("admin", "⚙️ Администрирование")
    CONTENT = ("content", "📦 Контент")
    SYSTEM = ("system", "🔧 Система")

@dataclass
class Permission:
    """Описание одного права"""
    code: str
    name: str
    description: str
    category: PermissionCategory
    default_roles: List[str] = field(default_factory=list)
    dangerous: bool = False
    inheritable: bool = True

# ==========================================
# 📋 ПОЛНЫЙ СПИСОК ПРАВ
# ==========================================

ALL_PERMISSIONS: Dict[str, Permission] = {
    # === 💬 ФОРУМ ===
    'forum.view': Permission(
        code='forum.view', name='Просмотр форума',
        description='Может просматривать разделы и темы',
        category=PermissionCategory.FORUM,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'forum.create_category': Permission(
        code='forum.create_category', name='Создание разделов',
        description='Может создавать новые категории форума',
        category=PermissionCategory.FORUM,
        default_roles=['admin', 'owner'],
        dangerous=True, inheritable=False
    ),
    'forum.edit_category': Permission(
        code='forum.edit_category', name='Редактирование разделов',
        description='Может менять название, описание, иконку раздела',
        category=PermissionCategory.FORUM,
        default_roles=['admin', 'owner'], inheritable=False
    ),
    'forum.delete_category': Permission(
        code='forum.delete_category', name='Удаление разделов',
        description='Может удалять разделы (вместе с темами!)',
        category=PermissionCategory.FORUM,
        default_roles=['owner'], dangerous=True, inheritable=False
    ),
    
    # === 📝 ТЕМЫ ===
    'topic.create': Permission(
        code='topic.create', name='Создание тем',
        description='Может создавать новые темы в разрешённых разделах',
        category=PermissionCategory.TOPICS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'topic.create_in_announce': Permission(  # ✅ ПРАВО ДЛЯ ОБЪЯВЛЕНИЙ
        code='topic.create_in_announce', name='Публикация в Объявлениях',
        description='Может создавать темы в разделе "Объявления"',
        category=PermissionCategory.TOPICS,
        default_roles=['moderator', 'admin', 'owner'],  # 🔒 Только админы/модеры
        inheritable=False
    ),
    'topic.edit_own': Permission(
        code='topic.edit_own', name='Редактирование своих тем',
        description='Может менять заголовок и содержание своих тем',
        category=PermissionCategory.TOPICS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'topic.edit_any': Permission(
        code='topic.edit_any', name='Редактирование любых тем',
        description='Может редактировать темы других пользователей',
        category=PermissionCategory.TOPICS,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'topic.delete_own': Permission(
        code='topic.delete_own', name='Удаление своих тем',
        description='Может удалять свои темы (если нет ответов)',
        category=PermissionCategory.TOPICS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'topic.delete_any': Permission(
        code='topic.delete_any', name='Удаление любых тем',
        description='Может удалять любые темы',
        category=PermissionCategory.TOPICS,
        default_roles=['moderator', 'admin', 'owner'],
        dangerous=True, inheritable=False
    ),
    'topic.pin': Permission(
        code='topic.pin', name='Закрепление тем',
        description='Может закреплять/откреплять темы',
        category=PermissionCategory.TOPICS,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'topic.lock': Permission(
        code='topic.lock', name='Закрытие тем',
        description='Может закрывать/открывать темы для ответов',
        category=PermissionCategory.TOPICS,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'topic.move': Permission(
        code='topic.move', name='Перенос тем',
        description='Может переносить темы между разделами',
        category=PermissionCategory.TOPICS,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    
    # === 💬 СООБЩЕНИЯ ===
    'post.create': Permission(
        code='post.create', name='Ответы в темах',
        description='Может отвечать в темах',
        category=PermissionCategory.POSTS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'post.edit_own': Permission(
        code='post.edit_own', name='Редактирование своих постов',
        description='Может редактировать свои сообщения',
        category=PermissionCategory.POSTS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'post.edit_any': Permission(
        code='post.edit_any', name='Редактирование чужих постов',
        description='Может редактировать сообщения других',
        category=PermissionCategory.POSTS,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'post.delete_own': Permission(
        code='post.delete_own', name='Удаление своих постов',
        description='Может удалять свои сообщения',
        category=PermissionCategory.POSTS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'post.delete_any': Permission(
        code='post.delete_any', name='Удаление чужих постов',
        description='Может удалять любые сообщения',
        category=PermissionCategory.POSTS,
        default_roles=['moderator', 'admin', 'owner'],
        dangerous=True, inheritable=False
    ),
    'post.use_markdown': Permission(
        code='post.use_markdown', name='Markdown в постах',
        description='Может использовать Markdown-разметку',
        category=PermissionCategory.CONTENT,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'post.use_html': Permission(
        code='post.use_html', name='HTML в постах',
        description='Может использовать HTML (опасно!)',
        category=PermissionCategory.CONTENT,
        default_roles=['admin', 'owner'], dangerous=True, inheritable=False
    ),
    'post.upload_image': Permission(
        code='post.upload_image', name='Загрузка изображений',
        description='Может прикреплять картинки к постам',
        category=PermissionCategory.CONTENT,
        default_roles=['vip', 'moderator', 'admin', 'owner'], inheritable=False
    ),
    'post.upload_file': Permission(
        code='post.upload_file', name='Загрузка файлов',
        description='Может прикреплять файлы к постам',
        category=PermissionCategory.CONTENT,
        default_roles=['admin', 'owner'], dangerous=True, inheritable=False
    ),
    
    # === 👥 ПОЛЬЗОВАТЕЛИ ===
    'user.view_profile': Permission(
        code='user.view_profile', name='Просмотр профилей',
        description='Может просматривать профили других',
        category=PermissionCategory.USERS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'user.edit_own_profile': Permission(
        code='user.edit_own_profile', name='Редактирование своего профиля',
        description='Может менять свой аватар, титул, соцсети',
        category=PermissionCategory.USERS,
        default_roles=['player', 'vip', 'moderator', 'admin', 'owner'],
        inheritable=True
    ),
    'user.edit_any_profile': Permission(
        code='user.edit_any_profile', name='Редактирование чужих профилей',
        description='Может редактировать профили других',
        category=PermissionCategory.USERS,
        default_roles=['admin', 'owner'], dangerous=True, inheritable=False
    ),
    'user.view_ip': Permission(
        code='user.view_ip', name='Просмотр IP',
        description='Может видеть IP-адреса пользователей',
        category=PermissionCategory.USERS,
        default_roles=['admin', 'owner'], inheritable=False
    ),
    
    # === ⚖️ МОДЕРАЦИЯ ===
    'mod.warn': Permission(
        code='mod.warn', name='Выдача предупреждений',
        description='Может выносить предупреждения пользователям',
        category=PermissionCategory.MODERATION,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'mod.ban': Permission(
        code='mod.ban', name='Бан пользователей',
        description='Может банить пользователей',
        category=PermissionCategory.MODERATION,
        default_roles=['moderator', 'admin', 'owner'],
        dangerous=True, inheritable=False
    ),
    'mod.unban': Permission(
        code='mod.unban', name='Разбан пользователей',
        description='Может снимать баны',
        category=PermissionCategory.MODERATION,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'mod.change_role': Permission(
        code='mod.change_role', name='Смена роли',
        description='Может менять роль пользователя',
        category=PermissionCategory.MODERATION,
        default_roles=['admin', 'owner'], dangerous=True, inheritable=False
    ),
    'mod.change_flags': Permission(
        code='mod.change_flags', name='Изменение флагов',
        description='Может выдавать/забирать флаги',
        category=PermissionCategory.MODERATION,
        default_roles=['admin', 'owner'], inheritable=False
    ),
    'mod.view_reports': Permission(
        code='mod.view_reports', name='Просмотр жалоб',
        description='Может просматривать жалобы на контент',
        category=PermissionCategory.MODERATION,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'mod.handle_reports': Permission(
        code='mod.handle_reports', name='Обработка жалоб',
        description='Может принимать решения по жалобам',
        category=PermissionCategory.MODERATION,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    
    # === ⚙️ АДМИНИСТРИРОВАНИЕ ===
    'admin.view': Permission(
        code='admin.view', name='Доступ к админке',
        description='Может заходить в админ-панель',
        category=PermissionCategory.ADMIN,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'admin.view_dashboard': Permission(
        code='admin.view_dashboard', name='Просмотр дашборда',
        description='Может видеть статистику на дашборде',
        category=PermissionCategory.ADMIN,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'admin.view_users': Permission(
        code='admin.view_users', name='Управление пользователями',
        description='Может просматривать и редактировать пользователей',
        category=PermissionCategory.ADMIN,
        default_roles=['moderator', 'admin', 'owner'], inheritable=False
    ),
    'admin.view_logs': Permission(
        code='admin.view_logs', name='Просмотр логов',
        description='Может просматривать журнал действий',
        category=PermissionCategory.ADMIN,
        default_roles=['admin', 'owner'], inheritable=False
    ),
    'admin.edit_settings': Permission(
        code='admin.edit_settings', name='Изменение настроек',
        description='Может менять настройки форума',
        category=PermissionCategory.ADMIN,
        default_roles=['admin', 'owner'], dangerous=True, inheritable=False
    ),
    'admin.clear_cache': Permission(
        code='admin.clear_cache', name='Очистка кэша',
        description='Может очищать кэш форума',
        category=PermissionCategory.ADMIN,
        default_roles=['admin', 'owner'], inheritable=False
    ),
    'admin.backup': Permission(
        code='admin.backup', name='Управление бэкапами',
        description='Может создавать и скачивать бэкапы БД',
        category=PermissionCategory.ADMIN,
        default_roles=['owner'], dangerous=True, inheritable=False
    ),
    
    # === 🔧 СИСТЕМА ===
    'system.maintenance': Permission(
        code='system.maintenance', name='Режим обслуживания',
        description='Может включать/выключать тех. работы',
        category=PermissionCategory.SYSTEM,
        default_roles=['owner'], dangerous=True, inheritable=False
    ),
    'system.reset_db': Permission(
        code='system.reset_db', name='Сброс базы данных',
        description='Может полностью сбросить БД (НЕОБРАТИМО!)',
        category=PermissionCategory.SYSTEM,
        default_roles=['owner'], dangerous=True, inheritable=False
    ),
}


# ==========================================
# 🗄️ МОДЕЛЬ ДЛЯ БАЗЫ ДАННЫХ
# ==========================================

class RolePermissionRecord(db.Model):
    """
    Хранит выданные/отозванные права для ролей.
    Если записи нет — используется дефолт из ALL_PERMISSIONS.
    """
    __tablename__ = 'role_permission_records'
    
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False, index=True)
    permission_code = db.Column(db.String(100), nullable=False)
    granted = db.Column(db.Boolean, default=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('role', 'permission_code', name='_role_perm_uc'),
    )
    
    @staticmethod
    def has_permission(role: str, permission_code: str) -> bool:
        """
        Проверить наличие права у роли.
        Приоритет: запись в БД > дефолт в ALL_PERMISSIONS > False
        """
        # 1. Проверяем БД
        record = RolePermissionRecord.query.filter_by(
            role=role, 
            permission_code=permission_code
        ).first()
        if record:
            return record.granted
        
        # 2. Проверяем дефолт
        perm = ALL_PERMISSIONS.get(permission_code)
        if perm and role in perm.default_roles:
            return True
        
        # 3. По умолчанию — запрещено (безопасный дефолт)
        return False
    
    @staticmethod
    def set_permission(role: str, permission_code: str, granted: bool, updated_by: Optional[int] = None):
        """Установить право для роли"""
        record = RolePermissionRecord.query.filter_by(
            role=role, 
            permission_code=permission_code
        ).first()
        
        if record:
            record.granted = granted
            record.updated_by = updated_by
        else:
            record = RolePermissionRecord(
                role=role,
                permission_code=permission_code,
                granted=granted,
                updated_by=updated_by
            )
            db.session.add(record)
        
        db.session.commit()
    
    @staticmethod
    def get_role_permissions(role: str) -> Dict[str, bool]:
        """Получить все права для роли с учётом дефолтов"""
        result = {}
        for code, perm in ALL_PERMISSIONS.items():
            # Сначала проверяем БД
            record = RolePermissionRecord.query.filter_by(
                role=role, permission_code=code
            ).first()
            if record:
                result[code] = record.granted
            else:
                # Иначе дефолт
                result[code] = role in perm.default_roles
        return result
    
    @staticmethod
    def get_permissions_by_category(role: str) -> Dict[str, List[Dict]]:
        """Группировка прав по категориям для админки"""
        result = {cat.value[0]: [] for cat in PermissionCategory}
        
        for code, perm in ALL_PERMISSIONS.items():
            has_perm = RolePermissionRecord.has_permission(role, code)
            result[perm.category.value[0]].append({
                'code': code,
                'name': perm.name,
                'description': perm.description,
                'granted': has_perm,
                'dangerous': perm.dangerous,
                'default': role in perm.default_roles
            })
        
        return result
    
    @staticmethod
    def init_default_permissions():
        """
        Инициализация прав по умолчанию для всех ролей.
        Вызывается один раз при старте приложения.
        """
        for role_code in ['player', 'vip', 'jr_moderator', 'moderator', 
                         'sr_forum_moderator', 'jr_admin', 'admin', 
                         'sr_admin', 'engineer', 'tech_admin', 
                         'main_admin', 's_owner', 'owner']:
            for perm_code, perm in ALL_PERMISSIONS.items():
                # Если права ещё нет в БД и роль в дефолтных — создаём запись
                existing = RolePermissionRecord.query.filter_by(
                    role=role_code, permission_code=perm_code
                ).first()
                if not existing and role_code in perm.default_roles:
                    record = RolePermissionRecord(
                        role=role_code,
                        permission_code=perm_code,
                        granted=True
                    )
                    db.session.add(record)
        db.session.commit()


# ==========================================
# 🎯 ХЕЛПЕРЫ ДЛЯ ПРОВЕРКИ ПРАВ
# ==========================================

def user_has_permission(user, permission_code: str) -> bool:
    """Проверить право у конкретного пользователя"""
    if not user or not user.is_authenticated:
        return False
    
    # OWNER имеет все права
    if user.role == 'owner':
        return True
    
    # Проверяем через модель
    return RolePermissionRecord.has_permission(user.role, permission_code)


def require_permission(permission_code: str, redirect_endpoint: str = 'core.index'):
    """
    Декоратор для защиты роутов.
    Пример: @require_permission('topic.create_in_announce')
    """
    from functools import wraps
    from flask import flash, redirect, url_for
    
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login_steam'))
            
            if not user_has_permission(current_user, permission_code):
                flash('❌ Недостаточно прав для этого действия', 'error')
                return redirect(url_for(redirect_endpoint))
            
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ==========================================
# 🎨 ХЕЛПЕРЫ ДЛЯ ШАБЛОНОВ
# ==========================================

def can(permission_code: str, user=None) -> bool:
    """
    Проверка права в шаблонах.
    Пример: {% if can('topic.create_in_announce') %}
    """
    if user is None:
        from flask_login import current_user
        user = current_user
    return user_has_permission(user, permission_code)


def get_permission_info(code: str) -> Optional[Permission]:
    """Получить информацию о праве по коду"""
    return ALL_PERMISSIONS.get(code)