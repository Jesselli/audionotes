from dataclasses import dataclass

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import and_

db = SQLAlchemy()
Session = scoped_session(sessionmaker())


class BaseModel:
    __allow_unmapped__ = True

    def add_to_db(self):
        Session.add(self)
        Session.commit()

    def delete_from_db(self):
        Session.delete(self)
        Session.commit()


@dataclass
class Snippet(db.Model, BaseModel):
    id: int
    user_id: int
    source_id: int
    time: int
    duration: int
    created_at: str
    text: str

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False)
    time = db.Column(db.Integer, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    text = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<Snippet {self.id} - {self.text}>"

    @classmethod
    def find_by_id(cls, snippet_id):
        return Session.query(Snippet).filter_by(id=snippet_id).first()

    @classmethod
    def get_snippets_since(cls, source_id, since):
        filter = and_(Snippet.source_id == source_id, Snippet.created_at > since)
        return Session.query(Snippet).filter(filter).all()

    def update_text_in_db(self, text):
        self.text = text
        Session.commit()


@dataclass
class Source(db.Model, BaseModel):
    id: int
    url: str
    title: str
    thumb_url: str
    provider: str
    snippets: list

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False, unique=True)
    title = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="source")
    thumb_url = db.Column(db.String(255))
    provider = db.Column(db.String(255))

    def __repr__(self):
        return f"<Source {self.id} - {self.title}>"

    @classmethod
    def get_user_sources_snippets(cls, user_id):
        sources = (
            Session.query(Source)
            .join(Snippet)
            .filter(Snippet.user_id == user_id)
            .order_by(Snippet.created_at.desc())
            .all()
        )
        for source in sources:
            source.snippets.sort(key=lambda x: x.time, reverse=False)
        return sources

    @classmethod
    def find_by_id(cls, source_id):
        return Session.query(Source).filter_by(id=source_id).first()

    @classmethod
    def find_snippet(cls, url, time, duration):
        filter = and_(
            Snippet.source_id == Source.id,
            Snippet.time == time,
            Snippet.duration == duration,
        )
        return Session.query(Source).filter_by(url=url).filter(filter).first()


@dataclass
class SyncRecord(db.Model, BaseModel):
    id: int
    user_id: int
    source_id: int
    synced_at: str

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False)
    synced_at = db.Column(db.DateTime, default=db.func.now())

    @classmethod
    def get_user_sync_record(cls, source_id, user_id):
        sync_record = (
            Session.query(SyncRecord)
            .filter_by(user_id=user_id, source_id=source_id)
            .order_by(SyncRecord.synced_at.desc())
            .first()
        )
        return sync_record

    @classmethod
    def find_by_user_source(cls, user_id, source_id):
        return (
            Session.query(SyncRecord)
            .filter_by(user_id=user_id, source_id=source_id)
            .first()
        )

    def update_sync_time(self, time=db.func.now()):
        self.synced_at = time
        Session.commit()


@dataclass
class User(db.Model, UserMixin, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="user")
    devices = db.relationship("Device", backref="user")

    def __repr__(self):
        return f"<User {self.id} - {self.name}>"

    @classmethod
    def get_all(cls):
        return Session.query(User).all()

    @classmethod
    def create(cls, email, password):
        user = User(email=email, password=password)
        Session.add(user)
        Session.commit()
        return user

    @classmethod
    def find_by_email(cls, email):
        return Session.query(User).filter_by(email=email).first()

    @classmethod
    def get_by_id(cls, user_id):
        return Session.query(User).get(user_id)


class UserSettings(db.Model, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    setting_name = db.Column(db.String(80), nullable=False)
    setting_value = db.Column(db.String(80), nullable=False)

    @classmethod
    def find_by_user_id(cls, user_id):
        return Session.query(UserSettings).filter_by(user_id=user_id).all()

    @classmethod
    def find_by_user_and_setting_name(cls, user_id, setting_name):
        return (
            Session.query(UserSettings)
            .filter_by(user_id=user_id, setting_name=setting_name)
            .first()
        )

    @classmethod
    def get_value(cls, user_id, setting_name):
        setting = cls.find_by_user_and_setting_name(user_id, setting_name)
        if setting:
            return setting.setting_value
        return None

    def update_value(self, value):
        self.setting_value = value
        Session.commit()


class Device(db.Model, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    device_key = db.Column(db.String(80), nullable=False)

    @classmethod
    def find_by_name(cls, device_name):
        return Session.query(Device).filter_by(device_name=device_name).first()

    @classmethod
    def find_devices_for_user(cls, user_id):
        return Session.query(Device).filter_by(user_id=user_id).all()

    @classmethod
    def find_by_key(cls, device_key):
        return Session.query(Device).filter_by(device_key=device_key).first()

    @classmethod
    def find_by_id(cls, device_id):
        return Session.query(Device).get(device_id)
