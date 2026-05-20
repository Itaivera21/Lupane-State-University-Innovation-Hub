from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # FIXED: Changed from String(200) to String(512) to prevent hash truncation
    password = db.Column(db.String(512), nullable=False)
    faculty = db.Column(db.String(100), nullable=True)
    student_id = db.Column(db.String(50), unique=True, nullable=True)
    skills = db.Column(db.Text, default='')
    phone = db.Column(db.String(20), nullable=True)
    location = db.Column(db.String(100), nullable=True)

    # Role flags
    is_admin = db.Column(db.Boolean, default=False)
    is_dev = db.Column(db.Boolean, default=False)
    is_supervisor = db.Column(db.Boolean, default=False)

    # Supervisor specific fields
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    specialization = db.Column(db.String(200), nullable=True)
    bio = db.Column(db.Text, nullable=True)

    # Timestamps
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships - Student projects
    projects_created = db.relationship('Project', foreign_keys='Project.student_id', back_populates='student', lazy=True)

    # Relationships - Supervisor projects
    supervised_projects = db.relationship('Project', foreign_keys='Project.supervisor_id', back_populates='supervisor', lazy=True)

    # Applications
    project_applications = db.relationship('ProjectApplication', foreign_keys='ProjectApplication.applicant_id', back_populates='applicant', lazy=True)

    # Forum
    forum_topics = db.relationship('ForumTopic', back_populates='author', lazy=True)
    forum_posts = db.relationship('ForumPost', back_populates='author', lazy=True)

    # Chat
    chat_messages = db.relationship('ChatMessage', foreign_keys='ChatMessage.sender_id', back_populates='sender', lazy=True)
    chat_resources = db.relationship('ChatResource', back_populates='uploader', lazy=True)

    # Group memberships
    group_memberships = db.relationship('GroupMember', back_populates='user', lazy=True)

    def get_full_name(self):
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        return self.username

    def set_skills(self, skills_list):
        """Store skills as comma-separated string"""
        if skills_list and isinstance(skills_list, list):
            cleaned_skills = [s.strip() for s in skills_list if s and s.strip()]
            self.skills = ','.join(cleaned_skills)
        elif isinstance(skills_list, str):
            cleaned_skills = [s.strip() for s in skills_list.split(',') if s.strip()]
            self.skills = ','.join(cleaned_skills)
        else:
            self.skills = ''

    def get_skills(self):
        """Return skills as list"""
        if self.skills:
            return [s.strip() for s in self.skills.split(',') if s.strip()]
        return []

    def __repr__(self):
        return f'<User {self.email}>'


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.String(50), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    skills_required = db.Column(db.Text, default='')
    team_size = db.Column(db.Integer, default=3)
    duration = db.Column(db.String(50))
    category = db.Column(db.String(100))
    roles = db.Column(db.Text)
    additional_details = db.Column(db.Text)

    # Project status
    status = db.Column(db.String(50), default='active')  # active, completed, pending_supervision

    # Supervision fields
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    supervision_requested_at = db.Column(db.DateTime, nullable=True)
    supervision_approved_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship('User', foreign_keys=[student_id], back_populates='projects_created')
    supervisor = db.relationship('User', foreign_keys=[supervisor_id], back_populates='supervised_projects')
    applications = db.relationship('ProjectApplication', back_populates='project', cascade='all, delete-orphan', lazy=True)
    forum_topics = db.relationship('ForumTopic', back_populates='project', lazy=True)
    chat_messages = db.relationship('ChatMessage', back_populates='project', lazy=True)
    chat_resources = db.relationship('ChatResource', back_populates='project', lazy=True)
    group = db.relationship('Group', back_populates='project', uselist=False, lazy=True)

    def set_skills(self, skills_list):
        """Store skills as comma-separated string"""
        if skills_list and isinstance(skills_list, list):
            cleaned_skills = [s.strip() for s in skills_list if s and s.strip()]
            self.skills_required = ','.join(cleaned_skills)
        elif isinstance(skills_list, str):
            cleaned_skills = [s.strip() for s in skills_list.split(',') if s.strip()]
            self.skills_required = ','.join(cleaned_skills)
        else:
            self.skills_required = ''

    def get_skills(self):
        """Return skills as list"""
        if self.skills_required:
            return [s.strip() for s in self.skills_required.split(',') if s.strip()]
        return []

    def get_team_members(self):
        """Get all team members including student and approved applicants"""
        members = []
        if self.student:
            members.append(self.student)

        approved_apps = ProjectApplication.query.filter_by(
            project_id=self.id,
            status='approved'
        ).all()

        for app in approved_apps:
            if app.applicant and app.applicant not in members:
                members.append(app.applicant)

        if self.supervisor and self.supervisor not in members:
            members.append(self.supervisor)

        return members

    def __repr__(self):
        return f'<Project {self.title}>'


class ProjectApplication(db.Model):
    __tablename__ = 'project_applications'

    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    message = db.Column(db.Text)
    status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    applicant = db.relationship('User', foreign_keys=[applicant_id], back_populates='project_applications')
    project = db.relationship('Project', back_populates='applications')

    def __repr__(self):
        return f'<ProjectApplication {self.applicant_id} -> {self.project_id}>'


class ForumTopic(db.Model):
    __tablename__ = 'forum_topics'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False)
    pinned_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Foreign Keys
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)

    # Relationships
    author = db.relationship('User', back_populates='forum_topics')
    project = db.relationship('Project', back_populates='forum_topics')
    posts = db.relationship('ForumPost', back_populates='topic', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return f'<ForumTopic {self.title}>'


class ForumPost(db.Model):
    __tablename__ = 'forum_posts'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Foreign Keys
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('forum_topics.id'), nullable=False)

    # Relationships
    author = db.relationship('User', back_populates='forum_posts')
    topic = db.relationship('ForumTopic', back_populates='posts')

    def __repr__(self):
        return f'<ForumPost {self.id}>'


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Allow NULL for system messages
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('chat_resources.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    is_system = db.Column(db.Boolean, default=False)  # For system messages
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id], back_populates='chat_messages')
    project = db.relationship('Project', back_populates='chat_messages')
    resource = db.relationship('ChatResource', back_populates='chat_message', foreign_keys=[resource_id])

    def __repr__(self):
        return f'<ChatMessage {self.id}>'


class ChatResource(db.Model):
    __tablename__ = 'chat_resources'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.String(50))
    file_type = db.Column(db.String(50))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    uploader = db.relationship('User', back_populates='chat_resources')
    project = db.relationship('Project', back_populates='chat_resources')
    chat_message = db.relationship('ChatMessage', back_populates='resource', uselist=False, foreign_keys=[ChatMessage.resource_id])

    def __repr__(self):
        return f'<ChatResource {self.name}>'


class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    project = db.relationship('Project', back_populates='group')
    members = db.relationship('GroupMember', back_populates='group', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return f'<Group {self.name}>'


class GroupMember(db.Model):
    __tablename__ = 'group_members'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_muted = db.Column(db.Boolean, default=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    group = db.relationship('Group', back_populates='members')
    user = db.relationship('User', back_populates='group_memberships')

    def __repr__(self):
        return f'<GroupMember user={self.user_id} group={self.group_id}>'


class SystemVariable(db.Model):
    __tablename__ = 'system_variables'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SystemVariable {self.key}={self.value}>'


# ==================== ANNOUNCEMENTS MODEL ====================

class Announcement(db.Model):
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False)
    attachment_filename = db.Column(db.String(200), nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)
    attachment_size = db.Column(db.String(50), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<Announcement {self.title}>'
