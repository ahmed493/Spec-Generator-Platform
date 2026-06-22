"""
SQLAlchemy models for User, Role, Project, and Source
- User: stores SSO subject, email, name, provider
- Role: stores role name
- UserRole: association table for many-to-many
- Project: stores project metadata
- Source: stores data sources connected to projects
"""
from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, Text, JSON
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import json as json_module

Base = declarative_base()

user_role_table = Table(
    'user_role', Base.metadata,
    Column('user_id', Integer, ForeignKey('user.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('role.id'), primary_key=True)
)

class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    sub = Column(String, unique=True, nullable=False)  # SSO subject
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    provider = Column(String)
    roles = relationship('Role', secondary=user_role_table, back_populates='users')

class Role(Base):
    __tablename__ = 'role'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    users = relationship('User', secondary=user_role_table, back_populates='roles')

class Project(Base):
    __tablename__ = 'project'
    id = Column(String, primary_key=True)  # UUID hex
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sources = relationship('Source', back_populates='project', cascade='all, delete-orphan')

class Source(Base):
    __tablename__ = 'source'
    id = Column(String, primary_key=True)  # UUID hex
    project_id = Column(String, ForeignKey('project.id'), nullable=False)
    type = Column(String, nullable=False)  # github, pdf, notion, etc.
    type_name = Column(String)  # Human readable name
    icon = Column(String)  # Icon name
    label = Column(String, nullable=False)  # User-provided label
    config = Column(JSON)  # Config dict (owner, repo, url, etc.)
    status = Column(String, default='connected')  # connected, error, etc.
    added_at = Column(DateTime, default=datetime.utcnow)
    project = relationship('Project', back_populates='sources')
