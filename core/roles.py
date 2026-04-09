# core/roles.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import IntEnum

class PermissionLevel(IntEnum):
    NONE = 0
    READ = 10
    INTERACT = 20
    MODERATE = 30
    ADMIN = 40
    DEV = 50
    GOD = 99

PERMISSIONS_MATRIX = {
    'read_forum': { 'level': PermissionLevel.READ, 'desc': 'Чтение форума' },
    'create_topic': { 'level': PermissionLevel.INTERACT, 'desc': 'Создание тем' },
    'reply_topic': { 'level': PermissionLevel.INTERACT, 'desc': 'Ответ в темах' },
    'edit_own_post': { 'level': PermissionLevel.INTERACT, 'desc': 'Ред. своих постов' },
    'delete_own_post': { 'level': PermissionLevel.INTERACT, 'desc': 'Удал. своих постов' },
    'pin_own_topic': { 'level': PermissionLevel.INTERACT, 'desc': 'Закрепление своих тем' },
    'bypass_captcha': { 'level': PermissionLevel.INTERACT, 'desc': 'Обход капчи' },
    'edit_all_posts': { 'level': PermissionLevel.MODERATE, 'desc': 'Ред. чужих постов' },
    'delete_all_posts': { 'level': PermissionLevel.MODERATE, 'desc': 'Удал. чужих постов' },
    'manage_topics': { 'level': PermissionLevel.MODERATE, 'desc': 'Перенос/Лок тем' },
    'warn_user': { 'level': PermissionLevel.MODERATE, 'desc': 'Выдача предупреждений' },
    'ban_user': { 'level': PermissionLevel.MODERATE, 'desc': 'Баны аккаунтов' },
    'view_ip': { 'level': PermissionLevel.ADMIN, 'desc': 'Просмотр IP адресов' },
    'ban_ip': { 'level': PermissionLevel.ADMIN, 'desc': 'Баны по IP/Сети' },
    'manage_roles': { 'level': PermissionLevel.ADMIN, 'desc': 'Назначение рангов' },
    'manage_flags': { 'level': PermissionLevel.ADMIN, 'desc': 'Управление флагами' },
    'manage_categories': { 'level': PermissionLevel.ADMIN, 'desc': 'Создание разделов' },
    'manage_tags': { 'level': PermissionLevel.ADMIN, 'desc': 'Управление тегами' },
    'manage_announcements': { 'level': PermissionLevel.ADMIN, 'desc': 'Глобальные объявления' },
    'view_logs': { 'level': PermissionLevel.ADMIN, 'desc': 'Чтение логов действий' },
    'view_error_logs': { 'level': PermissionLevel.DEV, 'desc': 'Логи ошибок сервера' },
    'maintenance_mode': { 'level': PermissionLevel.DEV, 'desc': 'Режим обслуживания' },
    'clear_cache': { 'level': PermissionLevel.DEV, 'desc': 'Очистка кэша' },
    'manage_infrastructure': { 'level': PermissionLevel.DEV, 'desc': 'Настройки сервера/БД' },
    'api_keys': { 'level': PermissionLevel.DEV, 'desc': 'Управление API ключами' },
    'hard_reset': { 'level': PermissionLevel.GOD, 'desc': 'Сброс базы данных' },
    'god_mode': { 'level': PermissionLevel.GOD, 'desc': 'Абсолютный доступ (God Mode)' },
}

@dataclass
class RankConfig:
    name: str
    color: str
    icon: str
    level: PermissionLevel
    permissions: List[str] = field(default_factory=list)
    inherit_lower_levels: bool = True

RANKS: Dict[str, RankConfig] = {
    'player': RankConfig('Игрок', '#95a5a6', '👤', PermissionLevel.READ, [
        'read_forum', 'create_topic', 'reply_topic', 'edit_own_post', 'delete_own_post'
    ]),
    'vip': RankConfig('VIP', '#d4af37', '⭐', PermissionLevel.INTERACT, [
        'read_forum', 'create_topic', 'reply_topic', 'edit_own_post', 'delete_own_post', 
        'pin_own_topic', 'bypass_captcha'
    ]),
    'jr_moderator': RankConfig('Мл.Модератор', '#27ae60', '🛡️', PermissionLevel.MODERATE, [
        'read_forum', 'create_topic', 'reply_topic', 'edit_own_post', 'delete_own_post',
        'edit_all_posts', 'delete_all_posts', 'warn_user'
    ], inherit_lower_levels=True),
    'moderator': RankConfig('Модератор', '#2ecc71', '⚔️', PermissionLevel.MODERATE, [
        'read_forum', 'create_topic', 'reply_topic', 'edit_own_post', 'delete_own_post',
        'edit_all_posts', 'delete_all_posts', 'manage_topics', 'warn_user', 'ban_user'
    ], inherit_lower_levels=True),
    'sr_forum_moderator': RankConfig('Ст.Модератор форума', '#16a085', '🏅', PermissionLevel.MODERATE, [
        'read_forum', 'create_topic', 'reply_topic', 'edit_own_post', 'delete_own_post',
        'edit_all_posts', 'delete_all_posts', 'manage_topics', 'warn_user', 'ban_user',
        'manage_announcements'
    ], inherit_lower_levels=True),
    'jr_admin': RankConfig('Мл.Администратор', '#3498db', '🔷', PermissionLevel.ADMIN, [
        'read_forum', 'create_topic', 'reply_topic', 'manage_topics', 'warn_user', 
        'ban_user', 'view_ip', 'ban_ip', 'view_logs', 'manage_roles'
    ], inherit_lower_levels=True),
    'admin': RankConfig('Администратор', '#2980b9', '🔶', PermissionLevel.ADMIN, [
        'read_forum', 'create_topic', 'reply_topic', 'manage_topics', 'warn_user', 
        'ban_user', 'view_ip', 'ban_ip', 'view_logs', 'manage_roles',
        'manage_categories', 'manage_tags'
    ], inherit_lower_levels=True),
    'sr_admin': RankConfig('Ст.Администратор', '#8e44ad', '👑', PermissionLevel.ADMIN, [
        'read_forum', 'create_topic', 'reply_topic', 'warn_user', 'ban_user', 'view_ip', 'ban_ip',
        'manage_roles', 'manage_categories', 'manage_tags', 'manage_flags'
    ], inherit_lower_levels=True),
    'engineer': RankConfig('Инженер', '#e67e22', '🔧', PermissionLevel.DEV, [
        'read_forum', 'create_topic', 'reply_topic', 'view_error_logs', 'maintenance_mode', 'clear_cache'
    ], inherit_lower_levels=False),
    'tech_admin': RankConfig('Тех. Администратор', '#c0392b', '⚙️', PermissionLevel.DEV, [
        'read_forum', 'create_topic', 'reply_topic', 'view_error_logs', 'maintenance_mode', 'clear_cache',
        'manage_infrastructure', 'api_keys'
    ], inherit_lower_levels=False),
    'main_admin': RankConfig('Главный администратор', '#f39c12', '🎖️', PermissionLevel.ADMIN, [
        'read_forum', 'create_topic', 'reply_topic', 'warn_user', 'ban_user', 'view_ip', 'ban_ip',
        'manage_roles', 'manage_categories', 'manage_tags', 'manage_flags', 'view_logs',
        'manage_infrastructure', 'api_keys'
    ], inherit_lower_levels=True),
    's_owner': RankConfig('S.OWNER', '#e74c3c', '🌟', PermissionLevel.GOD, [
        'read_forum', 'create_topic', 'reply_topic', 'warn_user', 'ban_user', 'view_ip', 'ban_ip',
        'manage_roles', 'manage_categories', 'manage_tags', 'manage_flags', 'view_logs',
        'manage_infrastructure', 'api_keys', 'maintenance_mode', 'clear_cache', 'view_error_logs',
        'hard_reset'
    ], inherit_lower_levels=True),
    'owner': RankConfig('OWNER', '#FFD700', '💎', PermissionLevel.GOD, [], inherit_lower_levels=True),
}

# ==========================================
# 🏷️ ПОЛНАЯ СИСТЕМА ФЛАГОВ (BADGES)
# ==========================================

@dataclass
class FlagConfig:
    name: str
    icon: str
    color: str
    description: str  # ✅ Описание что даёт флаг
    permissions: List[str] = field(default_factory=list)
    auto_assign: bool = False
    category: str = 'general'  # general, premium, special, technical

FLAGS: Dict[str, FlagConfig] = {
    # === 🎁 ПРЕМИУМ ФЛАГИ ===
    'donator': FlagConfig(
        name='Донатер',
        icon='💎',
        color='#d4af37',
        description='Поддержал форум финансово',
        permissions=['bypass_captcha'],
        category='premium'
    ),
    'vip': FlagConfig(
        name='VIP',
        icon='👑',
        color='#ffd700',
        description='VIP статус с привилегиями',
        permissions=['bypass_captcha', 'view_error_logs'],
        category='premium'
    ),
    'founder': FlagConfig(
        name='Основатель',
        icon='🏛️',
        color='#f1c40f',
        description='Основатель проекта',
        permissions=['god_mode'],
        category='special'
    ),
    
    # === 🎖️ ОСОБЫЕ ЗАСЛУГИ ===
    'veteran': FlagConfig(
        name='Ветеран',
        icon='🎖️',
        color='#2ecc71',
        description='Давно с нами (более 1 года)',
        permissions=['bypass_captcha'],
        auto_assign=True,
        category='special'
    ),
    'bug_hunter': FlagConfig(
        name='Баг-хантер',
        icon='🐛',
        color='#e67e22',
        description='Нашёл и сообщил о критических багах',
        permissions=['view_error_logs'],
        category='special'
    ),
    'helper': FlagConfig(
        name='Помощник',
        icon='🤝',
        color='#3498db',
        description='Активно помогает новичкам',
        permissions=[],
        category='special'
    ),
    'creator': FlagConfig(
        name='Автор',
        icon='✍️',
        color='#9b59b6',
        description='Создатель контента/гайдов',
        permissions=[],
        category='special'
    ),
    'translator': FlagConfig(
        name='Переводчик',
        icon='🌐',
        color='#1abc9c',
        description='Помогает с переводами',
        permissions=[],
        category='special'
    ),
    
    # === 🎮 ИГРОВЫЕ ДОСТИЖЕНИЯ ===
    'champion': FlagConfig(
        name='Чемпион',
        icon='🏆',
        color='#e74c3c',
        description='Победитель турнира',
        permissions=[],
        category='special'
    ),
    'top_player': FlagConfig(
        name='Топ игрок',
        icon='🎯',
        color='#e67e22',
        description='Входит в топ-10 рейтинга',
        permissions=[],
        category='special'
    ),
    
    # === 🔧 ТЕХНИЧЕСКИЕ ФЛАГИ ===
    'beta_tester': FlagConfig(
        name='Бета-тестер',
        icon='🧪',
        color='#9b59b6',
        description='Тестирует новые функции',
        permissions=['view_error_logs'],
        category='technical'
    ),
    'developer': FlagConfig(
        name='Разработчик',
        icon='💻',
        color='#34495e',
        description='Разработчик форума',
        permissions=['view_error_logs', 'clear_cache'],
        category='technical'
    ),
    
    # === ⚠️ ОГРАНИЧЕНИЯ ===
    'sanctioned': FlagConfig(
        name='Подсанкционный',
        icon='⛓️',
        color='#e74c3c',
        description='Ограничения за нарушения',
        permissions=[],
        category='special'
    ),
    'probation': FlagConfig(
        name='Испытательный срок',
        icon='⏳',
        color='#f39c12',
        description='На испытательном сроке',
        permissions=[],
        category='special'
    ),
}

# ==========================================
# ХЕЛПЕРЫ
# ==========================================

def get_rank(role_code: str) -> RankConfig:
    return RANKS.get(role_code, RANKS['player'])

def get_flag(flag_code: str) -> Optional[FlagConfig]:
    return FLAGS.get(flag_code)

def _get_all_permissions_by_level(min_level: PermissionLevel) -> set:
    perms = set()
    for perm_code, perm_info in PERMISSIONS_MATRIX.items():
        if perm_info['level'] <= min_level:
            perms.add(perm_code)
    return perms

def can_perform(role_code: str, permission_code: str) -> bool:
    if role_code == 'owner':
        return True
    
    perm_info = PERMISSIONS_MATRIX.get(permission_code)
    if not perm_info:
        return False
    
    if perm_info['level'] == PermissionLevel.GOD:
        return role_code in ['owner', 's_owner']
    
    rank = get_rank(role_code)
    
    if permission_code in rank.permissions:
        return True
    
    if rank.inherit_lower_levels:
        if perm_info['level'] <= rank.level:
            return True
    
    return False

def user_has_permission(user) -> callable:
    def check(permission_code: str) -> bool:
        if getattr(user, 'is_banned', False) and permission_code != 'read_forum':
            return False
        
        if can_perform(user.role, permission_code):
            return True
        
        if hasattr(user, 'has_flag'):
            for flag_code in user.get_flags():
                flag = get_flag(flag_code)
                if flag and permission_code in flag.permissions:
                    return True
                if flag_code == 'founder' and permission_code == 'god_mode':
                    return True
        
        if hasattr(user, 'has_flag'):
            if user.has_flag('admin') and permission_code in ['edit_all_posts', 'delete_all_posts', 'manage_topics', 'warn_user', 'ban_user', 'view_logs']:
                return True
            if user.has_flag('moderator') and permission_code in ['edit_all_posts', 'delete_all_posts', 'warn_user']:
                return True
        
        return False
    
    return check

def get_user_permission_level(user) -> PermissionLevel:
    rank = get_rank(user.role)
    max_level = rank.level
    
    if hasattr(user, 'get_flags'):
        for flag_code in user.get_flags():
            if flag_code == 'founder':
                return PermissionLevel.GOD
            if flag_code == 'admin':
                max_level = max(max_level, PermissionLevel.ADMIN)
            if flag_code == 'moderator':
                max_level = max(max_level, PermissionLevel.MODERATE)
    
    return max_level

def get_available_permissions(user) -> List[Dict]:
    check = user_has_permission(user)
    result = []
    
    for perm_code, perm_info in PERMISSIONS_MATRIX.items():
        if check(perm_code):
            result.append({
                'code': perm_code,
                'desc': perm_info['desc'],
                'level': perm_info['level'].name,
                'level_value': perm_info['level'].value
            })
    
    result.sort(key=lambda x: x['level_value'], reverse=True)
    return result

def get_role_options_for_assigner(assigner_user) -> List[Dict]:
    assigner_level = get_user_permission_level(assigner_user)
    options = []
    
    for role_code, rank in RANKS.items():
        if rank.level <= assigner_level or role_code == 'player':
            options.append({
                'code': role_code,
                'name': rank.name,
                'color': rank.color,
                'icon': rank.icon,
                'disabled': role_code in ['owner', 's_owner'] and assigner_user.role != 'owner'
            })
    
    return options

def get_flag_options() -> List[Dict]:
    """Возвращает все флаги сгруппированные по категориям"""
    result = {
        'premium': [],
        'special': [],
        'technical': [],
        'other': []
    }
    
    for code, flag in FLAGS.items():
        flag_data = {
            'code': code,
            'name': flag.name,
            'icon': flag.icon,
            'color': flag.color,
            'description': flag.description
        }
        
        if flag.category in result:
            result[flag.category].append(flag_data)
        else:
            result['other'].append(flag_data)
    
    return result

def get_flags_by_category() -> Dict[str, List[Dict]]:
    """Группирует флаги по категориям для отображения в админке"""
    return get_flag_options()