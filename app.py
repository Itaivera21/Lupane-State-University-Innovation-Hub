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
app.config['SECRET_KEY'] = 'your-secret-key-here'

# ============ SQLITE DATABASE CONFIGURATION ============
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///innovation_hub.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
}
# ================================================

# Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'itaivera21@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password-here'
app.config['MAIL_DEFAULT_SENDER'] = 'itaivera21@gmail.com'

# Initialize extensions
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

print("Initializing mail...")
mail = Mail(app)
print("Mail initialized")

print("Initializing login manager...")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.signin'
print("Login manager initialized")

# Register blueprints
print("Registering blueprints...")
app.register_blueprint(dashboard_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(dev_bp)
app.register_blueprint(supervisor_bp)
print("Blueprints registered")

@app.errorhandler(Exception)
def handle_error(error):
    print(f"Route error: {type(error).__name__}: {error}")
    traceback.print_exc()
    return f"Error: {error}", 500

def generate_project_id():
    year = datetime.now().year
    random_part = ''.join(secrets.choice(string.digits) for _ in range(4))
    return f"PRJ-{year}-{random_part}"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== PUBLIC ROUTES ====================

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
    """Public view of completed project for portfolio"""
    try:
        project = Project.query.get_or_404(project_id)

        # Only allow viewing completed projects
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


# ==================== PUBLIC ANNOUNCEMENTS API ====================

@app.route('/api/announcements')
def get_public_announcements():
    """Get announcements for landing page (public access, no login required)"""
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


# ==================== DOWNLOAD ANNOUNCEMENT ATTACHMENT ====================

@app.route('/api/download-announcement/<int:announcement_id>')
def download_announcement(announcement_id):
    """Download announcement attachment (public access)"""
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


# ==================== PROJECT ROUTES ====================

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

            # Create group for the project and add project owner
            new_group = Group(
                name=f"{title} Chat Group",
                project_id=new_project.id
            )
            db.session.add(new_group)
            db.session.flush()

            # Add project owner to group
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
    try:
        category = request.args.get('category')
        filter_type = request.args.get('filter', 'all')

        if filter_type == 'recommended' and current_user.is_authenticated:
            user_skills = current_user.get_skills()
            if user_skills:
                all_projects = Project.query.filter_by(status='active').all()
                matched_projects = []
                for project in all_projects:
                    project_skills = project.get_skills()
                    if project_skills and set(user_skills) & set(project_skills):
                        matched_projects.append(project)
                projects = matched_projects
            else:
                projects = Project.query.filter_by(status='active').order_by(Project.created_at.desc()).all()
        elif filter_type == 'pending_supervision' and current_user.is_supervisor:
            projects = Project.query.filter_by(
                supervisor_id=current_user.id,
                status='pending_supervision'
            ).all()
        elif filter_type == 'my_supervised' and current_user.is_supervisor:
            projects = Project.query.filter_by(
                supervisor_id=current_user.id,
                status='active'
            ).all()
        else:
            query = Project.query.filter_by(status='active')
            if category:
                query = query.filter_by(category=category)
            projects = query.order_by(Project.created_at.desc()).all()
    except:
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
        import traceback
        traceback.print_exc()
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

        if project.status != 'completed':
            flash('Only completed projects can be marked as active', 'warning')
            return redirect(url_for('project_detail', project_id=project.id))

        project.status = 'active'
        project.completed_at = None
        db.session.commit()

        flash('Project marked as active again.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('project_detail', project_id=project_id))

@app.route('/project/<int:project_id>/request-supervisor', methods=['POST'])
@login_required
def request_supervisor(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        supervisor_id = request.form.get('supervisor_id')
        message = request.form.get('message', '')

        if project.student_id != current_user.id:
            flash('You do not have permission to request supervision for this project', 'error')
            return redirect(url_for('project_detail', project_id=project.id))

        if project.supervisor_id:
            flash('This project already has a supervisor', 'warning')
            return redirect(url_for('project_detail', project_id=project.id))

        if not supervisor_id:
            flash('Please select a supervisor', 'error')
            return redirect(url_for('project_detail', project_id=project.id))

        supervisor = User.query.get(supervisor_id)
        if not supervisor or not supervisor.is_supervisor:
            flash('Invalid supervisor selected', 'error')
            return redirect(url_for('project_detail', project_id=project.id))

        project.supervisor_id = supervisor_id
        project.status = 'pending_supervision'
        project.supervision_requested_at = datetime.utcnow()
        db.session.commit()

        flash(f'Supervision request sent to {supervisor.get_full_name()}', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')

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

            # Add the approved applicant to the group
            group = Group.query.filter_by(project_id=application.project_id).first()
            if group:
                # Check if already a member
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
    app.run(debug=True)
