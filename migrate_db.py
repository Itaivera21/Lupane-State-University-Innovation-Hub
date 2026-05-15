# migrate_db.py
import sys
import os

# Add current directory to path
sys.path.insert(0, os.getcwd())

from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    print("Starting database migration...")
    
    # Add supervisor columns to users table
    columns_to_add = [
        ('is_supervisor', 'BOOLEAN DEFAULT FALSE'),
        ('first_name', 'VARCHAR(100)'),
        ('last_name', 'VARCHAR(100)'),
        ('department', 'VARCHAR(100)'),
        ('specialization', 'VARCHAR(200)'),
        ('bio', 'TEXT')
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            db.session.execute(text(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}'))
            db.session.commit()
            print(f"Added {col_name} column")
        except Exception as e:
            if "Duplicate column" in str(e):
                print(f"{col_name} already exists")
            else:
                print(f"Error adding {col_name}: {e}")
    
    # Add supervision fields to projects table
    project_columns = [
        ('supervisor_id', 'INTEGER'),
        ('supervision_requested_at', 'DATETIME'),
        ('supervision_approved_at', 'DATETIME'),
        ('completed_at', 'DATETIME')
    ]
    
    for col_name, col_type in project_columns:
        try:
            db.session.execute(text(f'ALTER TABLE projects ADD COLUMN {col_name} {col_type}'))
            db.session.commit()
            print(f"Added {col_name} column")
        except Exception as e:
            if "Duplicate column" in str(e):
                print(f"{col_name} already exists")
            else:
                print(f"Error adding {col_name}: {e}")
    
    # Create new tables (groups, group_members, etc.)
    db.create_all()
    db.session.commit()
    
    print("Migration completed successfully!")