from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from models import db, User, Project, ProjectApplication, ForumTopic, ForumPost, ChatMessage, ChatResource, Group, GroupMember, Announcement
from datetime import datetime
import json
import secrets
import string
import os
import sys
import traceback
import ssl
from functools import wraps
from werkzeug.security import generate_password_hash

# ============ GLOBAL EXCEPTION HANDLER ============
def global_exception_handler(exctype, value, tb):
    print("=" * 80)
    print("UNCAUGHT EXCEPTION DETECTED")
    print(f"Type: {exctype.__name__}")
    print(f"Value: {value}")
    print("\nFull Traceback:")
    traceback.print_tb(tb)
    print("=" * 80)
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_exception_handler

# Import your blueprints
from dashboard import dashboard_bp
from chat import chat_bp
from auth import auth_bp
from admin import admin_bp
from dev import dev_bp
from supervisor import supervisor_bp

app = Flask(__name__)

# ============ SECURE CONFIGURATION ============
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Session security
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# ============ TiDB CLOUD DATABASE CONFIGURATION ============
DB_USER = os.environ.get('DB_USER', 'Zs51ycD7dYgEUy3.root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'qar204jhgxpJE2sB')
DB_HOST = os.environ.get('DB_HOST', 'gateway01.eu-central-1.prod.aws.tidbcloud.com')
DB_PORT = os.environ.get('DB_PORT', '4000')
DB_NAME = os.environ.get('DB_NAME', 'innovation_hub')

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SSL configuration for pymysql
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
    'connect_args': {
        'ssl': {
            'ssl': True
        }
    }
}

# ============ FLASK-MAIL CONFIGURATION ============
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@innovationhub.com')

# ============ FILE UPLOAD CONFIGURATION ============
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')

# ============ INITIALIZE EXTENSIONS ============
print("Starting application initialization...")

try:
    print("Initializing database...")
    db.init_app(app)
    print("db.init_app() successful")

    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Database tables ready")

        print("Testing database connection...")
        result = db.session.execute(db.text("SELECT 1")).scalar()
        print(f"Database connection test successful: {result}")

        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Existing tables: {tables}")

except Exception as e:
    print(f"Database initialization error: {type(e).__name__}: {e}")
    traceback.print_exc()

# Flask-Mail is optional - handle gracefully
try:
    mail = Mail(app)
    print("Mail initialized")
except Exception as e:
    print(f"Mail initialization skipped: {e}")
    mail = None

print("Initializing login manager...")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.signin'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'
print("Login manager initialized")

# ============ REGISTER BLUEPRINTS ============
print("Registering blueprints...")
app.register_blueprint(dashboard_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(dev_bp)
app.register_blueprint(supervisor_bp)
print("Blueprints registered")

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found'}), 404
    return "Page not found", 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return "Server error", 500

@app.errorhandler(Exception)
def handle_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': str(error)}), 500
    return str(error), 500

# ============ HELPER FUNCTIONS ============

def generate_project_id():
    year = datetime.now().year
    random_part = ''.join(secrets.choice(string.digits) for _ in range(4))
    return f"PRJ-{year}-{random_part}"

def is_approved_member(user_id, project_id):
    """Check if user is already a member of the project"""
    project = Project.query.get(project_id)
    if project and project.student_id == user_id:
        return True
    if project and project.supervisor_id == user_id:
        return True
    approved_app = ProjectApplication.query.filter_by(
        project_id=project_id,
        applicant_id=user_id,
        status='approved'
    ).first()
    return approved_app is not None

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except:
        return None

# ============ PUBLIC ROUTES ============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/portfolio')
def portfolio():
    try:
        completed_projects = Project.query.filter_by(status='completed').all()
    except:
        completed_projects = []
    return render_template('portfolio.html', projects=completed_projects)

@app.route('/portfolio/project/<int:project_id>')
def portfolio_detail(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        if project.status != 'completed':
            flash('This project is not available for public viewing', 'error')
            return redirect(url_for('portfolio'))
        return render_template('portfolio_detail.html', project=project)
    except Exception as e:
        print(f"Error in portfolio_detail: {e}")
        flash('Project not found', 'error')
        return redirect(url_for('portfolio'))

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

# ============ PUBLIC ANNOUNCEMENTS API ============

@app.route('/api/announcements')
def get_public_announcements():
    try:
        announcements = Announcement.query.order_by(
            Announcement.is_pinned.desc(),
            Announcement.created_at.desc()
        ).limit(5).all()
        data = []
        for ann in announcements:
            data.append({
                'id': ann.id,
                'title': ann.title,
                'content': ann.content,
                'is_pinned': ann.is_pinned,
                'attachment_filename': ann.attachment_filename,
                'created_at': ann.created_at.strftime('%b %d, %Y') if ann.created_at else 'Recently'
            })
        return jsonify(data)
    except Exception as e:
        print(f"Error fetching announcements: {e}")
        return jsonify([])

# ============ DOWNLOAD ANNOUNCEMENT ATTACHMENT ============

@app.route('/api/download-announcement/<int:announcement_id>')
def download_announcement(announcement_id):
    try:
        announcement = Announcement.query.get_or_404(announcement_id)
        if not announcement.attachment_path or not os.path.exists(announcement.attachment_path):
            flash('File not found', 'error')
            return redirect(url_for('index'))
        return send_file(
            announcement.attachment_path,
            as_attachment=True,
            download_name=announcement.attachment_filename
        )
    except Exception as e:
        print(f"Error downloading attachment: {e}")
        flash('Error downloading file', 'error')
        return redirect(url_for('index'))

# ============ PROJECT ROUTES ============

@app.route('/create-project', methods=['GET', 'POST'])
@login_required
def create_project():
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            team_size = request.form.get('team_size')
            duration = request.form.get('duration')
            category = request.form.get('category')
            roles = request.form.get('roles')
            additional_details = request.form.get('additional_details')
            skills_input = request.form.get('skills', '')
            skills_required = [s.strip() for s in skills_input.split(',') if s.strip()]
            
            if not title or not description or not team_size:
                flash('Please fill in all required fields', 'error')
                return redirect(url_for('create_project'))
            
            new_project = Project(
                project_id=generate_project_id(),
                title=title,
                description=description,
                team_size=int(team_size),
                duration=duration,
                category=category,
                roles=roles,
                additional_details=additional_details,
                student_id=current_user.id,
                status='active'
            )
            new_project.set_skills(skills_required)
            db.session.add(new_project)
            db.session.flush()
            
            new_group = Group(
                name=f"{title} Chat Group",
                project_id=new_project.id
            )
            db.session.add(new_group)
            db.session.flush()
            
            group_member = GroupMember(
                group_id=new_group.id,
                user_id=current_user.id,
                is_muted=False
            )
            db.session.add(group_member)
            db.session.commit()
            
            flash(f'Project created successfully. Project ID: {new_project.project_id}', 'success')
            return redirect(url_for('project_detail', project_id=new_project.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating project: {str(e)}', 'error')
            return redirect(url_for('create_project'))
    return render_template('create_project.html')

@app.route('/projects')
def projects():
    """Show all projects that are visible to students - includes active and pending_supervision"""
    try:
        category = request.args.get('category')
        filter_type = request.args.get('filter', 'all')
        
        # Base query shows both active AND pending_supervision projects
        base_query = Project.query.filter(Project.status.in_(['active', 'pending_supervision']))
        
        # For recommended filter (logged in users only)
        if filter_type == 'recommended' and current_user.is_authenticated:
            user_skills = current_user.get_skills()
            if user_skills:
                all_projects = base_query.all()
                matched_projects = []
                for project in all_projects:
                    project_skills = project.get_skills()
                    if project_skills and set(user_skills) & set(project_skills):
                        matched_projects.append(project)
                projects = matched_projects
            else:
                projects = base_query.order_by(Project.created_at.desc()).all()
        
        # FIXED: For pending supervision filter, use requested_supervisor_id
        elif filter_type == 'pending_supervision' and current_user.is_authenticated and current_user.is_supervisor:
            projects = Project.query.filter_by(
                requested_supervisor_id=current_user.id,
                status='pending_supervision'
            ).all()
        
        # For my supervised filter (supervisors only) - supervisor_id is correct here (approved)
        elif filter_type == 'my_supervised' and current_user.is_authenticated and current_user.is_supervisor:
            projects = Project.query.filter_by(
                supervisor_id=current_user.id,
                status='active'
            ).all()
        
        # Default: show all active and pending_supervision projects (visible to everyone)
        else:
            if category:
                projects = base_query.filter_by(category=category).order_by(Project.created_at.desc()).all()
            else:
                projects = base_query.order_by(Project.created_at.desc()).all()
        
    except Exception as e:
        print(f"Error in projects route: {e}")
        projects = []
    
    return render_template('projects.html', projects=projects)

@app.route('/project/<int:project_id>')
def project_detail(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        supervisors = User.query.filter_by(is_supervisor=True).all()
        has_applied = False
        if current_user.is_authenticated:
            application = ProjectApplication.query.filter_by(
                applicant_id=current_user.id,
                project_id=project_id
            ).first()
            has_applied = application is not None
        return render_template('project_detail.html',
                             project=project,
                             supervisors=supervisors,
                             has_applied=has_applied)
    except Exception as e:
        print(f"Error in project_detail: {e}")
        flash('Project not found', 'error')
        return redirect(url_for('projects'))

@app.route('/project/<int:project_id>/apply', methods=['POST'])
@login_required
def apply_to_project(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        existing = ProjectApplication.query.filter_by(
            applicant_id=current_user.id,
            project_id=project_id
        ).first()
        if existing:
            flash('You have already applied to this project', 'warning')
            return redirect(url_for('project_detail', project_id=project_id))
        
        message = request.form.get('message', '')
        application = ProjectApplication(
            applicant_id=current_user.id,
            project_id=project_id,
            message=message,
            status='pending'
        )
        db.session.add(application)
        db.session.commit()
        flash('Application submitted successfully. The project creator will review it.', 'success')
    except Exception as e:
        flash(f'Error applying to project: {str(e)}', 'error')
    return redirect(url_for('project_detail', project_id=project_id))

# ==================== PROJECT STATUS MANAGEMENT ====================

@app.route('/project/<int:project_id>/mark-complete', methods=['POST'])
@login_required
def mark_project_complete(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        if project.student_id != current_user.id:
            flash('You do not have permission to modify this project', 'error')
            return redirect(url_for('project_detail', project_id=project.id))
        if project.status == 'completed':
            flash('Project is already completed', 'warning')
            return redirect(url_for('project_detail', project_id=project.id))
        
        project.status = 'completed'
        project.completed_at = datetime.utcnow()
        db.session.commit()
        flash('Project marked as completed. It will appear in the portfolio.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('project_detail', project_id=project_id))

@app.route('/project/<int:project_id>/mark-active', methods=['POST'])
@login_required
def mark_project_active(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        if project.student_id != current_user.id:
            flash('You do not have permission to modify this project', 'error')
            return redirect(url_for('project_detail', project_id=project.id))
        
        if project.status not in ['completed', 'pending_supervision']:
            flash('Only completed or pending supervision projects can be marked as active', 'warning')
            return redirect(url_for('project_detail', project_id=project.id))
        
        project.status = 'active'
        project.completed_at = None
        # Clear supervision fields if reverting from pending_supervision
        if project.requested_supervisor_id or (project.supervisor_id and project.supervision_approved_at is None):
            project.supervisor_id = None
            project.requested_supervisor_id = None
            project.supervision_requested_at = None
        db.session.commit()
        
        flash('Project marked as active again.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('project_detail', project_id=project_id))

# ==================== SUPERVISION REQUEST ====================

@app.route('/project/<int:project_id>/request-supervisor', methods=['POST'])
@login_required
def request_supervisor(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        # Renamed to avoid collision with model attribute
        selected_supervisor_id = request.form.get('supervisor_id')
        message = request.form.get('message', '')
        
        if project.student_id != current_user.id:
            flash('You do not have permission to request supervision for this project', 'error')
            return redirect(url_for('project_detail', project_id=project.id))
        
        if project.supervisor_id:
            flash('This project already has a supervisor', 'warning')
            return redirect(url_for('project_detail', project_id=project.id))
        
        if not selected_supervisor_id:
            flash('Please select a supervisor', 'error')
            return redirect(url_for('project_detail', project_id=project.id))
        
        # Cast to int explicitly to ensure correct type written to DB
        supervisor = User.query.get(int(selected_supervisor_id))
        if not supervisor or not supervisor.is_supervisor:
            flash('Invalid supervisor selected', 'error')
            return redirect(url_for('project_detail', project_id=project.id))
        
        # Store in requested_supervisor_id only — supervisor_id stays NULL until approved
        project.status = 'pending_supervision'
        project.requested_supervisor_id = int(selected_supervisor_id)
        project.supervision_requested_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'Supervision request sent to {supervisor.get_full_name()}. They will need to approve it.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('project_detail', project_id=project_id))

# ==================== SUPERVISOR APPROVAL ROUTE ====================

@app.route('/project/<int:project_id>/approve-supervision', methods=['POST'])
@login_required
def approve_supervision(project_id):
    """Supervisor approves a pending supervision request"""
    try:
        project = Project.query.get_or_404(project_id)
        
        if project.requested_supervisor_id != current_user.id:
            flash('You are not authorized to approve this supervision request', 'error')
            return redirect(url_for('dashboard.dashboard'))
        
        if project.status != 'pending_supervision':
            flash('This project is not pending supervision approval', 'warning')
            return redirect(url_for('dashboard.dashboard'))
        
        # Move requested_supervisor_id into supervisor_id now that it is approved
        project.supervisor_id = project.requested_supervisor_id
        project.requested_supervisor_id = None
        project.status = 'active'
        project.supervision_approved_at = datetime.utcnow()
        db.session.commit()
        
        # Add supervisor to the chat group
        group = Group.query.filter_by(project_id=project.id).first()
        if group:
            existing_member = GroupMember.query.filter_by(
                group_id=group.id,
                user_id=current_user.id
            ).first()
            if not existing_member:
                group_member = GroupMember(
                    group_id=group.id,
                    user_id=current_user.id,
                    is_muted=False
                )
                db.session.add(group_member)
                db.session.commit()
        
        flash(f'Supervision approved for project: {project.title}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('supervisor.dashboard'))

# ==================== CANCEL SUPERVISION REQUEST ====================

@app.route('/project/<int:project_id>/cancel-supervision', methods=['POST'])
@login_required
def cancel_supervision(project_id):
    """Student cancels a pending supervision request"""
    try:
        project = Project.query.get_or_404(project_id)
        
        if project.student_id != current_user.id:
            flash('You do not have permission to cancel this request', 'error')
            return redirect(url_for('project_detail', project_id=project.id))
        
        if project.status != 'pending_supervision':
            flash('This project does not have a pending supervision request', 'warning')
            return redirect(url_for('project_detail', project_id=project.id))
        
        project.status = 'active'
        project.requested_supervisor_id = None
        project.supervisor_id = None
        project.supervision_requested_at = None
        db.session.commit()
        
        flash('Supervision request cancelled successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error cancelling request: {str(e)}', 'error')
    
    return redirect(url_for('project_detail', project_id=project_id))

# ==================== APPLICATION MANAGEMENT ====================

@app.route('/manage-applications')
@login_required
def manage_applications():
    try:
        my_projects = Project.query.filter_by(student_id=current_user.id).all()
        project_ids = [p.id for p in my_projects]
        pending_applications = ProjectApplication.query.filter(
            ProjectApplication.project_id.in_(project_ids),
            ProjectApplication.status == 'pending'
        ).order_by(ProjectApplication.applied_at.desc()).all()
        approved_members = ProjectApplication.query.filter(
            ProjectApplication.project_id.in_(project_ids),
            ProjectApplication.status == 'approved'
        ).order_by(ProjectApplication.applied_at.desc()).all()
        user_projects = Project.query.filter_by(student_id=current_user.id).all()
        return render_template('manage_applications.html',
                             pending_applications=pending_applications,
                             approved_members=approved_members,
                             user_projects=user_projects)
    except Exception as e:
        flash(f'Error loading applications: {str(e)}', 'error')
        return redirect(url_for('dashboard.dashboard'))

@app.route('/application/<int:application_id>/handle', methods=['POST'])
@login_required
def handle_application(application_id):
    try:
        application = ProjectApplication.query.get_or_404(application_id)
        if application.project.student_id != current_user.id:
            flash('You do not have permission to do that', 'error')
            return redirect(url_for('manage_applications'))
        
        action = request.form.get('action')
        if action == 'approve':
            application.status = 'approved'
            application.approved_at = datetime.utcnow()
            db.session.commit()
            
            group = Group.query.filter_by(project_id=application.project_id).first()
            if group:
                existing_member = GroupMember.query.filter_by(
                    group_id=group.id,
                    user_id=application.applicant_id
                ).first()
                if not existing_member:
                    group_member = GroupMember(
                        group_id=group.id,
                        user_id=application.applicant_id,
                        is_muted=False
                    )
                    db.session.add(group_member)
                    db.session.commit()
                    flash(f'Application from {application.applicant.username} approved and added to chat.', 'success')
                else:
                    flash(f'Application from {application.applicant.username} approved. User already in chat.', 'success')
            else:
                flash(f'Application from {application.applicant.username} approved.', 'success')
        elif action == 'reject':
            application.status = 'rejected'
            db.session.commit()
            flash(f'Application from {application.applicant.username} rejected.', 'info')
        else:
            flash('Invalid action', 'error')
            return redirect(url_for('manage_applications'))
    except Exception as e:
        flash(f'Error handling application: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('manage_applications'))

@app.route('/application/<int:application_id>/cancel', methods=['POST'])
@login_required
def cancel_application(application_id):
    try:
        application = ProjectApplication.query.get_or_404(application_id)
        if application.applicant_id != current_user.id:
            flash('You do not have permission to cancel this application', 'error')
            return redirect(url_for('manage_applications'))
        if application.status != 'pending':
            flash('Only pending applications can be cancelled', 'error')
            return redirect(url_for('manage_applications'))
        
        db.session.delete(application)
        db.session.commit()
        flash('Application cancelled successfully', 'success')
    except Exception as e:
        flash(f'Error cancelling application: {str(e)}', 'error')
    return redirect(url_for('dashboard.dashboard'))

# ==================== FORUM ROUTES ====================

@app.route('/forum')
def forum():
    try:
        topics = ForumTopic.query.order_by(ForumTopic.created_at.desc()).all()
    except:
        topics = []
    return render_template('forum.html', topics=topics)

@app.route('/forum/create-topic', methods=['GET', 'POST'])
@login_required
def create_topic():
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            content = request.form.get('content')
            project_id = request.form.get('project_id')
            if not title or not content:
                flash('Title and content are required', 'error')
                return redirect(url_for('create_topic'))
            
            new_topic = ForumTopic(
                title=title,
                content=content,
                author_id=current_user.id,
                project_id=project_id if project_id else None
            )
            db.session.add(new_topic)
            db.session.commit()
            flash('Topic created successfully', 'success')
            return redirect(url_for('forum'))
        except Exception as e:
            flash(f'Error creating topic: {str(e)}', 'error')
            return redirect(url_for('create_topic'))
    
    try:
        projects = Project.query.filter_by(student_id=current_user.id).all()
    except:
        projects = []
    return render_template('create_topic.html', projects=projects)

@app.route('/forum/topic/<int:topic_id>', methods=['GET', 'POST'])
def view_topic(topic_id):
    try:
        topic = ForumTopic.query.get_or_404(topic_id)
    except:
        flash('Topic not found', 'error')
        return redirect(url_for('forum'))
    
    if request.method == 'POST' and current_user.is_authenticated:
        try:
            content = request.form.get('content')
            if content:
                new_post = ForumPost(
                    content=content,
                    author_id=current_user.id,
                    topic_id=topic_id
                )
                db.session.add(new_post)
                db.session.commit()
                flash('Reply posted successfully', 'success')
        except Exception as e:
            flash(f'Error posting reply: {str(e)}', 'error')
        return redirect(url_for('view_topic', topic_id=topic_id))
    
    return render_template('view_topic.html', topic=topic)

# ==================== CONTACT FORM ====================

@app.route('/send-contact', methods=['POST'])
def send_contact():
    try:
        name = request.form.get('name')
        organization = request.form.get('organization', 'Not provided')
        email = request.form.get('email')
        phone = request.form.get('phone', 'Not provided')
        inquiry_type = request.form.get('inquiry_type')
        message = request.form.get('message')
        
        if not name or not email or not inquiry_type or not message:
            flash('Please fill in all required fields', 'error')
            return redirect(url_for('contact'))
        
        flash('Thank you for your inquiry. We will get back to you soon.', 'success')
    except Exception as e:
        flash(f'Error sending message: {str(e)}', 'error')
    return redirect(url_for('contact'))

# ==================== API ENDPOINTS ====================

@app.route('/api/match-projects')
def match_projects():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        user_skills = set(current_user.get_skills())
        if not user_skills:
            return jsonify([])
        
        matches = []
        projects = Project.query.filter_by(status='active').all()
        for project in projects:
            project_skills = set(project.get_skills())
            common_skills = user_skills.intersection(project_skills)
            match_score = len(common_skills) / len(project_skills) if project_skills else 0
            if match_score > 0:
                matches.append({
                    'id': project.id,
                    'title': project.title,
                    'match_score': round(match_score * 100),
                    'common_skills': list(common_skills),
                    'project_id': project.project_id
                })
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        return jsonify(matches[:10])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== SUPERVISOR PROFILE VIEW (PUBLIC) ====================

@app.route('/supervisor/profile/<int:supervisor_id>')
def view_supervisor_profile(supervisor_id):
    try:
        supervisor = User.query.get_or_404(supervisor_id)
        if not supervisor.is_supervisor:
            flash('User is not a supervisor', 'error')
            return redirect(url_for('index'))
        
        supervised_projects = Project.query.filter_by(
            supervisor_id=supervisor.id,
            status='active'
        ).all()
        return render_template('supervisor/public_profile.html',
                             supervisor=supervisor,
                             supervised_projects=supervised_projects)
    except Exception as e:
        flash('Supervisor not found', 'error')
        return redirect(url_for('index'))

# ==================== CLI COMMANDS ====================

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized")

if __name__ == '__main__':
    app.run(debug=False)
