import re
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, redirect, url_for, request, current_app, flash
from flask_login import login_user, logout_user, current_user
from urllib.parse import urlencode
from auth.models import User
from forum.models import Notification
from extensions import db

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

FOUNDER_STEAM_ID = "76561199528061055"

# HTTP session
_http_session = requests.Session()
_http_session.headers.update({'User-Agent': 'TW-Forum-Engine/1.0'})
_adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
_http_session.mount('http://', _adapter)
_http_session.mount('https://', _adapter)


# ==========================================
# 🔐 SECURITY HELPERS
# ==========================================

def get_location_from_ip(ip_address: str) -> str:
    if not ip_address:
        return 'Неизвестно'

    if ip_address in ['127.0.0.1', '::1']:
        return 'Локальная сеть'

    if ip_address.startswith(('192.168.', '10.')):
        return 'Локальная сеть'

    return 'Неизвестно'


def is_new_device(user: User, user_agent: str, ip_address: str) -> bool:
    if not hasattr(user, '_last_login_info'):
        return True

    last = user._last_login_info

    if last.get('user_agent') != user_agent:
        return True

    if last.get('ip', '').split('.')[:-1] != ip_address.split('.')[:-1]:
        return True

    return False


def log_security_action(user_id, action_type, details=None, ip_address=None):
    logger.info(f"SECURITY_LOG: {{'user_id': {user_id}, 'action': {action_type}, 'ip': {ip_address}}}")


def send_login_notification(user: User, is_new_device: bool, location: str):
    try:
        Notification.create_system_notification(
            user_id=user.id,
            title='🔐 Новый вход',
            message='Вход с нового устройства' if is_new_device else 'Вход в аккаунт',
            extra_data={'location': location}
        )
    except Exception as e:
        logger.error(f"Notification error: {e}")


# ==========================================
# 🔐 STEAM
# ==========================================

def _verify_openid_fast(params: dict):
    if params.get('openid.mode') != 'id_res':
        return None

    claimed_id = params.get('openid.claimed_id', '')
    match = re.search(r'id/(\d+)', claimed_id)

    return match.group(1) if match else None


def _fetch_profile_cached(steam_id: str, user: User | None):
    if user and user.avatar and user.username and user.last_login:
        if (datetime.utcnow() - user.last_login) < timedelta(hours=24):
            return None

    api_key = current_app.config.get('STEAM_API_KEY')
    if not api_key:
        return None

    try:
        url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={api_key}&steamids={steam_id}"
        resp = _http_session.get(url, timeout=2)
        data = resp.json()['response']['players'][0]

        return {
            'username': data.get('personaname'),
            'avatar': data.get('avatarfull')
        }
    except Exception as e:
        logger.error(f"Steam API error: {e}")
        return None


# ==========================================
# 🔐 ROUTES
# ==========================================

@auth_bp.route('/login')
def login_steam():
    return_to = url_for('auth.login_callback', _external=True)
    base_url = return_to.replace('/auth/callback', '')

    params = {
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.mode': 'checkid_setup',
        'openid.return_to': return_to,
        'openid.realm': base_url,
        'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select'
    }

    logger.info(f"Steam redirect → {return_to}")

    return redirect(f"https://steamcommunity.com/openid/login?{urlencode(params)}")


@auth_bp.route('/callback')
def login_callback():
    logger.info("STEAM CALLBACK HIT")

    if current_user.is_authenticated:
        return redirect(url_for('core.index'))

    if not request.args:
        flash('Ошибка авторизации', 'error')
        return redirect(url_for('core.index'))

    steam_id = _verify_openid_fast(request.args.to_dict())
    if not steam_id:
        flash('Steam verification failed', 'error')
        return redirect(url_for('core.index'))

    user = db.session.execute(
        db.select(User).filter_by(steam_id=steam_id)
    ).scalar_one_or_none()

    profile = _fetch_profile_cached(steam_id, user)

    is_new = user is None

    if is_new:
        user = User(
            steam_id=steam_id,
            username=(profile.get('username') if profile else None) or f'User_{steam_id[-6:]}',
            avatar=(profile.get('avatar') if profile else '') or '',
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow(),
            role='player'
        )
        db.session.add(user)
    else:
        user.last_login = datetime.utcnow()

        if profile:
            user.username = profile.get('username') or user.username
            user.avatar = profile.get('avatar') or user.avatar

    if steam_id == FOUNDER_STEAM_ID:
        user.role = 'owner'

    try:
        ip = request.remote_addr or '0.0.0.0'
        ua = request.user_agent.string

        user._last_login_info = {
            'ip': ip,
            'user_agent': ua
        }

        log_security_action(user.id if user else None, 'login', ip_address=ip)

    except Exception as e:
        logger.error(f"Security error: {e}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"DB error: {e}")
        return redirect(url_for('core.index'))

    login_user(user)

    flash(f'Добро пожаловать, {user.username}', 'success')

    return redirect(url_for('core.index'))


@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Вы вышли', 'info')
    return redirect(url_for('core.index'))
