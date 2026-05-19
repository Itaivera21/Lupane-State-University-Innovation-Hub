from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from sqlalchemy import and_
from models import db, User, Project, ProjectApplication, ForumTopic, ForumPost, Announcement, SystemVariable, Group, GroupMember, ChatMessage, ChatResource
from datetime import datetime, timedelta
import secrets
import os
import uuid

# Create admin blueprint - THIS MUST BE FIRST
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Allowed file extensions for announcements
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('admin.signin'))
        return f(*args, **kwargs)
    return decorated_function

# Admin signin route
@admin_bp.route('/signin', methods=['GET', 'POST'])
def signin():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.is_admin and check_password_hash(user.password, password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Welcome to Admin Portal', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials', 'error')
            return redirect(url_for('admin.signin'))

    return render_template('admin/adminsignin.html')

# Admin dashboard
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_users = User.query.filter_by(is_dev=False).count()
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='active').count()
    pending_apps = ProjectApplication.query.filter_by(status='pending').count()
    completed_projects = Project.query.filter_by(status='completed').count()

    recent_projects = Project.query.order_by(Project.created_at.desc()).limit(5).all()

    recent_activity = []

    recent_users = User.query.filter_by(is_dev=False).order_by(User.created_at.desc()).limit(5).all()
    for user in recent_users:
        recent_activity.append({
            'type': 'user',
            'title': f'New user registered: {user.username}',
            'time': user.created_at
        })

    recent_projects_activity = Project.query.order_by(Project.created_at.desc()).limit(5).all()
    for project in recent_projects_activity:
        recent_activity.append({
            'type': 'project',
            'title': f'Project created: {project.title}',
            'time': project.created_at
        })

    recent_apps = ProjectApplication.query.order_by(ProjectApplication.applied_at.desc()).limit(5).all()
    for app in recent_apps:
        recent_activity.append({
            'type': 'application',
            'title': f'New application from {app.applicant.username}',
            'time': app.applied_at
        })

    recent_topics = ForumTopic.query.order_by(ForumTopic.created_at.desc()).limit(5).all()
    for topic in recent_topics:
        recent_activity.append({
            'type': 'topic',
            'title': f'New forum topic: {topic.title}',
            'time': topic.created_at
        })

    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:8]

    return render_template('admin/admindashboard.html',
        total_users=total_users,
        total_projects=total_projects,
        active_projects=active_projects,
        pending_apps=pending_apps,
        completed_projects=completed_projects,
        recent_projects=recent_projects,
        recent_activity=recent_activity
    )


# ==================== ANNOUNCEMENTS API ====================

@admin_bp.route('/api/announcements', methods=['GET'])
@login_required
@admin_required
def get_announcements():
    """Get all announcements for admin dashboard"""
    announcements = Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).all()

    data = []
    for ann in announcements:
        data.append({
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'is_pinned': ann.is_pinned,
            'attachment_filename': ann.attachment_filename,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M') if ann.created_at else 'Unknown',
            'created_by': ann.creator.username if ann.creator else 'Unknown'
        })

    return jsonify(data)

@admin_bp.route('/api/announcements', methods=['POST'])
@login_required
@admin_required
def create_announcement():
    """Create a new announcement"""
    title = request.form.get('title')
    content = request.form.get('content')
    is_pinned = request.form.get('is_pinned') == 'on'

    if not title or not content:
        return jsonify({'error': 'Title and content are required'}), 400

    # Handle file upload
    attachment_filename = None
    attachment_path = None
    attachment_size = None

    if 'attachment' in request.files:
        file = request.files['attachment']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"

            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'announcements')
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, unique_filename)
            file.save(file_path)

            file_size = os.path.getsize(file_path)
            size_kb = round(file_size / 1024, 1)
            attachment_size = f"{size_kb} KB" if size_kb < 1024 else f"{round(size_kb / 1024, 1)} MB"

            attachment_filename = filename
            attachment_path = file_path

    announcement = Announcement(
        title=title,
        content=content,
        is_pinned=is_pinned,
        attachment_filename=attachment_filename,
        attachment_path=attachment_path,
        attachment_size=attachment_size,
        created_by=current_user.id
    )

    db.session.add(announcement)
    db.session.commit()

    return jsonify({'success': True, 'id': announcement.id})

@admin_bp.route('/api/announcements/<int:announcement_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_announcement(announcement_id):
    """Delete an announcement"""
    announcement = Announcement.query.get_or_404(announcement_id)

    # Delete attachment file if exists
    if announcement.attachment_path and os.path.exists(announcement.attachment_path):
        try:
            os.remove(announcement.attachment_path)
        except:
            pass

    db.session.delete(announcement)
    db.session.commit()

    return jsonify({'success': True})

@admin_bp.route('/api/download-announcement/<int:announcement_id>')
def download_announcement(announcement_id):
    """Download announcement attachment (public access)"""
    announcement = Announcement.query.get_or_404(announcement_id)

    if not announcement.attachment_path or not os.path.exists(announcement.attachment_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        announcement.attachment_path,
        as_attachment=True,
        download_name=announcement.attachment_filename
    )


# ==================== PUBLIC ANNOUNCEMENTS API (for landing page) ====================

@admin_bp.route('/api/public/announcements', methods=['GET'])
def get_public_announcements():
    """Get announcements for landing page (public access, no login required)"""
    announcements = Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(5).all()

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


# ==================== USER MANAGEMENT ====================

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    filter_type = request.args.get('filter', 'all')
    search_query = request.args.get('search', '')

    query = User.query.filter_by(is_dev=False)

    if search_query:
        query = query.filter(
            (User.username.contains(search_query)) |
            (User.email.contains(search_query)) |
            (User.student_id.contains(search_query))
        )

    month_ago = datetime.utcnow() - timedelta(days=30)

    if filter_type == 'students':
        query = query.filter_by(is_admin=False, is_supervisor=False)
    elif filter_type == 'supervisors':
        query = query.filter_by(is_supervisor=True)
    elif filter_type == 'admins':
        query = query.filter_by(is_admin=True)
    elif filter_type == 'active':
        # FIXED: Handle None values in last_login
        query = query.filter(and_(User.last_login.isnot(None), User.last_login >= month_ago))
    elif filter_type == 'new':
        query = query.filter(User.created_at >= month_ago)

    users = query.order_by(User.created_at.desc()).all()

    total_users = User.query.filter_by(is_dev=False).count()
    total_admins = User.query.filter_by(is_admin=True, is_dev=False).count()
    total_supervisors = User.query.filter_by(is_supervisor=True, is_dev=False).count()
    total_students = total_users - total_admins - total_supervisors
    new_this_month = User.query.filter_by(is_dev=False).filter(User.created_at >= month_ago).count()

    return render_template('admin/usermanagement.html',
        users=users,
        total_users=total_users,
        total_admins=total_admins,
        total_supervisors=total_supervisors,
        total_students=total_students,
        new_this_month=new_this_month,
        current_filter=filter_type,
        search_query=search_query
    )

@admin_bp.route('/user/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)

    if user.is_dev:
        flash('Access denied. Cannot view developer accounts.', 'error')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_detail.html', user=user)

@admin_bp.route('/user/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    """Reset user password - accepts form data"""
    user = User.query.get_or_404(user_id)

    if user.is_dev:
        flash('Cannot reset password for developer accounts.', 'error')
        return redirect(url_for('admin.users'))

    # Get password from form data (not JSON)
    new_password = request.form.get('password')
    
    if not new_password:
        temp_password = secrets.token_urlsafe(8)
        new_password = temp_password
        user.password = generate_password_hash(temp_password)
    else:
        user.password = generate_password_hash(new_password)

    db.session.commit()
    
    flash(f'Password reset for {user.email}. New password: {new_password}', 'success')
    return redirect(url_for('admin.users'))

# ==================== FIXED DELETE USER FUNCTION ====================

@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.is_dev:
        flash('Cannot delete developer accounts.', 'error')
        return redirect(url_for('admin.users'))

    if user.id == current_user.id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('admin.users'))

    if user.is_admin:
        flash('Cannot delete other admin accounts. Use the Delete Admin button instead.', 'error')
        return redirect(url_for('admin.users'))

    try:
        # 1. Delete group memberships (critical - prevents foreign key errors)
        GroupMember.query.filter_by(user_id=user.id).delete()

        # 2. Delete chat resources uploaded by user
        ChatResource.query.filter_by(uploaded_by=user.id).delete()

        # 3. Delete applications
        ProjectApplication.query.filter_by(applicant_id=user.id).delete()

        # 4. Delete forum posts and topics
        ForumPost.query.filter_by(author_id=user.id).delete()
        ForumTopic.query.filter_by(author_id=user.id).delete()

        # 5. Delete chat messages
        ChatMessage.query.filter_by(sender_id=user.id).delete()

        # 6. Delete user's projects and related data
        user_projects = Project.query.filter_by(student_id=user.id).all()
        for project in user_projects:
            # Delete group for this project
            group = Group.query.filter_by(project_id=project.id).first()
            if group:
                GroupMember.query.filter_by(group_id=group.id).delete()
                db.session.delete(group)
            # Delete applications for the project
            ProjectApplication.query.filter_by(project_id=project.id).delete()
            # Delete chat messages for the project
            ChatMessage.query.filter_by(project_id=project.id).delete()
            # Delete chat resources for the project
            ChatResource.query.filter_by(project_id=project.id).delete()
            # Delete forum topics for the project
            ForumTopic.query.filter_by(project_id=project.id).delete()
            # Delete the project
            db.session.delete(project)

        # 7. Finally delete the user
        db.session.delete(user)
        db.session.commit()

        flash(f'User {user.email} and all associated data deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')

    return redirect(url_for('admin.users'))

@admin_bp.route('/user/<int:user_id>/delete-admin', methods=['POST'])
@login_required
@admin_required
def delete_admin(user_id):
    user = User.query.get_or_404(user_id)

    if not user.is_admin:
        flash('User is not an admin.', 'error')
        return redirect(url_for('admin.users'))

    if user.id == current_user.id:
        flash('Cannot delete your own admin account.', 'error')
        return redirect(url_for('admin.users'))

    if user.is_dev:
        flash('Cannot delete developer accounts.', 'error')
        return redirect(url_for('admin.users'))

    try:
        # Also need to clean up group memberships for admin
        GroupMember.query.filter_by(user_id=user.id).delete()
        ChatResource.query.filter_by(uploaded_by=user.id).delete()

        db.session.delete(user)
        db.session.commit()
        flash(f'Admin {user.email} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting admin: {str(e)}', 'error')

    return redirect(url_for('admin.users'))

# ==================== CREATE ADMIN ====================

@admin_bp.route('/create-admin', methods=['POST'])
@login_required
@admin_required
def create_admin():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')

    if not username or not email or not password:
        flash('All fields are required', 'error')
        return redirect(url_for('admin.dashboard'))

    existing = User.query.filter_by(email=email).first()
    if existing:
        flash('Email already exists', 'error')
        return redirect(url_for('admin.dashboard'))

    new_admin = User(
        username=username,
        email=email,
        password=generate_password_hash(password),
        faculty='Administration',
        student_id=f'ADMIN{secrets.randbelow(9000) + 1000}',
        is_admin=True,
        is_dev=False,
        is_supervisor=False
    )

    db.session.add(new_admin)
    db.session.commit()

    flash(f'Admin {username} created successfully!', 'success')
    return redirect(url_for('admin.dashboard'))

# ==================== PROJECT MANAGEMENT ====================

@admin_bp.route('/projects')
@login_required
@admin_required
def projects():
    filter_type = request.args.get('filter', 'all')

    query = Project.query

    if filter_type == 'active':
        query = query.filter_by(status='active')
    elif filter_type == 'pending':
        query = query.filter_by(status='pending')
    elif filter_type == 'completed':
        query = query.filter_by(status='completed')

    projects = query.order_by(Project.created_at.desc()).all()

    active_count = Project.query.filter_by(status='active').count()
    completed_count = Project.query.filter_by(status='completed').count()
    pending_count = Project.query.filter_by(status='pending').count()

    return render_template('admin/projects.html',
        projects=projects,
        active_count=active_count,
        completed_count=completed_count,
        pending_count=pending_count,
        current_filter=filter_type
    )

@admin_bp.route('/project/<int:project_id>')
@login_required
@admin_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    applications = ProjectApplication.query.filter_by(project_id=project_id).all()
    return render_template('admin/project_detail.html', project=project, applications=applications)

@admin_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)

    try:
        # Delete group for this project
        group = Group.query.filter_by(project_id=project_id).first()
        if group:
            GroupMember.query.filter_by(group_id=group.id).delete()
            db.session.delete(group)

        ProjectApplication.query.filter_by(project_id=project_id).delete()
        ChatMessage.query.filter_by(project_id=project_id).delete()
        ChatResource.query.filter_by(project_id=project_id).delete()
        ForumTopic.query.filter_by(project_id=project_id).delete()

        db.session.delete(project)
        db.session.commit()
        flash(f'Project "{project.title}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting project: {str(e)}', 'error')

    return redirect(url_for('admin.projects'))

# ==================== APPLICATION MANAGEMENT ====================

@admin_bp.route('/applications')
@login_required
@admin_required
def applications():
    filter_by = request.args.get('filter', 'all')

    query = ProjectApplication.query

    if filter_by == 'pending':
        query = query.filter_by(status='pending')
    elif filter_by == 'approved':
        query = query.filter_by(status='approved')
    elif filter_by == 'rejected':
        query = query.filter_by(status='rejected')

    applications = query.order_by(ProjectApplication.applied_at.desc()).all()

    total_applications = ProjectApplication.query.count()
    pending_count = ProjectApplication.query.filter_by(status='pending').count()
    approved_count = ProjectApplication.query.filter_by(status='approved').count()
    rejected_count = ProjectApplication.query.filter_by(status='rejected').count()

    return render_template('admin/applications.html',
        applications=applications,
        total_applications=total_applications,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        current_filter=filter_by
    )

@admin_bp.route('/application/<int:app_id>/handle', methods=['POST'])
@login_required
@admin_required
def handle_application(app_id):
    application = ProjectApplication.query.get_or_404(app_id)
    action = request.form.get('action')

    if action == 'approve':
        application.status = 'approved'
        flash('Application approved', 'success')
    elif action == 'reject':
        application.status = 'rejected'
        flash('Application rejected', 'success')
    else:
        flash('Invalid action', 'error')
        return redirect(url_for('admin.applications'))

    db.session.commit()
    return redirect(url_for('admin.applications'))

# ==================== FORUM MODERATION ====================

@admin_bp.route('/forum')
@login_required
@admin_required
def forum():
    topics = ForumTopic.query.order_by(ForumTopic.created_at.desc()).all()
    pinned_topics = ForumTopic.query.filter_by(is_pinned=True).order_by(ForumTopic.pinned_at.desc()).all()

    total_topics = ForumTopic.query.count()
    total_posts = ForumPost.query.count()
    reported_count = 0
    
    # FIXED: Handle None values in last_login for active users
    week_ago = datetime.utcnow() - timedelta(days=7)
    active_users = User.query.filter(
        and_(
            User.is_dev == False,
            User.last_login.isnot(None),
            User.last_login > week_ago
        )
    ).count()

    return render_template('admin/forum.html',
        topics=topics,
        pinned_topics=pinned_topics,
        reported_items=[],
        total_topics=total_topics,
        total_posts=total_posts,
        reported_count=reported_count,
        active_users=active_users
    )

@admin_bp.route('/forum/topic/<int:topic_id>/pin', methods=['POST'])
@login_required
@admin_required
def pin_topic(topic_id):
    topic = ForumTopic.query.get_or_404(topic_id)
    topic.is_pinned = True
    topic.pinned_at = datetime.utcnow()
    db.session.commit()
    flash(f'Topic "{topic.title}" pinned', 'success')
    return redirect(url_for('admin.forum'))

@admin_bp.route('/forum/topic/<int:topic_id>/unpin', methods=['POST'])
@login_required
@admin_required
def unpin_topic(topic_id):
    topic = ForumTopic.query.get_or_404(topic_id)
    topic.is_pinned = False
    topic.pinned_at = None
    db.session.commit()
    flash(f'Topic "{topic.title}" unpinned', 'success')
    return redirect(url_for('admin.forum'))

# FIXED: Corrected syntax error - changed methods(['POST']) to methods=['POST']
@admin_bp.route('/forum/topic/<int:topic_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_topic(topic_id):
    topic = ForumTopic.query.get_or_404(topic_id)
    title = topic.title
    db.session.delete(topic)
    db.session.commit()
    flash(f'Topic "{title}" deleted', 'success')
    return redirect(url_for('admin.forum'))

# ==================== SETTINGS ====================

@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    return render_template('admin/settings.html')

@admin_bp.route('/settings/general', methods=['POST'])
@login_required
@admin_required
def update_general_settings():
    site_name = request.form.get('site_name')
    site_description = request.form.get('site_description')
    contact_email = request.form.get('contact_email')

    # Store in system_variables table
    for key, value in [('site_name', site_name), ('site_description', site_description), ('contact_email', contact_email)]:
        var = SystemVariable.query.filter_by(key=key).first()
        if var:
            var.value = value
        else:
            var = SystemVariable(key=key, value=value)
            db.session.add(var)

    db.session.commit()
    flash('General settings updated successfully', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/registration', methods=['POST'])
@login_required
@admin_required
def update_registration_settings():
    allow_registration = request.form.get('allow_registration') == 'on'
    default_role = request.form.get('default_role')

    for key, value in [('allow_registration', str(allow_registration)), ('default_role', default_role)]:
        var = SystemVariable.query.filter_by(key=key).first()
        if var:
            var.value = value
        else:
            var = SystemVariable(key=key, value=value)
            db.session.add(var)

    db.session.commit()
    flash('Registration settings updated', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/email', methods=['POST'])
@login_required
@admin_required
def update_email_settings():
    flash('Email settings updated', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/security', methods=['POST'])
@login_required
@admin_required
def update_security_settings():
    flash('Security settings updated', 'success')
    return redirect(url_for('admin.settings'))

# ==================== CHANGE PASSWORD ====================

@admin_bp.route('/change-password', methods=['POST'])
@login_required
@admin_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        flash('All password fields are required', 'error')
        return redirect(url_for('admin.settings'))

    if new_password != confirm_password:
        flash('New passwords do not match', 'error')
        return redirect(url_for('admin.settings'))

    if len(new_password) < 6:
        flash('New password must be at least 6 characters', 'error')
        return redirect(url_for('admin.settings'))

    if not check_password_hash(current_user.password, current_password):
        flash('Current password is incorrect', 'error')
        return redirect(url_for('admin.settings'))

    current_user.password = generate_password_hash(new_password)
    db.session.commit()

    flash('Password changed successfully', 'success')
    return redirect(url_for('admin.settings'))

# ==================== SIGN OUT ====================

@admin_bp.route('/signout')
@login_required
def signout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin.signin'))
