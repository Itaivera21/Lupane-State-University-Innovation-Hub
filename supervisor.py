from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from models import db, User, Project, ProjectApplication, ForumTopic, ForumPost, ChatMessage, ChatResource, Group, GroupMember
from datetime import datetime, timedelta

# Create supervisor blueprint - THIS MUST BE FIRST
supervisor_bp = Blueprint('supervisor', __name__, url_prefix='/supervisor')

# Supervisor required decorator
def supervisor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('Access denied. Supervisor privileges required.', 'error')
            return redirect(url_for('supervisor.signin'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== AUTHENTICATION ROUTES ====================

@supervisor_bp.route('/signin', methods=['GET', 'POST'])
def signin():
    """Supervisor sign in page"""
    if current_user.is_authenticated and current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if user and user.is_supervisor and check_password_hash(user.password, password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Welcome to Supervisor Portal', 'success')
            return redirect(url_for('supervisor.dashboard'))
        else:
            flash('Invalid supervisor credentials', 'error')
            return redirect(url_for('supervisor.signin'))

    return render_template('supervisor/supervisor_signin.html')

@supervisor_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Supervisor registration page"""
    if current_user.is_authenticated and current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))

    if request.method == 'POST':
        try:
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            email = request.form.get('email', '').strip()
            department = request.form.get('department', '').strip()
            specialization = request.form.get('specialization', '').strip()
            skills = request.form.get('skills', '').strip()
            bio = request.form.get('bio', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            terms = request.form.get('terms')

            # Validation
            if not all([first_name, last_name, email, department, password]):
                flash('All required fields must be filled', 'error')
                return redirect(url_for('supervisor.signup'))

            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return redirect(url_for('supervisor.signup'))

            if len(password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return redirect(url_for('supervisor.signup'))

            # Validate LSU email
            if not email.endswith('@lsu.ac.zw'):
                flash('Must use a valid @lsu.ac.zw email address', 'error')
                return redirect(url_for('supervisor.signup'))

            if not terms:
                flash('You must agree to the Terms of Service', 'error')
                return redirect(url_for('supervisor.signup'))

            # Check if email already exists
            existing = User.query.filter_by(email=email).first()
            if existing:
                flash('Email already registered', 'error')
                return redirect(url_for('supervisor.signup'))

            # Create username from first and last name
            username = f"{first_name} {last_name}"

            # Create new supervisor
            new_supervisor = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
                faculty=department,
                is_supervisor=True,
                is_admin=False,
                is_dev=False,
                first_name=first_name,
                last_name=last_name,
                department=department,
                specialization=specialization,
                bio=bio
            )

            if skills:
                skills_list = [s.strip() for s in skills.split(',') if s.strip()]
                new_supervisor.set_skills(skills_list)

            db.session.add(new_supervisor)
            db.session.commit()

            login_user(new_supervisor)

            flash('Supervisor account created successfully. Welcome to Innovation Hub.', 'success')
            return redirect(url_for('supervisor.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {str(e)}', 'error')
            return redirect(url_for('supervisor.signup'))

    return render_template('supervisor/supervisor_signup.html')

@supervisor_bp.route('/signout')
@login_required
def signout():
    """Sign out supervisor"""
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('supervisor.signin'))

# ==================== DASHBOARD ====================

@supervisor_bp.route('/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Supervisor dashboard"""
    supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()
    pending_requests = Project.query.filter_by(
        supervisor_id=current_user.id,
        status='pending_supervision'
    ).all()

    total_students = len(set([p.student_id for p in supervised_projects if p.student_id]))
    completed_count = sum(1 for p in supervised_projects if p.status == 'completed')
    completion_rate = int((completed_count / len(supervised_projects)) * 100) if supervised_projects else 0

    # Recent activity
    recent_activity = []
    for project in supervised_projects[:5]:
        recent_activity.append({
            'type': 'project',
            'title': f'Project: {project.title}',
            'status': project.status,
            'time': project.created_at
        })

    return render_template('supervisor/supervisor_dashboard.html',
        supervised_projects_count=len(supervised_projects),
        pending_requests_count=len(pending_requests),
        total_students=total_students,
        completion_rate=completion_rate,
        supervised_projects=supervised_projects[:5],
        recent_activity=recent_activity
    )

# ==================== PROJECT MANAGEMENT ====================

@supervisor_bp.route('/projects')
@login_required
@supervisor_required
def projects():
    """View all supervised projects"""
    supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()

    projects_data = []
    for project in supervised_projects:
        projects_data.append({
            'id': project.id,
            'title': project.title,
            'description': project.description[:150],
            'status': project.status,
            'team_size': project.team_size,
            'created_at': project.created_at,
            'student_name': project.student.get_full_name() if project.student else 'Unknown',
            'skills': project.get_skills()[:3]
        })

    return render_template('supervisor/supervisor_projects.html',
        projects=projects_data,
        total_projects=len(projects_data),
        active_projects=sum(1 for p in projects_data if p['status'] == 'active'),
        completed_projects=sum(1 for p in projects_data if p['status'] == 'completed')
    )

@supervisor_bp.route('/project/<int:project_id>')
@login_required
@supervisor_required
def project_detail(project_id):
    """View detailed project information"""
    project = Project.query.get_or_404(project_id)

    if project.supervisor_id != current_user.id:
        flash('You do not have access to this project', 'error')
        return redirect(url_for('supervisor.projects'))

    team_members = [project.student] if project.student else []
    applications = ProjectApplication.query.filter_by(project_id=project.id).all()

    return render_template('supervisor/supervisor_project_detail.html',
        project=project,
        team_members=team_members,
        applications=applications
    )

# ==================== SUPERVISION REQUESTS ====================

@supervisor_bp.route('/applications')
@login_required
@supervisor_required
def applications():
    """View all supervision requests for this supervisor"""
    # Get pending supervision requests
    pending_projects = Project.query.filter_by(
        supervisor_id=current_user.id,
        status='pending_supervision'
    ).all()

    # Get approved projects (active ones)
    approved_projects = Project.query.filter_by(
        supervisor_id=current_user.id,
        status='active'
    ).all()

    # Get rejected projects (none for now, but we'll show them as rejected if they had supervision removed)
    rejected_projects = []

    # Get completed projects
    completed_projects = Project.query.filter_by(
        supervisor_id=current_user.id,
        status='completed'
    ).all()

    # Build applications list for the template
    applications = []

    # Add pending applications
    for project in pending_projects:
        applications.append({
            'id': project.id,
            'project': project,
            'student': project.student,
            'status': 'pending',
            'requested_at': project.supervision_requested_at,
            'message': ''
        })

    # Add approved projects
    for project in approved_projects:
        applications.append({
            'id': project.id,
            'project': project,
            'student': project.student,
            'status': 'approved',
            'requested_at': project.supervision_approved_at,
            'message': ''
        })

    # Add completed projects
    for project in completed_projects:
        applications.append({
            'id': project.id,
            'project': project,
            'student': project.student,
            'status': 'approved',
            'requested_at': project.completed_at,
            'message': ''
        })

    # Counts
    pending_count = len(pending_projects)
    approved_count = len(approved_projects) + len(completed_projects)
    rejected_count = len(rejected_projects)

    return render_template('supervisor/supervisor_applications.html',
        applications=applications,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count
    )

@supervisor_bp.route('/approve_request/<int:request_id>', methods=['POST'])
@login_required
@supervisor_required
def approve_request(request_id):
    """Approve a supervision request"""
    project = Project.query.get_or_404(request_id)

    if project.supervisor_id != current_user.id:
        flash('You are not authorized to approve this request', 'error')
        return redirect(url_for('supervisor.applications'))

    if project.status != 'pending_supervision':
        flash('This project is not pending supervision', 'error')
        return redirect(url_for('supervisor.applications'))

    project.status = 'active'
    project.supervision_approved_at = datetime.utcnow()
    db.session.commit()

    # Add supervisor to the group
    group = Group.query.filter_by(project_id=project.id).first()
    if group:
        # Check if already a member
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
            flash(f'Supervision approved for project: {project.title}. You have been added to the project chat.', 'success')
        else:
            flash(f'Supervision approved for project: {project.title}', 'success')
    else:
        flash(f'Supervision approved for project: {project.title}', 'success')

    return redirect(url_for('supervisor.applications'))

@supervisor_bp.route('/reject_request/<int:request_id>', methods=['POST'])
@login_required
@supervisor_required
def reject_request(request_id):
    """Reject a supervision request"""
    project = Project.query.get_or_404(request_id)

    if project.supervisor_id != current_user.id:
        flash('You are not authorized to reject this request', 'error')
        return redirect(url_for('supervisor.applications'))

    if project.status != 'pending_supervision':
        flash('This project is not pending supervision', 'error')
        return redirect(url_for('supervisor.applications'))

    # Remove supervisor assignment
    project.supervisor_id = None
    project.status = 'active'
    project.supervision_requested_at = None
    db.session.commit()

    flash(f'Supervision request rejected for project: {project.title}', 'warning')
    return redirect(url_for('supervisor.applications'))

# ==================== PROJECT STATUS MANAGEMENT ====================

@supervisor_bp.route('/project/<int:project_id>/mark-complete', methods=['POST'])
@login_required
@supervisor_required
def mark_project_complete(project_id):
    """Mark a supervised project as completed"""
    project = Project.query.get_or_404(project_id)

    if project.supervisor_id != current_user.id:
        flash('You do not have permission to modify this project', 'error')
        return redirect(url_for('supervisor.projects'))

    if project.status != 'active':
        flash('Only active projects can be marked as completed', 'error')
        return redirect(url_for('supervisor.projects'))

    project.status = 'completed'
    project.completed_at = datetime.utcnow()
    db.session.commit()

    flash(f'Project "{project.title}" marked as completed', 'success')
    return redirect(url_for('supervisor.project_detail', project_id=project_id))

@supervisor_bp.route('/project/<int:project_id>/mark-active', methods=['POST'])
@login_required
@supervisor_required
def mark_project_active(project_id):
    """Mark a completed project as active again"""
    project = Project.query.get_or_404(project_id)

    if project.supervisor_id != current_user.id:
        flash('You do not have permission to modify this project', 'error')
        return redirect(url_for('supervisor.projects'))

    if project.status != 'completed':
        flash('Only completed projects can be marked as active', 'error')
        return redirect(url_for('supervisor.projects'))

    project.status = 'active'
    project.completed_at = None
    db.session.commit()

    flash(f'Project "{project.title}" marked as active again', 'success')
    return redirect(url_for('supervisor.project_detail', project_id=project_id))

# ==================== PROFILE MANAGEMENT ====================

@supervisor_bp.route('/profile')
@login_required
@supervisor_required
def profile():
    """View and edit supervisor profile"""
    return render_template('supervisor/supervisor_profile.html', user=current_user)

@supervisor_bp.route('/profile/update', methods=['POST'])
@login_required
@supervisor_required
def update_profile():
    """Update supervisor profile information"""
    try:
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        department = request.form.get('department', '').strip()
        specialization = request.form.get('specialization', '').strip()
        skills = request.form.get('skills', '').strip()
        bio = request.form.get('bio', '').strip()

        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.username = f"{first_name} {last_name}"
        current_user.department = department
        current_user.specialization = specialization
        current_user.bio = bio
        current_user.faculty = department

        if skills:
            skills_list = [s.strip() for s in skills.split(',') if s.strip()]
            current_user.set_skills(skills_list)
        else:
            current_user.set_skills([])

        db.session.commit()
        flash('Profile updated successfully', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'error')

    return redirect(url_for('supervisor.profile'))

# ==================== VIEW SUPERVISOR PROFILE (PUBLIC) ====================

@supervisor_bp.route('/profile/<int:supervisor_id>')
def view_profile(supervisor_id):
    """Public view of supervisor profile"""
    supervisor = User.query.get_or_404(supervisor_id)

    if not supervisor.is_supervisor:
        flash('User is not a supervisor', 'error')
        return redirect(url_for('index'))

    supervised_projects = Project.query.filter(
        Project.supervisor_id == supervisor.id,
        Project.status.in_(['active', 'completed'])
    ).all()

    return render_template('supervisor/public_profile.html',
        supervisor=supervisor,
        supervised_projects=supervised_projects
    )

# ==================== CHANGE PASSWORD ====================

@supervisor_bp.route('/change-password', methods=['POST'])
@login_required
@supervisor_required
def change_password():
    """Change supervisor password"""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        flash('All password fields are required', 'error')
        return redirect(url_for('supervisor.profile'))

    if new_password != confirm_password:
        flash('New passwords do not match', 'error')
        return redirect(url_for('supervisor.profile'))

    if len(new_password) < 6:
        flash('New password must be at least 6 characters', 'error')
        return redirect(url_for('supervisor.profile'))

    if not check_password_hash(current_user.password, current_password):
        flash('Current password is incorrect', 'error')
        return redirect(url_for('supervisor.profile'))

    current_user.password = generate_password_hash(new_password)
    db.session.commit()

    flash('Password changed successfully', 'success')
    return redirect(url_for('supervisor.profile'))

# ==================== CHAT AND MESSAGING ====================

@supervisor_bp.route('/chats')
@login_required
@supervisor_required
def chats():
    """View all project chats for supervised projects"""
    project_id = request.args.get('project_id', type=int)
    supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()

    # Build project chats list with unread counts
    project_chats = []
    for project in supervised_projects:
        unread_count = ChatMessage.query.filter(
            ChatMessage.project_id == project.id,
            ChatMessage.is_read == False,
            ChatMessage.sender_id != current_user.id
        ).count()

        project_chats.append({
            'project': project,
            'unread_count': unread_count
        })

    current_project = None
    messages = []

    if project_id:
        current_project = Project.query.get_or_404(project_id)
        # Verify supervisor has access to this project
        if current_project.supervisor_id != current_user.id:
            flash('You do not have access to this chat', 'error')
            return redirect(url_for('supervisor.chats'))

        # Get messages for this project
        messages = ChatMessage.query.filter_by(project_id=project_id).order_by(ChatMessage.created_at).all()

        # Mark messages as read
        ChatMessage.query.filter_by(
            project_id=project_id,
            is_read=False
        ).filter(ChatMessage.sender_id != current_user.id).update({'is_read': True})
        db.session.commit()

    return render_template('supervisor/supervisor_chats.html',
        project_chats=project_chats,
        current_project=current_project,
        messages=messages
    )

# ==================== STATISTICS & REPORTS ====================

@supervisor_bp.route('/statistics')
@login_required
@supervisor_required
def statistics():
    """View statistics for supervised projects"""
    supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()

    total_projects = len(supervised_projects)
    active_projects = sum(1 for p in supervised_projects if p.status == 'active')
    completed_projects = sum(1 for p in supervised_projects if p.status == 'completed')
    pending_projects = sum(1 for p in supervised_projects if p.status == 'pending_supervision')

    completion_rate = int((completed_projects / total_projects) * 100) if total_projects > 0 else 0

    student_ids = set()
    for p in supervised_projects:
        if p.student_id:
            student_ids.add(p.student_id)
    total_students = len(student_ids)

    categories = {}
    for project in supervised_projects:
        cat = project.category or 'Uncategorized'
        categories[cat] = categories.get(cat, 0) + 1

    from collections import defaultdict
    monthly_projects = defaultdict(int)
    for project in supervised_projects:
        if project.created_at:
            month_key = project.created_at.strftime('%b %Y')
            monthly_projects[month_key] += 1

    return render_template('supervisor/supervisor_statistics.html',
        total_projects=total_projects,
        active_projects=active_projects,
        completed_projects=completed_projects,
        pending_projects=pending_projects,
        completion_rate=completion_rate,
        total_students=total_students,
        categories=categories,
        monthly_projects=dict(monthly_projects)
    )
