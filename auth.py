# auth.py
# Handles user authentication (signup, signin, logout, profile) for Innovation Hub

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Project, ProjectApplication, Group, GroupMember
from datetime import datetime
import json
import re

# Create blueprint for auth routes
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Student user registration page"""
    if request.method == 'POST':
        try:
            # Get form data
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            email = request.form.get('email', '').strip()
            student_id = request.form.get('student_id', '').strip()
            faculty = request.form.get('faculty', '').strip()
            skills = request.form.get('skills', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Validation
            if not all([first_name, last_name, email, student_id, faculty, password]):
                flash('All required fields must be filled', 'error')
                return redirect(url_for('auth.signup'))
            
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return redirect(url_for('auth.signup'))
            
            if len(password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return redirect(url_for('auth.signup'))
            
            # Validate LSU email for students
            if not email.endswith('@lsu.ac.zw'):
                flash('Must use a valid @lsu.ac.zw email address', 'error')
                return redirect(url_for('auth.signup'))
            
            # Check if user already exists
            existing_user = User.query.filter(
                (User.email == email) | (User.student_id == student_id)
            ).first()
            
            if existing_user:
                flash('Email or Student ID already registered', 'error')
                return redirect(url_for('auth.signup'))
            
            # Create username from first and last name
            username = f"{first_name} {last_name}"
            
            # Create new student user
            new_user = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
                faculty=faculty,
                student_id=student_id,
                first_name=first_name,
                last_name=last_name,
                is_supervisor=False,
                is_admin=False,
                is_dev=False
            )
            
            # Set skills if any
            if skills:
                skills_list = [s.strip() for s in skills.split(',') if s.strip()]
                new_user.set_skills(skills_list)
            
            # Save to database
            db.session.add(new_user)
            db.session.commit()
            
            # Log the user in
            login_user(new_user)
            
            flash('Account created successfully! Welcome to Innovation Hub.', 'success')
            return redirect(url_for('dashboard.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {str(e)}', 'error')
            return redirect(url_for('auth.signup'))
    
    return render_template('signup.html')

@auth_bp.route('/signin', methods=['GET', 'POST'])
def signin():
    """Student user login page"""
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            remember = True if request.form.get('remember') else False
            
            if not email or not password:
                flash('Email and password are required', 'error')
                return redirect(url_for('auth.signin'))
            
            user = User.query.filter_by(email=email).first()
            
            if not user or not check_password_hash(user.password, password):
                flash('Invalid email or password', 'error')
                return redirect(url_for('auth.signin'))
            
            # Check if user is trying to sign in to wrong portal
            if user.is_supervisor:
                flash('This is a supervisor account. Please use Supervisor Sign In.', 'error')
                return redirect(url_for('supervisor.signin'))
            
            if user.is_admin:
                flash('This is an admin account. Please use Admin Sign In.', 'error')
                return redirect(url_for('admin.signin'))
            
            if user.is_dev:
                flash('This is a developer account. Please use Developer Sign In.', 'error')
                return redirect(url_for('dev.signin'))
            
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash(f'Welcome back, {user.get_full_name() or user.username}!', 'success')
            return redirect(url_for('dashboard.dashboard'))
            
        except Exception as e:
            flash(f'Error signing in: {str(e)}', 'error')
            return redirect(url_for('auth.signin'))
    
    return render_template('signin.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Log out current user"""
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('index'))

@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page - works for both students and supervisors"""
    created_projects = []
    joined_projects = []
    applications = []
    
    if not current_user.is_supervisor:
        # Student view
        created_projects = Project.query.filter_by(student_id=current_user.id).all()
        
        # Get user's applications
        applications = ProjectApplication.query.filter_by(applicant_id=current_user.id).all()
        
        # Get joined projects (approved applications)
        approved_apps = ProjectApplication.query.filter_by(
            applicant_id=current_user.id,
            status='approved'
        ).all()
        joined_projects = [app.project for app in approved_apps if app.project]
    
    # For supervisors, show projects they supervise
    supervised_projects = []
    if current_user.is_supervisor:
        supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()
    
    # Calculate stats
    all_projects = created_projects + joined_projects
    active_count = sum(1 for p in all_projects if p and p.status == 'active')
    completed_count = sum(1 for p in all_projects if p and p.status == 'completed')
    pending_count = sum(1 for a in applications if a and a.status == 'pending')
    
    return render_template(
        'profile.html',
        user=current_user,
        created_projects=created_projects,
        joined_projects=joined_projects,
        supervised_projects=supervised_projects,
        applications=applications,
        active_count=active_count,
        completed_count=completed_count,
        pending_count=pending_count
    )

@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile - supports both students and supervisors"""
    if request.method == 'POST':
        try:
            # Get form data
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            faculty = request.form.get('faculty', '').strip()
            department = request.form.get('department', '').strip()
            specialization = request.form.get('specialization', '').strip()
            phone = request.form.get('phone', '').strip()
            location = request.form.get('location', '').strip()
            bio = request.form.get('bio', '').strip()
            skills = request.form.get('skills', '').strip()
            
            # Update basic user info
            if first_name:
                current_user.first_name = first_name
            if last_name:
                current_user.last_name = last_name
            if first_name and last_name:
                current_user.username = f"{first_name} {last_name}"
            
            # Update faculty/department
            if faculty:
                current_user.faculty = faculty
            if department:
                current_user.department = department
            if specialization and current_user.is_supervisor:
                current_user.specialization = specialization
            if bio:
                current_user.bio = bio
            if phone:
                current_user.phone = phone
            if location:
                current_user.location = location
            
            # Update skills
            if skills is not None:
                if skills.strip():
                    skills_list = [s.strip() for s in skills.split(',') if s.strip()]
                    current_user.set_skills(skills_list)
                else:
                    current_user.set_skills([])
            
            # Password change handling
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if current_password or new_password or confirm_password:
                if not check_password_hash(current_user.password, current_password):
                    flash('Current password is incorrect', 'error')
                    return redirect(url_for('auth.edit_profile'))
                
                if not new_password:
                    flash('New password is required', 'error')
                    return redirect(url_for('auth.edit_profile'))
                
                if len(new_password) < 6:
                    flash('New password must be at least 6 characters', 'error')
                    return redirect(url_for('auth.edit_profile'))
                
                if new_password != confirm_password:
                    flash('New passwords do not match', 'error')
                    return redirect(url_for('auth.edit_profile'))
                
                current_user.password = generate_password_hash(new_password)
                flash('Password changed successfully!', 'success')
            
            db.session.commit()
            
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('auth.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
            return redirect(url_for('auth.edit_profile'))
    
    return render_template('edit_profile.html', user=current_user)

@auth_bp.route('/profile/update-skills', methods=['POST'])
@login_required
def update_skills():
    """API endpoint to update skills"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
            
        data = request.get_json()
        if data is None:
            return jsonify({'success': False, 'error': 'Invalid JSON data'}), 400
            
        skills = data.get('skills', [])
        
        if not isinstance(skills, list):
            return jsonify({'success': False, 'error': 'Skills must be a list'}), 400
        
        current_user.set_skills(skills)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'skills': current_user.get_skills()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== VIEW SUPERVISOR PROFILE ====================

@auth_bp.route('/supervisor/profile/<int:supervisor_id>')
@login_required
def view_supervisor_profile(supervisor_id):
    """Public view of a supervisor's profile for students"""
    supervisor = User.query.get_or_404(supervisor_id)
    
    if not supervisor.is_supervisor:
        flash('User is not a supervisor', 'error')
        return redirect(url_for('projects'))
    
    supervised_projects = Project.query.filter_by(
        supervisor_id=supervisor.id,
        status='active'
    ).all()
    
    completed_projects = Project.query.filter_by(
        supervisor_id=supervisor.id,
        status='completed'
    ).all()
    
    return render_template('view_supervisor_profile.html',
        supervisor=supervisor,
        supervised_projects=supervised_projects,
        completed_projects=completed_projects
    )

# ==================== REQUEST SUPERVISION ====================

@auth_bp.route('/project/<int:project_id>/request-supervisor', methods=['POST'])
@login_required
def request_supervisor(project_id):
    """Request a supervisor for a project"""
    project = Project.query.get_or_404(project_id)
    
    if project.student_id != current_user.id:
        flash('You do not have permission to request supervision for this project', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    if project.supervisor_id:
        flash('This project already has a supervisor', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    supervisor_id = request.form.get('supervisor_id')
    message = request.form.get('message', '')
    
    if not supervisor_id:
        flash('Please select a supervisor', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    supervisor = User.query.get(supervisor_id)
    if not supervisor or not supervisor.is_supervisor:
        flash('Invalid supervisor selected', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    project.supervisor_id = supervisor.id
    project.status = 'pending_supervision'
    project.supervision_requested_at = datetime.utcnow()
    db.session.commit()
    
    flash(f'Supervision request sent to {supervisor.get_full_name()}', 'success')
    return redirect(url_for('project_detail', project_id=project.id))

# ==================== MARK PROJECT COMPLETE/ACTIVE ====================

@auth_bp.route('/project/<int:project_id>/mark-complete', methods=['POST'])
@login_required
def mark_project_complete(project_id):
    """Mark a project as completed (for project owner)"""
    project = Project.query.get_or_404(project_id)
    
    if project.student_id != current_user.id:
        flash('You do not have permission to modify this project', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    if project.status == 'completed':
        flash('Project is already marked as completed', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    project.status = 'completed'
    project.completed_at = datetime.utcnow()
    db.session.commit()
    
    flash('Project marked as completed! It will appear in the portfolio.', 'success')
    return redirect(url_for('project_detail', project_id=project.id))

@auth_bp.route('/project/<int:project_id>/mark-active', methods=['POST'])
@login_required
def mark_project_active(project_id):
    """Mark a completed project as active again"""
    project = Project.query.get_or_404(project_id)
    
    if project.student_id != current_user.id:
        flash('You do not have permission to modify this project', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    if project.status != 'completed':
        flash('Only completed projects can be marked as active', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    
    project.status = 'active'
    project.completed_at = None
    db.session.commit()
    
    flash('Project marked as active again.', 'success')
    return redirect(url_for('project_detail', project_id=project.id))

# ==================== FORGOT PASSWORD ====================

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset - sends email to admin"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('Please enter your email address', 'error')
            return redirect(url_for('auth.forgot_password'))
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Log the request (for admin to see)
            print(f"[PASSWORD RESET REQUEST] User: {user.username} ({user.email}) at {datetime.now()}")
            
            # Store request in database or file for admin review
            # For now, flash message to user
            flash('Your password reset request has been sent to the administrator. You will be contacted shortly.', 'success')
        else:
            # Don't reveal if email exists or not for security
            flash('If an account exists with that email, a reset request has been sent.', 'success')
        
        return redirect(url_for('auth.signin'))
    
    return render_template('forgot_password.html')

# ==================== PASSWORD RESET (Admin only) ====================

@auth_bp.route('/reset-password/<int:user_id>', methods=['GET', 'POST'])
@login_required
def reset_password(user_id):
    """Admin-only password reset page"""
    # Check if current user is admin or developer
    if not current_user.is_admin and not current_user.is_dev:
        flash('Access denied. Only administrators can reset passwords.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password:
            flash('New password is required', 'error')
            return redirect(url_for('auth.reset_password', user_id=user_id))
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect(url_for('auth.reset_password', user_id=user_id))
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('auth.reset_password', user_id=user_id))
        
        user.password = generate_password_hash(new_password)
        db.session.commit()
        
        flash(f'Password reset for {user.email}. New password: {new_password}', 'success')
        
        if current_user.is_admin:
            return redirect(url_for('admin.users'))
        else:
            return redirect(url_for('dev.dashboard'))
    
    return render_template('reset_password.html', user=user)
