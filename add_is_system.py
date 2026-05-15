# add_is_system.py
from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    try:
        # Try SQLite syntax first
        db.session.execute(text('ALTER TABLE chat_messages ADD COLUMN is_system BOOLEAN DEFAULT 0'))
        db.session.commit()
        print("Successfully added is_system column to chat_messages")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print("Column is_system already exists")
        else:
            print(f"Error: {e}")
