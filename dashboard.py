# dashboard.py
# This file handles all dashboard-related routes for the Innovation Hub
# It works alongside your main app.py but keeps dashboard logic separate

from flask import Blueprint, render_template, jsonify, session, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, User, Project, ProjectApplication, ForumTopic, ForumPost
from datetime import datetime, timedelta
from sqlalchemy import desc, and_

# Create a Blueprint for dashboard routes
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Main dashboard view - renders the dashboard HTML page
    Supports both students and supervisors with different views
    """
    try:
        # Check if user is supervisor
        if current_user.is_supervisor:
            return render_supervisor_dashboard()
        else:
            return render_student_dashboard()
        
    except Exception as e:
        print(f"Error loading dashboard: {str(e)}")
        return render_template('dashboard.html', 
                             error="Unable to load some data. Please refresh.")

def render_student_dashboard():
    """Render dashboard for regular students"""
    # Get user's active projects (status = 'active')
    active_projects_list = Project.query.filter(
        Project.student_id == current_user.id,
        Project.status == 'active'
    ).all()
    
    # Get projects they applied to and were approved (active ones only)
    approved_applications = ProjectApplication.query.filter_by(
        applicant_id=current_user.id,
        status='approved'
    ).all()
    joined_active_projects = [app.project for app in approved_applications if app.project and app.project.status == 'active']
    
    # Combine active projects (remove duplicates)
    all_active_projects = list(set(active_projects_list + joined_active_projects))
    
    # Get user's completed projects
    completed_projects_list = Project.query.filter(
        Project.student_id == current_user.id,
        Project.status == 'completed'
    ).all()
    
    # Get joined completed projects
    joined_completed_projects = [app.project for app in approved_applications if app.project and app.project.status == 'completed']
    
    # Combine completed projects (remove duplicates)
    all_completed_projects = list(set(completed_projects_list + joined_completed_projects))
    
    # Get pending applications count
    pending_applications_count = ProjectApplication.query.filter_by(
        applicant_id=current_user.id,
        status='pending'
    ).count()
    
    # Get actual pending applications with project details
    pending_apps = ProjectApplication.query.filter_by(
        applicant_id=current_user.id,
        status='pending'
    ).order_by(desc(ProjectApplication.applied_at)).all()
    
    # Get project recommendations based on user's skills
    user_skills = current_user.get_skills()
    recommended_projects = []
    
    if user_skills:
        all_projects_for_recommendation = Project.query.filter(
            and_(
                Project.status == 'active',
                Project.student_id != current_user.id
            )
        ).all()
        
        for project in all_projects_for_recommendation:
            project_skills = project.get_skills()
            if project_skills:
                matching_skills = set(user_skills) & set(project_skills)
                match_percentage = int((len(matching_skills) / len(project_skills)) * 100)
                
                if match_percentage > 50:
                    recommended_projects.append({
                        'project': project,
                        'match': match_percentage,
                        'matching_skills': list(matching_skills)
                    })
        
        recommended_projects.sort(key=lambda x: x['match'], reverse=True)
        recommended_projects = recommended_projects[:3]
    
    # Get recent forum activity
    recent_forum_posts = ForumTopic.query.order_by(
        desc(ForumTopic.created_at)
    ).limit(5).all()
    
    return render_template('dashboard.html',
        user=current_user,
        active_projects=all_active_projects[:3],
        active_projects_count=len(all_active_projects),
        completed_projects=all_completed_projects[:3],
        completed_projects_count=len(all_completed_projects),
        pending_applications_count=pending_applications_count,
        pending_applications=pending_apps,
        recommended_projects=recommended_projects,
        forum_posts=recent_forum_posts,
        is_supervisor=False
    )

def render_supervisor_dashboard():
    """Render dashboard for supervisors"""
    # Get projects supervised by this supervisor - separate by status
    supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()
    
    # Separate by status
    active_supervised = [p for p in supervised_projects if p.status == 'active']
    completed_supervised_list = [p for p in supervised_projects if p.status == 'completed']
    pending_supervision_requests = [p for p in supervised_projects if p.status == 'pending_supervision']
    
    # Count stats
    supervised_projects_count = len(supervised_projects)
    pending_requests_count = len(pending_supervision_requests)
    completed_supervised_count = len(completed_supervised_list)
    
    # Get recent forum activity (same for all users)
    recent_forum_posts = ForumTopic.query.order_by(
        desc(ForumTopic.created_at)
    ).limit(5).all()
    
    # Get recent activity on supervised projects (new applications, messages)
    recent_activity = []
    
    # Get recent applications to supervised projects
    for project in supervised_projects[:5]:
        recent_apps = ProjectApplication.query.filter_by(
            project_id=project.id,
            status='pending'
        ).order_by(desc(ProjectApplication.applied_at)).limit(3).all()
        
        for app in recent_apps:
            recent_activity.append({
                'type': 'application',
                'message': f'New application from {app.applicant.get_full_name()} for {project.title}',
                'time': app.applied_at,
                'project_id': project.id
            })
    
    # Sort recent activity by time (newest first)
    recent_activity.sort(key=lambda x: x['time'], reverse=True)
    recent_activity = recent_activity[:10]
    
    return render_template('dashboard.html',
        user=current_user,
        supervised_projects_list=active_supervised[:5],
        supervised_projects_count=supervised_projects_count,
        pending_supervision_requests=pending_requests_count,
        pending_supervision_requests_list=pending_supervision_requests,
        completed_supervised=completed_supervised_count,
        forum_posts=recent_forum_posts,
        recent_activity=recent_activity,
        is_supervisor=True
    )

# ==================== API ENDPOINTS ====================

@dashboard_bp.route('/api/dashboard/stats')
@login_required
def get_dashboard_stats():
    """
    API endpoint to get dashboard statistics as JSON
    Useful for updating dashboard without page refresh
    """
    try:
        if current_user.is_supervisor:
            # Supervisor stats
            supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()
            pending_requests = [p for p in supervised_projects if p.status == 'pending_supervision']
            completed_projects = [p for p in supervised_projects if p.status == 'completed']
            
            return jsonify({
                'success': True,
                'is_supervisor': True,
                'stats': {
                    'supervised_projects': len(supervised_projects),
                    'pending_requests': len(pending_requests),
                    'completed_projects': len(completed_projects),
                    'username': current_user.get_full_name() or current_user.username
                }
            })
        else:
            # Student stats
            active_projects = Project.query.filter(
                and_(
                    Project.student_id == current_user.id,
                    Project.status == 'active'
                )
            ).count()
            
            completed_projects = Project.query.filter(
                and_(
                    Project.student_id == current_user.id,
                    Project.status == 'completed'
                )
            ).count()
            
            pending_apps = ProjectApplication.query.filter_by(
                applicant_id=current_user.id,
                status='pending'
            ).count()
            
            return jsonify({
                'success': True,
                'is_supervisor': False,
                'stats': {
                    'active_projects': active_projects,
                    'completed_projects': completed_projects,
                    'pending_applications': pending_apps,
                    'username': current_user.get_full_name() or current_user.username
                }
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@dashboard_bp.route('/api/supervisor/pending-requests')
@login_required
def get_pending_supervision_requests():
    """API endpoint for supervisors to get pending requests"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Access denied'}), 403
    
    pending = Project.query.filter_by(
        supervisor_id=current_user.id,
        status='pending_supervision'
    ).all()
    
    return jsonify({
        'success': True,
        'requests': [{
            'id': p.id,
            'title': p.title,
            'student_name': p.student.get_full_name() if p.student else 'Unknown',
            'requested_at': p.supervision_requested_at.isoformat() if p.supervision_requested_at else None,
            'description': p.description[:100]
        } for p in pending]
    })

@dashboard_bp.route('/dashboard/refresh-projects')
@login_required
def refresh_projects():
    """
    API endpoint to refresh just the projects section
    Useful for when user completes a task
    """
    if current_user.is_supervisor:
        supervised_projects = Project.query.filter_by(supervisor_id=current_user.id).all()
        active_supervised = [p for p in supervised_projects if p.status == 'active']
        return render_template('partials/supervisor_projects.html', 
                             projects=active_supervised[:3])
    else:
        active_projects_list = Project.query.filter(
            Project.student_id == current_user.id,
            Project.status == 'active'
        ).all()
        
        approved_apps = ProjectApplication.query.filter_by(
            applicant_id=current_user.id,
            status='approved'
        ).all()
        
        joined_active = [app.project for app in approved_apps if app.project and app.project.status == 'active']
        all_active = list(set(active_projects_list + joined_active))
        
        return render_template('partials/project_cards.html', 
                             projects=all_active[:3])

# ==================== SUPERVISOR SPECIFIC ROUTES ====================

@dashboard_bp.route('/supervisor/approve-request/<int:project_id>', methods=['POST'])
@login_required
def approve_supervision_request(project_id):
    """Approve a pending supervision request"""
    if not current_user.is_supervisor:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    project = Project.query.get_or_404(project_id)
    
    if project.supervisor_id != current_user.id:
        flash('You are not authorized to approve this request', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    if project.status != 'pending_supervision':
        flash('This request is no longer pending', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    project.status = 'active'
    project.supervision_approved_at = datetime.utcnow()
    db.session.commit()
    
    flash(f'Supervision approved for project: {project.title}', 'success')
    return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/supervisor/reject-request/<int:project_id>', methods=['POST'])
@login_required
def reject_supervision_request(project_id):
    """Reject a pending supervision request"""
    if not current_user.is_supervisor:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    project = Project.query.get_or_404(project_id)
    
    if project.supervisor_id != current_user.id:
        flash('You are not authorized to reject this request', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    if project.status != 'pending_supervision':
        flash('This request is no longer pending', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    # Remove supervisor assignment
    project.supervisor_id = None
    project.status = 'active'
    project.supervision_requested_at = None
    db.session.commit()
    
    flash(f'Supervision request rejected for project: {project.title}', 'warning')
    return redirect(url_for('dashboard.dashboard'))

# ==================== HELPER FUNCTIONS ====================

def get_time_based_greeting():
    """Returns appropriate greeting based on time of day"""
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 18:
        return "Good afternoon"
    else:
        return "Good evening"
