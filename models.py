from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='USER', nullable=False)  # 'USER' or 'ADMIN'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    items = db.relationship('Item', backref='reporter', lazy=True, foreign_keys='Item.user_id')
    claims = db.relationship('Claim', backref='claimant', lazy=True)
    bids = db.relationship('Bid', backref='bidder', lazy=True)


class Item(db.Model):
    __tablename__ = 'items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_type = db.Column(db.String(10), nullable=False)  # 'LOST' or 'FOUND'
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    location = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)

    # Core states: 'OPEN', 'RESOLVED', 'ARCHIVED', 'AUCTION_ACTIVE', 'AUCTION_SOLD'
    status = db.Column(db.String(20), default='OPEN', nullable=False, index=True)
    is_high_alert = db.Column(db.Boolean, default=False)
    payment_status = db.Column(db.String(20), default='FREE')

    # Live Handover Tracking
    is_live_tracking = db.Column(db.Boolean, default=False)
    current_lat = db.Column(db.Float, nullable=True)
    current_lng = db.Column(db.Float, nullable=True)

    # Unclaimed Property Bidding & Auction Pipeline
    base_bid = db.Column(db.Float, default=0.0)
    current_highest_bid = db.Column(db.Float, default=0.0)
    auction_ends_at = db.Column(db.DateTime, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    claims = db.relationship('Claim', backref='item', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='item', lazy=True, cascade='all, delete-orphan')
    bids = db.relationship('Bid', backref='item', lazy=True, cascade='all, delete-orphan')
    auction_winner = db.relationship('User', foreign_keys=[winner_id])


class Claim(db.Model):
    __tablename__ = 'claims'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    claimant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    proof_description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='PENDING', nullable=False)  # 'PENDING', 'APPROVED', 'REJECTED'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Bid(db.Model):
    __tablename__ = 'bids'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    bidder_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Feedback(db.Model):
    __tablename__ = 'feedback'

    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(100), nullable=False)
    user_email = db.Column(db.String(254), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))