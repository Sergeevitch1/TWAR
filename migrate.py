# migrate.py
from app import create_app
from extensions import db

app = create_app()

with app.app_context():
    # Список новых колонок для добавления
    new_columns = [
        "ALTER TABLE users ADD COLUMN signature TEXT",
        "ALTER TABLE users ADD COLUMN game_nickname VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN discord VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN telegram VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN theme VARCHAR(20) DEFAULT 'dark'",
        "ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'Europe/Moscow'",
        "ALTER TABLE users ADD COLUMN language VARCHAR(10) DEFAULT 'ru'",
        "ALTER TABLE users ADD COLUMN show_online_status BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN show_email BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN show_activity BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN allow_search_index BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN email_new_reply BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN email_new_mention BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN email_private_message BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notify_new_reply BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notify_new_like BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notify_announcements BOOLEAN DEFAULT 1",
    ]
    
    with db.engine.connect() as conn:
        for sql in new_columns:
            try:
                conn.execute(db.text(sql))
                print(f"✓ {sql.split()[3]}")
            except Exception as e:
                print(f"✗ {sql.split()[3]}: {e}")
        conn.commit()
    
    print("\n✅ Миграция завершена!")