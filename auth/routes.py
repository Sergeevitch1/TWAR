# auth/routes.py
import re
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, redirect, url_for, request, current_app, flash, session, render_template
from flask_login import login_user, logout_user, current_user
from urllib.parse import urlencode
from auth.models import User
from forum.models import Notification  # Для уведомлений о входах
from extensions import db

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

FOUNDER_STEAM_ID = "76561199528061055"

# Оптимизированная сессия с keep-alive
_http_session = requests.Session()
_http_session.headers.update({'User-Agent': 'TW-Forum-Engine/1.0'})
# Пул коннектов для скорости
_adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
_http_session.mount('http://', _adapter)
_http_session.mount('https://', _adapter)

# ==========================================
# 🔐 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БЕЗОПАСНОСТИ
# ==========================================

def get_location_from_ip(ip_address: str) -> str:
    """
    Получает приблизительное местоположение по IP (заглушка)
    В продакшене можно использовать ipapi.co или ipinfo.io
    """
    # Заглушка: возвращаем "Неизвестно" или кэшируем простые диапазоны
    if ip_address in ['127.0.0.1', '::1']:
        return 'Локальная сеть'
    
    # Простая эвристика по первым октетам (для примера)
    if ip_address.startswith('192.168.') or ip_address.startswith('10.'):
        return 'Локальная сеть'
    
    # В реальном проекте здесь был бы API-запрос
    return 'Неизвестно'


def is_new_device(user: User, user_agent: str, ip_address: str) -> bool:
    """
    Проверяет, является ли устройство/местоположение новым для пользователя
    """
    # Если нет истории входов — считаем новым
    if not hasattr(user, '_last_login_info'):
        return True
    
    last_info = user._last_login_info
    
    # Сравниваем User-Agent (браузер + ОС)
    if last_info.get('user_agent') != user_agent:
        return True
    
    # Сравниваем подсеть IP (первые 3 октета)
    last_ip_parts = last_info.get('ip', '').split('.')[:-1]
    current_ip_parts = ip_address.split('.')[:-1]
    
    if last_ip_parts != current_ip_parts:
        return True
    
    return False


def log_security_action(user_id: int, action_type: str, details: dict = None, ip_address: str = None):
    """
    Логирует действие безопасности (можно расширить до модели SecurityLog)
    """
    log_entry = {
        'user_id': user_id,
        'action': action_type,
        'timestamp': datetime.utcnow().isoformat(),
        'ip': ip_address or request.remote_addr,
        'details': details or {}
    }
    
    # Логируем в файл/консоль
    logger.info(f"SECURITY_LOG: {log_entry}")
    
    # В будущем: db.session.add(SecurityLog(**log_entry))


def send_login_notification(user: User, is_new_device: bool, location: str):
    """
    Создаёт уведомление и/или email о новом входе
    """
    # Создаём уведомление в базе
    message = f'Вход с нового устройства' if is_new_device else f'Вход в аккаунт'
    if location and location != 'Неизвестно':
        message += f' ({location})'
    
    Notification.create_system_notification(
        user_id=user.id,
        title='🔐 Новый вход',
        message=message,
        extra_data={
            'ip': request.remote_addr,
            'user_agent': request.user_agent.string,
            'location': location,
            'is_new_device': is_new_device
        }
    )
    
    # Отправляем email если включено в настройках
    if hasattr(user, 'email_new_login') and user.email_new_login and user.email:
        send_login_email(user, location, is_new_device)


def send_login_email(user: User, location: str, is_new_device: bool):
    """
    Отправляет email-уведомление о входе
    (Заглушка — в продакшене использовать Flask-Mail)
    """
    subject = f"🔐 Новый вход в аккаунт {'(новое устройство)' if is_new_device else ''}"
    
    body = f"""
Здравствуйте, {user.username}!

В ваш аккаунт на TW-FORUM был выполнен вход.

📍 Местоположение: {location or 'Неизвестно'}
🌐 IP-адрес: {request.remote_addr}
🖥️ Устройство: {request.user_agent.browser or 'Unknown'} на {request.user_agent.platform or 'Unknown'}
⏰ Время: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC

{'⚠️ Если это были не вы, немедленно смените пароль и завершите все сессии в настройках безопасности!' if is_new_device else ''}

Если это были вы — просто проигнорируйте это письмо.

С уважением,
Команда TW-FORUM
    """.strip()
    
    # Логируем вместо реальной отправки
    logger.info(f"EMAIL_QUEUED: to={user.email}, subject={subject}")
    
    # В продакшене:
    # from flask_mail import Message, Mail
    # msg = Message(subject, recipients=[user.email], body=body)
    # mail.send(msg)


def _verify_openid_fast(params: dict) -> str | None:
    """Ускоренная проверка (только извлечение ID без полной валидации)"""
    if params.get('openid.mode') != 'id_res':
        return None

    claimed_id = params.get('openid.claimed_id', '')
    match = re.search(r'steamcommunity\.com/openid/id/(\d{17,19})', claimed_id)
    
    if not match:
        return None
    
    steam_id = match.group(1)
    
    # ОПТИМИЗАЦИЯ: Для localhost пропускаем полную проверку подписи
    if current_app.config.get('FLASK_ENV') == 'development':
        return steam_id
    
    # В продакшене делаем полную проверку
    verify_url = params.get('openid.op_endpoint', '')
    if not verify_url:
        return None

    signed_fields = params.get('openid.signed', '')
    verify_data = {
        'openid.assoc_handle': params.get('openid.assoc_handle', ''),
        'openid.signed': signed_fields,
        'openid.sig': params.get('openid.sig', ''),
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.mode': 'check_authentication'
    }

    for field in signed_fields.split(','):
        if field and f'openid.{field}' in params:
            verify_data[f'openid.{field}'] = params[f'openid.{field}']

    try:
        resp = _http_session.post(verify_url, data=verify_data, timeout=3)
        return steam_id if 'is_valid:true' in resp.text else None
    except requests.RequestException as e:
        logger.error(f"OpenID verification failed: {e}")
        return None


def _fetch_profile_cached(steam_id: str, user: User | None) -> dict | None:
    """
    Умное получение профиля:
    1. Если юзер есть и последний апдейт < 24ч - берем из БД
    2. Иначе запрашиваем Steam API
    """
    if user and user.avatar and user.username:
        last_update = user.last_login
        if (datetime.utcnow() - last_update) < timedelta(hours=24):
            return None
    
    api_key = current_app.config.get('STEAM_API_KEY')
    if not api_key:
        return None

    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={api_key}&steamids={steam_id}"
    try:
        resp = _http_session.get(url, timeout=2)
        resp.raise_for_status()
        players = resp.json().get('response', {}).get('players', [])
        if not players:
            return None

        p = players[0]
        return {
            'username': p.get('personaname', f'User_{steam_id[-6:]}'),
            'avatar': p.get('avatarfull', p.get('avatarmedium', '')),
            'profile_url': p.get('profileurl', '')
        }
    except requests.Timeout:
        logger.warning(f"Steam API timeout (2s) for {steam_id}")
        return None
    except requests.RequestException as e:
        logger.error(f"Steam API fetch failed: {e}")
        return None


# ==========================================
# 🔐 РОУТЫ АВТОРИЗАЦИИ
# ==========================================

@auth_bp.route('/login')
def login_steam():
    base_url = current_app.config.get('SITE_URL', 'https://twar.onrender.com')
    return_to = f"{base_url}/auth/callback"

    params = {
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.mode': 'checkid_setup',
        'openid.return_to': return_to,
        'openid.realm': base_url,
        'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select'
    }

    return redirect(f"https://steamcommunity.com/openid/login?{urlencode(params)}")


@auth_bp.route('/callback')
def login_callback():
    if current_user.is_authenticated:
        return redirect(url_for('core.index'))

    if not request.args:
        flash('Отсутствуют данные авторизации', 'error')
        return redirect(url_for('core.index'))

    # 1. Быстрая проверка OpenID
    steam_id = _verify_openid_fast(request.args.to_dict())
    if not steam_id:
        flash('Ошибка проверки подлинности Steam', 'error')
        return redirect(url_for('core.index'))

    # 2. Ищем пользователя
    user = db.session.execute(
        db.select(User).filter_by(steam_id=steam_id)
    ).scalar_one_or_none()
    
    # 3. Получаем профиль (только если нужно)
    profile = _fetch_profile_cached(steam_id, user)
    
    # 4. Создаем или обновляем
    is_new_user = user is None
    if is_new_user:
        user = User(
            steam_id=steam_id,
            username=profile['username'] if profile else f'User_{steam_id[-6:]}',
            avatar=profile['avatar'] if profile else '',
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow(),
            role='player'
        )
        db.session.add(user)
        login_action = 'first_login'
    else:
        login_action = 'login'
        user.last_login = datetime.utcnow()
        # Обновляем только если получили свежие данные
        if profile:
            user.username = profile['username']
            if profile['avatar']:
                user.avatar = profile['avatar']

    # 5. Авто-выдача OWNER
    if str(steam_id) == FOUNDER_STEAM_ID:
        user.role = 'owner'
        if 'founder' not in user.get_flags():
            user.add_flag('founder')

    # 6. 🔐 БЕЗОПАСНОСТЬ: Логируем вход и проверяем новое устройство
    try:
        # Проверяем, новое ли это устройство/местоположение
        user_agent = request.user_agent.string
        ip_address = request.remote_addr
        location = get_location_from_ip(ip_address)
        
        # Сохраняем инфо о последнем входе для сравнения (временно в памяти)
        if user:
            user._last_login_info = {
                'user_agent': user_agent,
                'ip': ip_address,
                'time': datetime.utcnow()
            }
        
        is_new = is_new_device(user, user_agent, ip_address) if user else True
        
        # Логируем действие
        log_security_action(
            user_id=user.id if user else None,
            action_type=login_action,
            details={
                'steam_id': steam_id,
                'is_new_user': is_new_user,
                'is_new_device': is_new,
                'location': location
            },
            ip_address=ip_address
        )
        
        # Создаём уведомление и/или email
        if user and not is_new_user:  # Не спамим при первой регистрации
            send_login_notification(user, is_new, location)
            
    except Exception as e:
        # Не ломаем вход если безопасность упала
        logger.error(f"Security logging failed: {e}")

    # 7. Коммит и вход
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database commit failed: {e}")
        flash('Ошибка сохранения данных', 'error')
        return redirect(url_for('core.index'))

    login_user(user)
    
    if str(steam_id) == FOUNDER_STEAM_ID:
        flash('Добро пожаловать, Создатель! Права OWNER активированы.', 'success')
    elif is_new_user:
        flash(f'Добро пожаловать, {user.username}! Аккаунт создан.', 'success')
    else:
        flash(f'С возвращением, {user.username}!', 'success')
    
    return redirect(url_for('core.index'))


@auth_bp.route('/logout')
def logout():
    if current_user.is_authenticated:
        # Логируем выход
        log_security_action(
            user_id=current_user.id,
            action_type='logout',
            details={'username': current_user.username},
            ip_address=request.remote_addr
        )
    
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('core.index'))
