# config.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "instance" / "forum.db"}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    STEAM_API_KEY = os.environ.get('STEAM_API_KEY')
    SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:5000')
    SITE_NAME = "TW-FORUM"
    
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = 'noreply@tw-forum.com'    