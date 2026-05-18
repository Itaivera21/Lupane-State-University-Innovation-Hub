from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app, session
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, Project, ChatMessage, Group, GroupMember, ChatResource, ProjectApplication
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename

# ==================== BLUEPRINT DEFINITION ====================
chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'py', 'js', 'html', 'css', 'zip', 'json'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_team_members(project):
    """Get all team members for a project"""
    members = [project.student] if project.student else []
    # Add approved members from applications
    approved_apps = ProjectApplication.query.filter_by(
        project_id=project.id,
        status='approved'
    ).all()
    for app in approved_apps:
        if app.applicant not in members:
            members.append(app.applicant)
    return members

def get_system_user():
    """Get or create system user for system messages"""
    # First try to get existing system user
    system_user = User.query.filter_by(username='system').first()
    if system_user:
        return system_user

    # If no system user, use the first admin user
    admin_user = User.query.filter_by(is_admin=True).first()
    if admin_user:
        return admin_user

    # If no admin, use the first user
    first_user = User.query.first()
    if first_user:
        return first_user

    # Last resort - create a system user without password
    system_user = User(
        username='system',
        email='system@innovationhub.com',
        is_admin=False,
        is_supervisor=False
    )
    # Try to set password using different possible methods
    try:
        # Try set_password method
        system_user.set_password('system_pass_123')
    except AttributeError:
        try:
            # Try hash_password method
            system_user.hash_password('system_pass_123')
        except AttributeError:
            try:
                # Try setting password_hash directly (Werkzeug)
                from werkzeug.security import generate_password_hash
                system_user.password_hash = generate_password_hash('system_pass_123')
            except AttributeError:
                try:
                    # Try just setting password attribute
                    system_user.password = 'system_pass_123'
                except AttributeError:
                    # No password method available, continue without password
                    pass

    db.session.add(system_user)
    db.session.commit()
    return system_user

def send_system_message(project_id, content):
    """Send a system message to the chat"""
    system_user = get_system_user()
    system_message = ChatMessage(
        content=content,
        sender_id=system_user.id,
        project_id=project_id,
        is_read=False,
        is_system=True
    )
    db.session.add(system_message)
    db.session.commit()

# ==================== PAGE ROUTES ====================

@chat_bp.route('/chats')
@login_required
def chats():
    """Main chat page - shows all user's project chats"""
    user_projects = []

    # Projects user created
    owned_projects = Project.query.filter_by(student_id=current_user.id).all()
    for p in owned_projects:
        p.unread_count = ChatMessage.query.filter_by(
            project_id=p.id,
            is_read=False
        ).filter(ChatMessage.sender_id != current_user.id).count()
        user_projects.append(p)

    # Projects user applied to and was approved
    approved_apps = ProjectApplication.query.filter_by(
        applicant_id=current_user.id,
        status='approved'
    ).all()
    for app in approved_apps:
        if app.project not in user_projects:
            app.project.unread_count = ChatMessage.query.filter_by(
                project_id=app.project.id,
                is_read=False
            ).filter(ChatMessage.sender_id != current_user.id).count()
            user_projects.append(app.project)

    # If supervisor, add supervised projects
    if current_user.is_supervisor:
        supervised = Project.query.filter_by(supervisor_id=current_user.id).all()
        for p in supervised:
            if p not in user_projects:
                p.unread_count = ChatMessage.query.filter_by(
                    project_id=p.id,
                    is_read=False
                ).filter(ChatMessage.sender_id != current_user.id).count()
                user_projects.append(p)

    return render_template('chats.html', user_projects=user_projects, current_project=None)

@chat_bp.route('/project/<int:project_id>')
@login_required
def project_chat(project_id):
    """View chat for a specific project"""
    project = Project.query.get_or_404(project_id)

    # Check if user has access to this chat
    has_access = False

    if project.student_id == current_user.id:
        has_access = True

    approved_app = ProjectApplication.query.filter_by(
        project_id=project_id,
        applicant_id=current_user.id,
        status='approved'
    ).first()
    if approved_app:
        has_access = True

    if project.supervisor_id == current_user.id:
        has_access = True

    if current_user.is_admin:
        has_access = True

    if not has_access:
        flash('You do not have access to this chat', 'error')
        return redirect(url_for('chat.chats'))

    # Get all messages for this project
    messages = ChatMessage.query.filter_by(project_id=project_id).order_by(ChatMessage.created_at).all()

    # Mark messages as read
    unread_messages = ChatMessage.query.filter_by(
        project_id=project_id,
        is_read=False
    ).filter(ChatMessage.sender_id != current_user.id).all()

    for msg in unread_messages:
        msg.is_read = True
    db.session.commit()

    # Get team members
    team_members = get_team_members(project)
    if project.supervisor and project.supervisor not in team_members:
        team_members.append(project.supervisor)

    # Get all user's projects for sidebar
    user_projects = []
    owned = Project.query.filter_by(student_id=current_user.id).all()
    for p in owned:
        p.unread_count = ChatMessage.query.filter_by(
            project_id=p.id,
            is_read=False
        ).filter(ChatMessage.sender_id != current_user.id).count()
        user_projects.append(p)

    approved_apps_list = ProjectApplication.query.filter_by(
        applicant_id=current_user.id,
        status='approved'
    ).all()
    for app in approved_apps_list:
        if app.project not in user_projects:
            app.project.unread_count = ChatMessage.query.filter_by(
                project_id=app.project.id,
                is_read=False
            ).filter(ChatMessage.sender_id != current_user.id).count()
            user_projects.append(app.project)

    if current_user.is_supervisor:
        supervised = Project.query.filter_by(supervisor_id=current_user.id).all()
        for p in supervised:
            if p not in user_projects:
                p.unread_count = ChatMessage.query.filter_by(
                    project_id=p.id,
                    is_read=False
                ).filter(ChatMessage.sender_id != current_user.id).count()
                user_projects.append(p)

    return render_template('chats.html',
        user_projects=user_projects,
        current_project=project,
        messages=messages,
        team_members=team_members,
        current_user=current_user
    )


# ==================== GROUP INFO & TEAM MEMBERS PAGES ====================

@chat_bp.route('/group-info/<int:project_id>')
@login_required
def group_info(project_id):
    """View group information page"""
    project = Project.query.get_or_404(project_id)

    # Check access
    has_access = (project.student_id == current_user.id or
                  project.supervisor_id == current_user.id or
                  current_user.is_admin)

    if not has_access:
        approved_app = ProjectApplication.query.filter_by(
            project_id=project_id,
            applicant_id=current_user.id,
            status='approved'
        ).first()
        if not approved_app:
            flash('You do not have access to this group', 'error')
            return redirect(url_for('chat.chats'))

    return render_template('group_info.html', project_id=project_id, current_user=current_user)

@chat_bp.route('/team-members/<int:project_id>')
@login_required
def team_members(project_id):
    """View team members management page"""
    project = Project.query.get_or_404(project_id)

    # Check access
    has_access = (project.student_id == current_user.id or
                  project.supervisor_id == current_user.id or
                  current_user.is_admin)

    if not has_access:
        approved_app = ProjectApplication.query.filter_by(
            project_id=project_id,
            applicant_id=current_user.id,
            status='approved'
        ).first()
        if not approved_app:
            flash('You do not have access to this group', 'error')
            return redirect(url_for('chat.chats'))

    return render_template('team_members.html', project_id=project_id, current_user=current_user)


# ==================== API ROUTES ====================

@chat_bp.route('/api/send-message/<int:project_id>', methods=['POST'])
@login_required
def send_message(project_id):
    """Send a message via AJAX"""
    try:
        project = Project.query.get_or_404(project_id)

        has_access = (project.student_id == current_user.id or
                      project.supervisor_id == current_user.id or
                      current_user.is_admin)

        if not has_access:
            return jsonify({'error': 'Access denied'}), 403

        # CHECK IF USER IS MUTED
        group = Group.query.filter_by(project_id=project_id).first()
        if group:
            group_member = GroupMember.query.filter_by(
                group_id=group.id,
                user_id=current_user.id
            ).first()
            if group_member and group_member.is_muted:
                return jsonify({'error': 'You are muted in this chat. You cannot send messages.'}), 403

        content = request.form.get('message', '').strip()
        if not content:
            return jsonify({'error': 'Message cannot be empty'}), 400

        message = ChatMessage(
            content=content,
            sender_id=current_user.id,
            project_id=project_id,
            is_read=False
        )
        db.session.add(message)
        db.session.commit()

        # FIXED: Return proper JSON with lowercase booleans
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'sender_name': current_user.get_full_name() or current_user.username,
                'time': message.created_at.strftime('%I:%M %p'),
                'is_own': True
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error sending message: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@chat_bp.route('/api/messages/<int:project_id>')
@login_required
def get_messages(project_id):
    """Get messages for a project via AJAX"""
    try:
        project = Project.query.get_or_404(project_id)

        has_access = (project.student_id == current_user.id or
                      project.supervisor_id == current_user.id or
                      current_user.is_admin)

        if not has_access:
            return jsonify({'error': 'Access denied'}), 403

        messages = ChatMessage.query.filter_by(project_id=project_id).order_by(ChatMessage.created_at).all()

        messages_data = []
        for m in messages:
            message_data = {
                'id': m.id,
                'content': m.content,
                'sender_name': m.sender.get_full_name() or m.sender.username if m.sender else 'System',
                'time': m.created_at.strftime('%I:%M %p, %d %b'),
                'is_own': m.sender_id == current_user.id if m.sender_id else False
            }

            if m.resource_id:
                resource = ChatResource.query.get(m.resource_id)
                if resource:
                    message_data['resource'] = {
                        'id': resource.id,
                        'name': resource.original_filename,
                        'size': resource.file_size,
                        'type': resource.file_type
                    }

            messages_data.append(message_data)

        return jsonify({'messages': messages_data})
        
    except Exception as e:
        print(f"Error getting messages: {str(e)}")
        return jsonify({'messages': [], 'error': str(e)}), 500

@chat_bp.route('/api/mark-project-read/<int:project_id>', methods=['POST'])
@login_required
def mark_project_read(project_id):
    """Mark all messages in a project as read"""
    try:
        ChatMessage.query.filter_by(
            project_id=project_id,
            is_read=False
        ).filter(ChatMessage.sender_id != current_user.id).update({'is_read': True})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error marking messages as read: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/download-resource/<int:resource_id>')
@login_required
def download_resource(resource_id):
    """Download a shared resource"""
    try:
        resource = ChatResource.query.get_or_404(resource_id)

        project = Project.query.get(resource.project_id)
        if project:
            has_access = (project.student_id == current_user.id or
                          project.supervisor_id == current_user.id or
                          current_user.is_admin)

            if not has_access:
                return jsonify({'error': 'Access denied'}), 403

        file_path = resource.file_path
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404

        return send_file(file_path, as_attachment=True, download_name=resource.original_filename)
        
    except Exception as e:
        print(f"Error downloading resource: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/share-resource/<int:project_id>', methods=['POST'])
@login_required
def share_resource(project_id):
    """Share a file resource in chat"""
    try:
        project = Project.query.get_or_404(project_id)

        has_access = (project.student_id == current_user.id or
                      project.supervisor_id == current_user.id or
                      current_user.is_admin)

        if not has_access:
            return jsonify({'error': 'Access denied'}), 403

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed'}), 400

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"

        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'chat')
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)

        file_size = os.path.getsize(file_path)
        size_kb = round(file_size / 1024, 1)
        size_str = f"{size_kb} KB" if size_kb < 1024 else f"{round(size_kb / 1024, 1)} MB"

        resource = ChatResource(
            name=request.form.get('resource_name', filename),
            original_filename=filename,
            file_path=file_path,
            file_size=size_str,
            file_type=filename.rsplit('.', 1)[1].lower(),
            project_id=project_id,
            uploaded_by=current_user.id
        )
        db.session.add(resource)
        db.session.flush()

        description = request.form.get('description', '')
        content = f"Shared file: {filename}"
        if description:
            content += f"\n\n{description}"

        message = ChatMessage(
            content=content,
            sender_id=current_user.id,
            project_id=project_id,
            resource_id=resource.id,
            is_read=False
        )
        db.session.add(message)
        db.session.commit()

        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error sharing resource: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/share-link/<int:project_id>', methods=['POST'])
@login_required
def share_link(project_id):
    """Share a link in chat"""
    try:
        project = Project.query.get_or_404(project_id)

        has_access = (project.student_id == current_user.id or
                      project.supervisor_id == current_user.id or
                      current_user.is_admin)

        if not has_access:
            return jsonify({'error': 'Access denied'}), 403

        data = request.get_json()
        link = data.get('link', '').strip()
        description = data.get('description', '').strip()

        if not link:
            return jsonify({'error': 'Link is required'}), 400

        content = f"Shared link: {link}"
        if description:
            content += f"\n\n{description}"

        message = ChatMessage(
            content=content,
            sender_id=current_user.id,
            project_id=project_id,
            is_read=False
        )
        db.session.add(message)
        db.session.commit()

        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error sharing link: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/share-code/<int:project_id>', methods=['POST'])
@login_required
def share_code(project_id):
    """Share a code snippet in chat"""
    try:
        project = Project.query.get_or_404(project_id)

        has_access = (project.student_id == current_user.id or
                      project.supervisor_id == current_user.id or
                      current_user.is_admin)

        if not has_access:
            return jsonify({'error': 'Access denied'}), 403

        data = request.get_json()
        language = data.get('language', 'text')
        code = data.get('code', '').strip()

        if not code:
            return jsonify({'error': 'Code is required'}), 400

        content = f"Shared {language} code:\n```{language}\n{code}\n```"

        message = ChatMessage(
            content=content,
            sender_id=current_user.id,
            project_id=project_id,
            is_read=False
        )
        db.session.add(message)
        db.session.commit()

        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error sharing code: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==================== GROUP MANAGEMENT API ====================

@chat_bp.route('/api/project-info/<int:project_id>')
@login_required
def get_project_info(project_id):
    """Get project information for group info page"""
    try:
        project = Project.query.get_or_404(project_id)

        has_access = (project.student_id == current_user.id or
                      project.supervisor_id == current_user.id or
                      current_user.is_admin)

        if not has_access:
            approved_app = ProjectApplication.query.filter_by(
                project_id=project_id,
                applicant_id=current_user.id,
                status='approved'
            ).first()
            if not approved_app:
                return jsonify({'error': 'Access denied'}), 403

        member_count = 1
        if project.supervisor:
            member_count += 1

        approved_apps = ProjectApplication.query.filter_by(
            project_id=project_id,
            status='approved'
        ).all()
        member_count += len(approved_apps)

        return jsonify({
            'id': project.id,
            'title': project.title,
            'description': project.description or 'No description provided',
            'owner_id': project.student_id,
            'supervisor_id': project.supervisor_id,
            'member_count': member_count,
            'created_date': project.created_at.strftime('%b %Y') if project.created_at else 'Unknown'
        })
        
    except Exception as e:
        print(f"Error getting project info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/mute-status/<int:project_id>')
@login_required
def get_mute_status(project_id):
    """Get current user's mute status for a project"""
    try:
        project = Project.query.get_or_404(project_id)

        group = Group.query.filter_by(project_id=project_id).first()
        is_muted = False

        if group:
            group_member = GroupMember.query.filter_by(
                group_id=group.id,
                user_id=current_user.id
            ).first()
            if group_member and group_member.is_muted:
                is_muted = True

        return jsonify({'is_muted': is_muted})
        
    except Exception as e:
        print(f"Error getting mute status: {str(e)}")
        return jsonify({'is_muted': False}), 200

@chat_bp.route('/api/toggle-mute/<int:project_id>', methods=['POST'])
@login_required
def toggle_mute(project_id):
    """Toggle mute status for current user on a project"""
    try:
        project = Project.query.get_or_404(project_id)

        data = request.get_json()
        muted = data.get('muted', False)

        group = Group.query.filter_by(project_id=project_id).first()
        if not group:
            group = Group(
                name=f"{project.title} Chat",
                project_id=project_id
            )
            db.session.add(group)
            db.session.flush()

        group_member = GroupMember.query.filter_by(
            group_id=group.id,
            user_id=current_user.id
        ).first()

        if group_member:
            group_member.is_muted = muted
        else:
            group_member = GroupMember(group_id=group.id, user_id=current_user.id, is_muted=muted)
            db.session.add(group_member)

        db.session.commit()

        return jsonify({'success': True, 'is_muted': muted})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error toggling mute: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/members/<int:project_id>')
@login_required
def get_members(project_id):
    """Get all members of a project chat group"""
    try:
        project = Project.query.get_or_404(project_id)

        members = get_team_members(project)
        if project.supervisor and project.supervisor not in members:
            members.append(project.supervisor)

        members_data = []
        for member in members:
            group = Group.query.filter_by(project_id=project_id).first()
            group_member = None
            if group:
                group_member = GroupMember.query.filter_by(
                    group_id=group.id,
                    user_id=member.id
                ).first()

            members_data.append({
                'user_id': member.id,
                'username': member.username,
                'name': member.get_full_name() if hasattr(member, 'get_full_name') else member.username,
                'email': member.email,
                'is_muted': group_member.is_muted if group_member else False,
                'is_supervisor': member.id == project.supervisor_id,
                'can_remove': member.id != project.student_id
            })

        return jsonify(members_data)
        
    except Exception as e:
        print(f"Error getting members: {str(e)}")
        return jsonify([]), 200

@chat_bp.route('/api/mute-member/<int:project_id>', methods=['POST'])
@login_required
def mute_member(project_id):
    """Mute or unmute a member in chat"""
    try:
        project = Project.query.get_or_404(project_id)

        if project.student_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403

        data = request.get_json()
        user_id = data.get('user_id')
        mute = data.get('mute', True)

        group = Group.query.filter_by(project_id=project_id).first()
        if not group:
            group = Group(name=f"{project.title} Chat", project_id=project_id)
            db.session.add(group)
            db.session.flush()

        group_member = GroupMember.query.filter_by(group_id=group.id, user_id=user_id).first()
        if group_member:
            group_member.is_muted = mute
        else:
            group_member = GroupMember(group_id=group.id, user_id=user_id, is_muted=mute)
            db.session.add(group_member)

        db.session.commit()

        if mute:
            user = User.query.get(user_id)
            send_system_message(project_id, f"{user.get_full_name() or user.username} has been muted by the project owner.")

        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error muting member: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/remove-member/<int:project_id>', methods=['POST'])
@login_required
def remove_member(project_id):
    """Remove a member from chat group and project"""
    try:
        project = Project.query.get_or_404(project_id)

        if project.student_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403

        data = request.get_json()
        user_id = data.get('user_id')

        if user_id == project.student_id:
            return jsonify({'error': 'Cannot remove project owner'}), 400

        user = User.query.get(user_id)

        group = Group.query.filter_by(project_id=project_id).first()
        if group:
            GroupMember.query.filter_by(group_id=group.id, user_id=user_id).delete()

        app = ProjectApplication.query.filter_by(
            project_id=project_id,
            applicant_id=user_id,
            status='approved'
        ).first()
        if app:
            db.session.delete(app)

        if user and user.is_supervisor and project.supervisor_id == user_id:
            project.supervisor_id = None

        db.session.commit()

        if user:
            send_system_message(project_id, f"{user.get_full_name() or user.username} has been removed from the project by the project owner.")

        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error removing member: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/add-member/<int:project_id>', methods=['POST'])
@login_required
def add_member(project_id):
    """Add a new member to the project chat group"""
    try:
        project = Project.query.get_or_404(project_id)

        if project.student_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Only project owner can add members'}), 403

        data = request.get_json()
        email = data.get('email', '').strip()

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': f'No user found with email: {email}'}), 404

        if user.id == project.student_id:
            return jsonify({'error': 'This is the project owner'}), 400

        existing_app = ProjectApplication.query.filter_by(
            project_id=project_id,
            applicant_id=user.id,
            status='approved'
        ).first()
        if existing_app:
            return jsonify({'error': 'User is already a team member'}), 400

        if project.supervisor_id == user.id:
            return jsonify({'error': 'User is already the supervisor'}), 400

        new_app = ProjectApplication(
            project_id=project_id,
            applicant_id=user.id,
            message=f"Added by project owner {current_user.get_full_name() or current_user.username}",
            status='approved',
            reviewed_by=current_user.id,
            reviewed_at=datetime.utcnow()
        )
        db.session.add(new_app)

        group = Group.query.filter_by(project_id=project_id).first()
        if group:
            group_member = GroupMember.query.filter_by(
                group_id=group.id,
                user_id=user.id
            ).first()
            if not group_member:
                new_member = GroupMember(group_id=group.id, user_id=user.id, is_muted=False)
                db.session.add(new_member)

        db.session.commit()

        send_system_message(project_id, f"{user.get_full_name() or user.username} has been added to the project by {current_user.get_full_name() or current_user.username}.")

        return jsonify({'success': True, 'message': f'{user.get_full_name() or user.username} added to project'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding member: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/update-role/<int:project_id>', methods=['POST'])
@login_required
def update_member_role(project_id):
    """Update a member's role (promote to supervisor or demote to member)"""
    try:
        project = Project.query.get_or_404(project_id)

        if project.student_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': 'Only project owner can update roles'}), 403

        data = request.get_json()
        user_id = data.get('user_id')
        is_supervisor = data.get('is_supervisor', False)

        user = User.query.get_or_404(user_id)

        if user_id == project.student_id:
            return jsonify({'error': 'Cannot change project owner\'s role'}), 400

        if is_supervisor:
            project.supervisor_id = user_id
            send_system_message(project_id, f"{user.get_full_name() or user.username} has been promoted to Supervisor.")
        else:
            if project.supervisor_id == user_id:
                project.supervisor_id = None
                send_system_message(project_id, f"{user.get_full_name() or user.username} is no longer a Supervisor.")

        db.session.commit()

        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating role: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/api/leave-group/<int:project_id>', methods=['POST'])
@login_required
def leave_group(project_id):
    """Allow a user to leave a project group"""
    try:
        project = Project.query.get_or_404(project_id)

        if project.student_id == current_user.id:
            return jsonify({'error': 'Project owner cannot leave the project. You must delete the project or transfer ownership.'}), 403

        user = current_user

        group = Group.query.filter_by(project_id=project_id).first()
        if group:
            GroupMember.query.filter_by(group_id=group.id, user_id=user.id).delete()

        app = ProjectApplication.query.filter_by(
            project_id=project_id,
            applicant_id=user.id,
            status='approved'
        ).first()
        if app:
            db.session.delete(app)

        if user.is_supervisor and project.supervisor_id == user.id:
            project.supervisor_id = None

        db.session.commit()

        send_system_message(project_id, f"{user.get_full_name() or user.username} has left the group.")

        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error leaving group: {str(e)}")
        return jsonify({'error': str(e)}), 500
