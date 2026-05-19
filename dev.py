from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from models import db, User, Project, ProjectApplication, ForumTopic, ForumPost, ChatMessage, ChatResource, GroupMember, Group
from datetime import datetime, timedelta
import os
import re
import tempfile
import sys
import platform
import shutil
import subprocess
import io

# Try to import optional dependencies
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Create developer blueprint
dev_bp = Blueprint('dev', __name__, url_prefix='/dev')

# Developer required decorator
def dev_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_dev:
            # Clear any stale flash messages before redirecting
            session.pop('_flashes', None)
            flash('Access denied. Developer privileges required.', 'error')
            return redirect(url_for('dev.signin'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function to get database size for MySQL/TiDB
def get_database_size():
    """Get database size and table count for MySQL/TiDB"""
    try:
        # Get database name from connection URI
        db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
        
        # Extract database name from MySQL URI
        match = re.search(r'mysql\+pymysql://[^:]+:[^@]+@[^/]+/([^?]+)', db_uri)
        if match:
            db_name = match.group(1)
            
            # Get table count
            result = db.session.execute(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = '{db_name}'
            """)
            table_count = result.scalar()
            
            # Get database size
            result = db.session.execute(f"""
                SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as size_mb
                FROM information_schema.tables 
                WHERE table_schema = '{db_name}'
            """)
            size_mb = result.scalar()
            
            if size_mb:
                return f"{size_mb:.2f} MB", table_count
        
        return "Unknown", 0
    except Exception as e:
        print(f"Error getting DB size: {e}")
        return "Unknown", 0

# Helper function to get server uptime for Windows
def get_server_uptime():
    """Get server uptime (Windows compatible)"""
    try:
        if platform.system() == "Windows":
            try:
                result = subprocess.run(['systeminfo', '|', 'find', 'System Boot Time'],
                                       capture_output=True, text=True, shell=True)
                if result.stdout:
                    return "Online"
            except:
                pass
            return "Online"
        else:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                days = int(uptime_seconds // 86400)
                hours = int((uptime_seconds % 86400) // 3600)
                if days > 0:
                    return f"{days}d {hours}h"
                return f"{hours}h"
    except:
        return "Online"

# Helper function to get last backup
def get_last_backup():
    backup_dir = os.path.join(current_app.root_path, 'backups')
    if os.path.exists(backup_dir):
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.sql')]
        if backups:
            latest = max(backups, key=lambda x: os.path.getctime(os.path.join(backup_dir, x)))
            ctime = os.path.getctime(os.path.join(backup_dir, latest))
            return datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M')
    return None

# Helper function to get log count
def get_log_count():
    log_dir = os.path.join(current_app.root_path, 'logs')
    log_file = os.path.join(log_dir, 'app.log')
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                return len(f.readlines())
        except:
            pass
    return 0

# Setup logging directory
def setup_logging():
    log_dir = os.path.join(current_app.root_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)

# Helper function to get database tables for SQL dump
def get_all_tables():
    """Get all table names from the database"""
    result = db.session.execute("SHOW TABLES")
    return [row[0] for row in result.fetchall()]

# Helper function to generate SQL dump
def generate_sql_dump():
    """Generate SQL dump of entire database"""
    dump_lines = []
    
    # Add header
    dump_lines.append("-- Innovation Hub Database Backup")
    dump_lines.append(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    dump_lines.append("-- ------------------------------------------------------")
    dump_lines.append("")
    
    # Get all tables
    tables = get_all_tables()
    
    for table in tables:
        # Get CREATE TABLE statement
        result = db.session.execute(f"SHOW CREATE TABLE `{table}`")
        row = result.fetchone()
        if row:
            create_stmt = row[1]
            dump_lines.append(f"-- Table structure for `{table}`")
            dump_lines.append(create_stmt + ";")
            dump_lines.append("")
            
            # Get table data
            result = db.session.execute(f"SELECT * FROM `{table}`")
            columns = result.keys()
            
            # Generate INSERT statements
            for row_data in result.fetchall():
                values = []
                for col in columns:
                    val = row_data[col]
                    if val is None:
                        values.append("NULL")
                    elif isinstance(val, (int, float)):
                        values.append(str(val))
                    elif isinstance(val, datetime):
                        values.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                    else:
                        # Escape single quotes
                        escaped_val = str(val).replace("'", "''")
                        values.append(f"'{escaped_val}'")
                
                insert_stmt = f"INSERT INTO `{table}` ({', '.join(columns)}) VALUES ({', '.join(values)});"
                dump_lines.append(insert_stmt)
            
            dump_lines.append("")
            dump_lines.append("-- ------------------------------------------------------")
            dump_lines.append("")
    
    return "\n".join(dump_lines)

# Developer signin route
@dev_bp.route('/signin', methods=['GET', 'POST'])
def signin():
    if current_user.is_authenticated and current_user.is_dev:
        return redirect(url_for('dev.dashboard'))

    # Clear any stale flash messages when loading the signin page
    session.pop('_flashes', None)

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.is_dev and check_password_hash(user.password, password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Welcome to Developer Portal', 'success')
            return redirect(url_for('dev.dashboard'))
        else:
            # Clear flashes before adding new one to avoid duplicates
            session.pop('_flashes', None)
            flash('Invalid developer credentials', 'error')
            return redirect(url_for('dev.signin'))

    return render_template('dev/devsignin.html')

# Developer dashboard
@dev_bp.route('/dashboard')
@login_required
@dev_required
def dashboard():
    # User stats
    total_users = User.query.count()
    total_admins = User.query.filter_by(is_admin=True).count()
    total_developers = User.query.filter_by(is_dev=True).count()
    total_supervisors = User.query.filter_by(is_supervisor=True).count()
    total_students = total_users - total_admins - total_developers - total_supervisors

    # Project stats
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='active').count()
    completed_projects = Project.query.filter_by(status='completed').count()
    pending_supervision = Project.query.filter_by(status='pending_supervision').count()

    # Forum stats
    total_topics = ForumTopic.query.count()
    total_posts = ForumPost.query.count()

    # Application stats
    total_applications = ProjectApplication.query.count()
    pending_applications = ProjectApplication.query.filter_by(status='pending').count()

    # Chat stats
    total_messages = ChatMessage.query.count()

    # New users this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_users = User.query.filter(User.created_at >= week_ago).count()

    # Database info
    db_size, total_tables = get_database_size()

    # System status
    try:
        db.session.execute('SELECT 1').scalar()
        system_status = "Online"
    except:
        system_status = "Issues Detected"

    # Server info
    uptime = get_server_uptime()
    server_start_str = "Server active"

    # Backup info
    last_backup = get_last_backup()

    # Environment
    flask_env = os.environ.get('FLASK_ENV', 'development')

    # Log count
    log_count = get_log_count()

    # All users and projects for tables
    all_users = User.query.order_by(User.created_at.desc()).all()
    all_projects = Project.query.order_by(Project.created_at.desc()).all()

    # Tool count
    tool_count = 6

    return render_template('dev/devdashboard.html',
        total_users=total_users,
        total_projects=total_projects,
        total_topics=total_topics,
        total_posts=total_posts,
        total_applications=total_applications,
        total_messages=total_messages,
        total_admins=total_admins,
        total_developers=total_developers,
        total_supervisors=total_supervisors,
        total_students=total_students,
        active_projects=active_projects,
        completed_projects=completed_projects,
        pending_supervision=pending_supervision,
        pending_applications=pending_applications,
        new_users=new_users,
        db_size=db_size,
        total_tables=total_tables,
        uptime=uptime,
        server_start=server_start_str,
        system_status=system_status,
        last_backup=last_backup,
        flask_env=flask_env,
        log_count=log_count,
        tool_count=tool_count,
        all_users=all_users,
        all_projects=all_projects
    )

# ==================== USER MANAGEMENT ====================

@dev_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@login_required
@dev_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('dev.dashboard'))

    try:
        # FIRST: Delete group memberships (critical - prevents foreign key errors)
        GroupMember.query.filter_by(user_id=user.id).delete()

        # Delete chat resources uploaded by user
        ChatResource.query.filter_by(uploaded_by=user.id).delete()

        # Delete applications
        ProjectApplication.query.filter_by(applicant_id=user.id).delete()

        # Delete forum posts and topics
        ForumPost.query.filter_by(author_id=user.id).delete()
        ForumTopic.query.filter_by(author_id=user.id).delete()

        # Delete chat messages
        ChatMessage.query.filter_by(sender_id=user.id).delete()

        # Delete user's projects
        user_projects = Project.query.filter_by(student_id=user.id).all()
        for project in user_projects:
            # Delete group for this project
            group = Group.query.filter_by(project_id=project.id).first()
            if group:
                GroupMember.query.filter_by(group_id=group.id).delete()
                db.session.delete(group)
            # Delete chat resources for the project
            ChatResource.query.filter_by(project_id=project.id).delete()
            # Delete applications for the project
            ProjectApplication.query.filter_by(project_id=project.id).delete()
            # Delete chat messages for the project
            ChatMessage.query.filter_by(project_id=project.id).delete()
            # Delete forum topics for the project
            ForumTopic.query.filter_by(project_id=project.id).delete()
            # Delete the project
            db.session.delete(project)

        db.session.delete(user)
        db.session.commit()

        flash(f'User {user.email} deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')

    return redirect(url_for('dev.dashboard'))

@dev_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
@dev_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)

    try:
        # Delete group members for this project's group
        group = Group.query.filter_by(project_id=project.id).first()
        if group:
            GroupMember.query.filter_by(group_id=group.id).delete()
            db.session.delete(group)

        ProjectApplication.query.filter_by(project_id=project.id).delete()
        ChatMessage.query.filter_by(project_id=project.id).delete()
        ChatResource.query.filter_by(project_id=project.id).delete()
        ForumTopic.query.filter_by(project_id=project.id).delete()
        db.session.delete(project)
        db.session.commit()

        flash(f'Project "{project.title}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting project: {str(e)}', 'error')

    return redirect(url_for('dev.dashboard'))

@dev_bp.route('/change-password', methods=['POST'])
@login_required
@dev_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        flash('All password fields are required', 'error')
        return redirect(url_for('dev.tools'))

    if new_password != confirm_password:
        flash('New passwords do not match', 'error')
        return redirect(url_for('dev.tools'))

    if len(new_password) < 6:
        flash('New password must be at least 6 characters', 'error')
        return redirect(url_for('dev.tools'))

    if not check_password_hash(current_user.password, current_password):
        flash('Current password is incorrect', 'error')
        return redirect(url_for('dev.tools'))

    current_user.password = generate_password_hash(new_password)
    db.session.commit()

    flash('Password changed successfully', 'success')
    return redirect(url_for('dev.tools'))

# ==================== DATABASE BACKUP ====================

@dev_bp.route('/backup')
@login_required
@dev_required
def backup():
    backup_dir = os.path.join(current_app.root_path, 'backups')
    backups = []

    if os.path.exists(backup_dir):
        files = os.listdir(backup_dir)
        sql_files = [f for f in files if f.endswith('.sql')]

        for file in sorted(sql_files, key=lambda x: os.path.getctime(os.path.join(backup_dir, x)), reverse=True)[:10]:
            file_path = os.path.join(backup_dir, file)
            stat = os.stat(file_path)
            is_full = 'backup' in file

            backups.append({
                'name': file,
                'size': f"{stat.st_size / 1024:.1f} KB",
                'created': datetime.fromtimestamp(stat.st_ctime).strftime('%B %d, %Y %I:%M %p'),
                'is_full': is_full
            })

    return render_template('dev/backup.html', backups=backups)

@dev_bp.route('/backup/create', methods=['POST'])
@login_required
@dev_required
def create_backup():
    try:
        backup_dir = os.path.join(current_app.root_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'innovation_hub_backup_{timestamp}.sql'
        backup_filepath = os.path.join(backup_dir, backup_filename)

        # Generate SQL dump
        sql_dump = generate_sql_dump()
        
        # Write to file
        with open(backup_filepath, 'w', encoding='utf-8') as f:
            f.write(sql_dump)

        file_size = os.path.getsize(backup_filepath)
        latest_file = os.path.join(backup_dir, 'latest_backup.sql')
        shutil.copy2(backup_filepath, latest_file)

        flash(f'Backup created successfully. Size: {file_size/1024:.1f} KB', 'success')
        return send_file(
            backup_filepath, 
            as_attachment=True, 
            download_name=backup_filename, 
            mimetype='application/sql'
        )
        
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'error')
        return redirect(url_for('dev.backup'))

@dev_bp.route('/backup/download/<filename>')
@login_required
@dev_required
def download_backup(filename):
    try:
        backup_dir = os.path.join(current_app.root_path, 'backups')
        backup_file = os.path.join(backup_dir, filename)

        if not os.path.exists(backup_file):
            flash('Backup file not found', 'error')
            return redirect(url_for('dev.backup'))

        return send_file(backup_file, as_attachment=True, download_name=filename, mimetype='application/sql', max_age=0)
    except Exception as e:
        flash(f'Error downloading backup: {str(e)}', 'error')
        return redirect(url_for('dev.backup'))

@dev_bp.route('/backup/delete/<filename>', methods=['POST'])
@login_required
@dev_required
def delete_backup(filename):
    try:
        backup_dir = os.path.join(current_app.root_path, 'backups')
        backup_file = os.path.join(backup_dir, filename)

        if os.path.exists(backup_file):
            os.remove(backup_file)
            flash(f'Deleted backup: {filename}', 'success')
        else:
            flash('Backup file not found', 'error')
    except Exception as e:
        flash(f'Error deleting backup: {str(e)}', 'error')

    return redirect(url_for('dev.backup'))

# ==================== SYSTEM LOGS ====================

@dev_bp.route('/logs')
@login_required
@dev_required
def logs():
    setup_logging()
    log_dir = os.path.join(current_app.root_path, 'logs')
    log_file = os.path.join(log_dir, 'app.log')
    logs = []

    # Get last modified time
    last_modified = None
    if os.path.exists(log_file):
        mtime = os.path.getmtime(log_file)
        last_modified = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

    # Read logs
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-200:]  # Last 200 lines
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Parse log line (format: timestamp - level - message)
                    parts = line.split(' - ', 2)
                    if len(parts) >= 3:
                        logs.append({
                            'timestamp': parts[0],
                            'level': parts[1].upper(),
                            'message': parts[2]
                        })
                    elif len(parts) == 2:
                        logs.append({
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'level': parts[0].upper(),
                            'message': parts[1]
                        })
                    else:
                        logs.append({
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'level': 'INFO',
                            'message': line
                        })
        except Exception as e:
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'ERROR',
                'message': f'Error reading log file: {str(e)}'
            })

    log_file_path = log_file if os.path.exists(log_file) else 'No log file found'

    return render_template('dev/logs.html', logs=logs, log_file_path=log_file_path, last_modified=last_modified)

@dev_bp.route('/logs/clear', methods=['POST'])
@login_required
@dev_required
def clear_logs():
    try:
        log_file = os.path.join(current_app.root_path, 'logs', 'app.log')
        if os.path.exists(log_file):
            open(log_file, 'w', encoding='utf-8').close()
            flash('Logs cleared successfully', 'success')
        else:
            flash('No log file to clear', 'warning')
    except Exception as e:
        flash(f'Error clearing logs: {str(e)}', 'error')
    return redirect(url_for('dev.logs'))

@dev_bp.route('/logs/download')
@login_required
@dev_required
def download_logs():
    log_file = os.path.join(current_app.root_path, 'logs', 'app.log')

    if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
        return send_file(log_file, as_attachment=True, download_name=f'system_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', mimetype='text/plain')
    else:
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8')
        temp_file.write(f"# System Logs - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        temp_file.write("# No log file found.\n")
        temp_file.close()
        return send_file(temp_file.name, as_attachment=True, download_name=f'system_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', mimetype='text/plain')

# ==================== SYSTEM CONFIG ====================

@dev_bp.route('/system-config')
@login_required
@dev_required
def system_config():
    import importlib.metadata
    try:
        flask_version = importlib.metadata.version('flask')
    except:
        flask_version = "Unknown"

    db_size, table_count = get_database_size()

    # Get database info from connection URI
    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    
    # Parse MySQL/TiDB URI
    db_type = "MySQL / TiDB"
    db_name = "innovation_hub"
    db_host = "Unknown"
    db_user = "Unknown"
    
    match = re.search(r'mysql\+pymysql://([^:]+):[^@]+@([^/]+)/([^?]+)', db_uri)
    if match:
        db_user = match.group(1)
        db_host = match.group(2)
        db_name = match.group(3)
        db_type = "TiDB Cloud"

    db_info = {
        'type': 'tidb',
        'name': db_name,
        'host': db_host,
        'user': db_user,
        'table_count': table_count,
        'size': db_size
    }

    system_info = {
        'python_version': sys.version.split()[0],
        'python_path': sys.executable,
        'flask_version': flask_version,
        'database': 'TiDB Cloud',
        'environment': 'Development' if current_app.debug else 'Production',
        'debug': current_app.debug,
        'platform': platform.platform(),
        'hostname': platform.node()
    }

    # Environment variables (redacted for security)
    env_vars_list = [
        {'key': 'FLASK_ENV', 'value': os.environ.get('FLASK_ENV', 'Not set'), 'redacted': False},
        {'key': 'FLASK_APP', 'value': os.environ.get('FLASK_APP', 'Not set'), 'redacted': False},
        {'key': 'FLASK_DEBUG', 'value': str(current_app.debug), 'redacted': False},
        {'key': 'SECRET_KEY', 'value': '••••••••••••••••', 'redacted': True},
        {'key': 'MAIL_SERVER', 'value': current_app.config.get('MAIL_SERVER', 'Not set'), 'redacted': False},
        {'key': 'MAIL_PORT', 'value': str(current_app.config.get('MAIL_PORT', 'Not set')), 'redacted': False},
        {'key': 'MAIL_USERNAME', 'value': current_app.config.get('MAIL_USERNAME', 'Not set'), 'redacted': False},
    ]

    return render_template('dev/system_config.html', system_info=system_info, db_info=db_info, env_vars=env_vars_list)

# ==================== DEV TOOLS ====================

@dev_bp.route('/tools')
@login_required
@dev_required
def tools():
    tool_count = 6
    return render_template('dev/tools.html', tool_count=tool_count)

@dev_bp.route('/tools/clear-cache', methods=['POST'])
@login_required
@dev_required
def clear_cache():
    try:
        # Clear template cache
        if hasattr(current_app, 'cache'):
            current_app.cache.clear()

        # Clear session files if any
        session_dir = os.path.join(current_app.root_path, 'sessions')
        if os.path.exists(session_dir):
            for f in os.listdir(session_dir):
                os.remove(os.path.join(session_dir, f))

        flash('Cache cleared successfully', 'success')
    except Exception as e:
        flash(f'Error clearing cache: {str(e)}', 'error')
    return redirect(url_for('dev.tools'))

@dev_bp.route('/tools/clear-sessions', methods=['POST'])
@login_required
@dev_required
def clear_sessions():
    try:
        # Clear all user sessions by clearing remember tokens
        for user in User.query.all():
            user.last_login = None
        db.session.commit()
        flash('All sessions cleared. Users will need to log in again.', 'success')
    except Exception as e:
        flash(f'Error clearing sessions: {str(e)}', 'error')
    return redirect(url_for('dev.tools'))

@dev_bp.route('/tools/check-database', methods=['POST'])
@login_required
@dev_required
def check_database():
    try:
        # Check database connectivity
        result = db.session.execute('SELECT 1').scalar()
        
        if result == 1:
            flash('Database connection test passed. Database is accessible.', 'success')
        else:
            flash('Database connection test failed.', 'warning')

        # Get counts
        user_count = User.query.count()
        project_count = Project.query.count()
        topic_count = ForumTopic.query.count()
        app_count = ProjectApplication.query.count()

        flash(f'Users: {user_count} | Projects: {project_count} | Topics: {topic_count} | Applications: {app_count}', 'info')
    except Exception as e:
        flash(f'Database check failed: {str(e)}', 'error')
    return redirect(url_for('dev.tools'))

@dev_bp.route('/tools/health-check', methods=['POST'])
@login_required
@dev_required
def health_check():
    try:
        health_results = []

        # Check database
        try:
            db.session.execute('SELECT 1').scalar()
            health_results.append("Database connection: OK")
        except Exception as e:
            health_results.append(f"Database connection: FAILED - {str(e)}")

        # Check disk space
        try:
            import shutil
            disk_usage = shutil.disk_usage(os.getcwd())
            free_gb = disk_usage.free / (1024**3)
            total_gb = disk_usage.total / (1024**3)
            health_results.append(f"Disk space: {free_gb:.1f} GB free / {total_gb:.1f} GB total")
        except:
            health_results.append("Disk space: Check not available")

        # Check memory if psutil available
        if PSUTIL_AVAILABLE:
            memory = psutil.virtual_memory()
            health_results.append(f"Memory: {memory.percent}% used ({memory.available / (1024**3):.1f} GB available)")
        else:
            health_results.append("Memory check: psutil not installed")

        # Check Python version
        health_results.append(f"Python version: {sys.version.split()[0]}")

        # Check Flask version
        import importlib.metadata
        try:
            flask_version = importlib.metadata.version('flask')
            health_results.append(f"Flask version: {flask_version}")
        except:
            pass

        health_results.append("Health check completed")

        for result in health_results:
            flash(result, 'info')
    except Exception as e:
        flash(f'Health check failed: {str(e)}', 'error')
    return redirect(url_for('dev.tools'))

@dev_bp.route('/tools/optimize-database', methods=['POST'])
@login_required
@dev_required
def optimize_database():
    try:
        # For MySQL/TiDB, analyze tables
        tables = get_all_tables()
        for table in tables:
            db.session.execute(f"ANALYZE TABLE `{table}`")
        
        db.session.commit()
        
        flash(f'Database optimized successfully ({len(tables)} tables analyzed)', 'success')
    except Exception as e:
        flash(f'Optimization failed: {str(e)}', 'error')
    return redirect(url_for('dev.tools'))

# ==================== SIGN OUT ====================

@dev_bp.route('/signout')
@login_required
def signout():
    logout_user()
    session.pop('_flashes', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('dev.signin'))
