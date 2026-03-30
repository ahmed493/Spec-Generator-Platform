"""
SQLAlchemy models for User and Role
- User: stores SSO subject, email, name, provider
- Role: stores role name
- UserRole: association table for many-to-many
"""
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship, declarative_base

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
