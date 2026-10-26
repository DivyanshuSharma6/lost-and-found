import os
import io
import csv
import uuid
from datetime import datetime, timedelta, timezone

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, send_file, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from flask_mail import Mail, Message as EmailMessage
from sqlalchemy import func
from PIL import Image, UnidentifiedImageError
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from models import db, User, Item, Claim, Bid, Message, Feedback
from ml_engine import match_items, extract_dominant_color_name

app = Flask(__name__)

is_vercel = bool(os.environ.get("VERCEL"))
secret_key = os.environ.get("SECRET_KEY")

# Safe fallback so serverless functions never raise on init
app.config["SECRET_KEY"] = secret_key or "local-dev-secret-key-muj-radar-2026"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False

database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# On Vercel, serverless filesystems are read-only except /tmp
if is_vercel:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:////tmp/lost_and_found.db"
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///lost_and_found.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

is_vercel = bool(os.environ.get('VERCEL'))

if is_vercel:
    UPLOAD_FOLDER = os.path.join('/tmp', 'uploads')
else:
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Safely ignore instance folder creation on Vercel's read-only filesystem
try:
    if not is_vercel:
        os.makedirs(app.instance_path, exist_ok=True)
except OSError:
    pass

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1')
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER') or app.config['MAIL_USERNAME']

mail = Mail(app)
db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def ensure_db():
    # Guarantees tables exist in /tmp SQLite on cold start
    if not getattr(app, '_got_first_request', False):
        try:
            db.create_all()
            app._got_first_request = True
        except Exception as e:
            app.logger.warning(f"DB creation on request error: {e}")
@app.errorhandler(413)
def request_entity_too_large(error):
    flash('The uploaded image is too large! Maximum allowed upload size is 16 MB.', 'danger')
    return redirect(url_for('report_item')), 413

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def allowed_file(filename):
    return bool(filename and '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS)

def validate_and_compress_image(file_storage, save_path):
    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            img.verify()

        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            img.save(save_path, format="JPEG", quality=82, optimize=True)
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False

def send_match_notification(recipient_email, item_title, match_score):
    if not app.config['MAIL_USERNAME']:
        return
    try:
        msg = EmailMessage(
            subject="[Campus Radar] High Similarity Match Found!",
            recipients=[recipient_email],
            body=f"Hello,\n\nA newly reported item has a {match_score}% description match with your item '{item_title}'.\n\nLog in to Campus Radar to review and coordinate recovery."
        )
        mail.send(msg)
    except Exception as e:
        app.logger.warning(f"Email delivery skipped: {e}")

def generate_clearance_pdf(claim, item):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFillColor(colors.HexColor('#0D2240'))
    p.rect(0, 720, 612, 80, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 18)
    p.drawString(40, 755, "MANIPAL UNIVERSITY JAIPUR")
    p.setFont("Helvetica", 11)
    p.drawString(40, 735, "Campus Lost & Found - Official Handover Clearance Certificate")

    p.setFillColor(colors.HexColor('#1F2937'))
    p.setFont("Helvetica-Bold", 13)
    p.drawString(40, 680, f"Claim Clearance ID: #MUJ-CLR-{claim.id:04d}")
    p.setFont("Helvetica", 10)
    p.drawString(40, 655, f"Date Issued: {datetime.now().strftime('%d %B %Y, %I:%M %p')}")
    p.drawString(40, 640, f"Item ID: #{item.id} | Category: {item.category}")
    p.drawString(40, 625, f"Item Title: {item.title}")
    p.drawString(40, 610, f"Original Found Location: {item.location}")

    p.setStrokeColor(colors.HexColor('#E5E7EB'))
    p.line(40, 595, 572, 595)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, 575, "Verified Claimant Details")
    p.setFont("Helvetica", 10)
    p.drawString(40, 555, f"Name: {claim.claimant.name}")
    p.drawString(40, 540, f"Institutional Email: {claim.claimant.email}")
    p.drawString(40, 520, "Submitted Proof of Ownership:")

    text_obj = p.beginText(50, 500)
    text_obj.setFont("Helvetica-Oblique", 9)
    p.setFillColor(colors.HexColor('#4B5563'))
    proof_snippet = claim.proof_description[:200] + ('...' if len(claim.proof_description) > 200 else '')
    text_obj.textLines(proof_snippet)
    p.drawText(text_obj)

    p.setStrokeColor(colors.HexColor('#9CA3AF'))
    p.line(50, 410, 220, 410)
    p.line(390, 410, 560, 410)
    p.setFillColor(colors.HexColor('#1F2937'))
    p.setFont("Helvetica", 9)
    p.drawString(50, 395, "Claimant Signature")
    p.drawString(390, 395, "Campus Security / Admin Signature")

    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(colors.HexColor('#E65100'))
    p.drawString(40, 340, "NOTICE: Present this certificate at the Campus Security Control Room for item collection.")
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

@app.route('/')
def index():
    # Auto-conclude expired auctions
    now = datetime.now(timezone.utc)
    expired_auctions = Item.query.filter(
        Item.status == 'AUCTION_ACTIVE',
        Item.auction_ends_at < now
    ).all()
    for exp in expired_auctions:
        exp.status = 'AUCTION_SOLD' if exp.winner_id else 'ARCHIVED'
    if expired_auctions:
        db.session.commit()

    items = Item.query.filter(
        Item.status.in_(['OPEN', 'AUCTION_ACTIVE']),
        Item.payment_status != 'PENDING'
    ).order_by(
        Item.is_high_alert.desc(),
        Item.created_at.desc()
    ).all()
    return render_template('index.html', items=items)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if not name or len(name) > 100 or not email or len(email) > 254 or len(password) < 8 or len(password) > 128:
            flash('Enter a valid name, email, and password between 8 and 128 characters.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page if next_page and next_page.startswith('/') else url_for('index'))

        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/report', methods=['GET', 'POST'])
@login_required
def report_item():
    if request.method != 'POST':
        return render_template('report.html')

    item_type = (request.form.get('item_type') or '').strip().upper()
    title = (request.form.get('title') or '').strip()
    category = (request.form.get('category') or '').strip()
    location = (request.form.get('location') or '').strip()
    description = (request.form.get('description') or '').strip()
    is_urgent = request.form.get('high_alert') == 'yes'

    if item_type not in {'LOST', 'FOUND'} or not title or not category or not location or not description:
        flash('Please complete all required fields.', 'danger')
        return redirect(url_for('report_item'))

    if len(title) > 150 or len(category) > 80 or len(location) > 160 or len(description) > 2000:
        flash('One or more fields exceed the character limit.', 'danger')
        return redirect(url_for('report_item'))

    recent_cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)
    duplicate = Item.query.filter(
        Item.user_id == current_user.id,
        Item.title == title,
        Item.location == location,
        Item.created_at >= recent_cutoff
    ).first()

    if duplicate:
        if is_urgent and duplicate.payment_status == 'PENDING':
            return redirect(url_for('payment_gateway', item_id=duplicate.id))
        flash('This item was just submitted.', 'info')
        return redirect(url_for('index'))

    image_filename = None
    color_detected = ''
    uploaded = request.files.get('image')

    if uploaded and uploaded.filename:
        if not allowed_file(uploaded.filename):
            flash('Invalid file format. Please upload PNG, JPG, JPEG, or WEBP.', 'danger')
            return redirect(url_for('report_item'))

        safe_name = secure_filename(uploaded.filename) or 'upload.jpg'
        image_filename = f"{uuid.uuid4().hex}_{safe_name}"
        saved_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)

        if not validate_and_compress_image(uploaded, saved_path):
            flash('Uploaded file is corrupted or not an image.', 'danger')
            return redirect(url_for('report_item'))

        try:
            color_detected = extract_dominant_color_name(saved_path) or ''
        except Exception:
            app.logger.exception('Color extraction failed')

    final_description = f"{description}\n(Dominant color: {color_detected})" if color_detected else description

    new_item = Item(
        user_id=current_user.id,
        item_type=item_type,
        title=title,
        category=category,
        location=location,
        description=final_description,
        image_filename=image_filename,
        is_high_alert=False,
        payment_status='PENDING' if is_urgent else 'FREE'
    )
    db.session.add(new_item)
    db.session.commit()

    if is_urgent:
        return redirect(url_for('payment_gateway', item_id=new_item.id))

    target_type = 'FOUND' if item_type == 'LOST' else 'LOST'
    candidates = Item.query.filter_by(item_type=target_type, status='OPEN').all()
    query_text = f"{title} {category} {final_description} {location} {color_detected}"
    matches = match_items(query_text, candidates, threshold=0.15)

    for match in matches:
        matched_item = match.get('item')
        if match.get('score', 0) >= 70.0 and matched_item and matched_item.reporter and matched_item.reporter.email:
            send_match_notification(matched_item.reporter.email, matched_item.title, match['score'])

    if matches:
        return render_template('matches.html', new_item=new_item, matches=matches)

    flash('Item reported successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/payment/<int:item_id>')
@login_required
def payment_gateway(item_id):
    item = db.session.get(Item, item_id)
    if not item or item.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
    return render_template('payment.html', item=item)

@app.route('/payment/confirm/<int:item_id>', methods=['POST'])
@login_required
def confirm_payment(item_id):
    item = db.session.get(Item, item_id)
    if not item or item.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))

    item.payment_status = 'DEMO_PAID'
    item.is_high_alert = True
    db.session.commit()
    flash('High-alert activated successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/item/delete/<int:item_id>', methods=['POST'])
@login_required
def user_delete_item(item_id):
    item = db.session.get(Item, item_id)
    if not item or (item.user_id != current_user.id and current_user.role != 'ADMIN'):
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('index'))

    if item.image_filename:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image_filename)
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except OSError as e:
                app.logger.warning(f"Error removing image: {e}")

    db.session.delete(item)
    db.session.commit()
    flash('Item removed.', 'info')
    return redirect(url_for('index'))

@app.route('/inbox')
@login_required
def inbox():
    all_user_messages = Message.query.filter(
        (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
    ).order_by(Message.created_at.desc()).all()

    conversations = {}
    for msg in all_user_messages:
        other_user_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        conv_key = (msg.item_id, other_user_id)

        if conv_key not in conversations:
            item = db.session.get(Item, msg.item_id)
            other_user = db.session.get(User, other_user_id)
            if item and other_user:
                conversations[conv_key] = {
                    'item': item,
                    'other_user': other_user,
                    'last_message': msg.content,
                    'last_time': msg.created_at,
                    'is_incoming': (msg.receiver_id == current_user.id)
                }

    return render_template('inbox.html', conversations=list(conversations.values()))

@app.route('/chat/<int:item_id>/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def chat(item_id, receiver_id):
    item = db.session.get(Item, item_id)
    receiver = db.session.get(User, receiver_id)
    if not item or not receiver:
        flash('Conversation not found.', 'danger')
        return redirect(url_for('index'))

    if receiver_id == current_user.id:
        flash('You cannot message yourself.', 'warning')
        return redirect(url_for('index'))

    if current_user.id != item.user_id and receiver_id != item.user_id and current_user.role != 'ADMIN':
        flash('Access restricted to item reporter and claimants.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        content = (request.form.get('content') or '').strip()
        if not content or len(content) > 2000:
            flash('Message must contain between 1 and 2000 characters.', 'danger')
            return redirect(url_for('chat', item_id=item_id, receiver_id=receiver_id))

        message = Message(
            item_id=item_id,
            sender_id=current_user.id,
            receiver_id=receiver_id,
            content=content
        )
        db.session.add(message)
        db.session.commit()
        return redirect(url_for('chat', item_id=item_id, receiver_id=receiver_id))

    messages = Message.query.filter(
        (Message.item_id == item_id) &
        (((Message.sender_id == current_user.id) & (Message.receiver_id == receiver_id)) |
         ((Message.sender_id == receiver_id) & (Message.receiver_id == current_user.id)))
    ).order_by(Message.created_at.asc()).all()

    return render_template('chat.html', item=item, messages=messages, receiver_id=receiver_id)

@app.route('/claim/<int:item_id>', methods=['GET', 'POST'])
@login_required
def submit_claim(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        flash('Item not found.', 'danger')
        return redirect(url_for('index'))

    if item.user_id == current_user.id:
        flash('You cannot claim an item you reported.', 'danger')
        return redirect(url_for('index'))

    if item.status != 'OPEN':
        flash('This item is no longer available.', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        proof = (request.form.get('proof_description') or '').strip()
        if len(proof) < 10 or len(proof) > 2000:
            flash('Please provide verification details between 10 and 2000 characters.', 'danger')
            return redirect(url_for('submit_claim', item_id=item.id))

        existing_claim = Claim.query.filter_by(
            item_id=item.id, claimant_id=current_user.id, status='PENDING'
        ).first()

        if existing_claim:
            flash('You already have a pending claim for this item.', 'info')
            return redirect(url_for('index'))

        claim = Claim(item_id=item.id, claimant_id=current_user.id, proof_description=proof)
        db.session.add(claim)
        db.session.commit()
        flash('Claim submitted successfully. Awaiting security review.', 'success')
        return redirect(url_for('index'))

    return render_template('claim.html', item=item)

@app.route('/auction/<int:item_id>/bid', methods=['POST'])
@login_required
def place_bid(item_id):
    item = db.session.get(Item, item_id)
    if not item or item.status != 'AUCTION_ACTIVE':
        flash('This auction is not active.', 'danger')
        return redirect(url_for('index'))

    now = datetime.now(timezone.utc)
    if item.auction_ends_at and now > item.auction_ends_at.replace(tzinfo=timezone.utc):
        item.status = 'AUCTION_SOLD' if item.winner_id else 'ARCHIVED'
        db.session.commit()
        flash('This auction has already ended.', 'warning')
        return redirect(url_for('index'))

    try:
        bid_amount = float(request.form.get('bid_amount', 0))
    except (ValueError, TypeError):
        flash('Please enter a valid bid amount.', 'danger')
        return redirect(url_for('index'))

    min_required = item.current_highest_bid if item.current_highest_bid > 0 else item.base_bid
    if bid_amount <= min_required:
        flash(f'Bid must be strictly higher than current amount (₹{min_required:.2f}).', 'danger')
        return redirect(url_for('index'))

    new_bid = Bid(item_id=item.id, bidder_id=current_user.id, amount=bid_amount)
    item.current_highest_bid = bid_amount
    item.winner_id = current_user.id
    db.session.add(new_bid)
    db.session.commit()

    flash(f'Bid of ₹{bid_amount:.2f} placed successfully! You are the top bidder.', 'success')
    return redirect(url_for('index'))

@app.route('/admin/item/<int:item_id>/start-auction', methods=['POST'])
@login_required
def start_auction(item_id):
    if current_user.role != 'ADMIN':
        flash('Administrator privileges required.', 'danger')
        return redirect(url_for('index'))

    item = db.session.get(Item, item_id)
    if not item or item.item_type != 'FOUND':
        flash('Only found items can be moved to the auction block.', 'danger')
        return redirect(url_for('admin_dashboard'))

    try:
        base_bid = float(request.form.get('base_bid', 50.0))
        duration_days = int(request.form.get('duration_days', 3))
    except (ValueError, TypeError):
        base_bid = 50.0
        duration_days = 3

    item.status = 'AUCTION_ACTIVE'
    item.base_bid = base_bid
    item.current_highest_bid = base_bid
    item.auction_ends_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
    db.session.commit()

    flash(f"Item #{item.id} launched in campus student auction with base bid ₹{base_bid:.2f}.", 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    name = (request.form.get('name') or 'Anonymous').strip()
    email = (request.form.get('email') or 'student@jaipur.manipal.edu').strip().lower()
    category = (request.form.get('category') or 'General').strip()
    msg_text = (request.form.get('message') or '').strip()

    if msg_text:
        feedback_entry = Feedback(
            user_name=name[:100],
            user_email=email[:254],
            category=category[:50],
            message=msg_text[:2000]
        )
        db.session.add(feedback_entry)
        db.session.commit()
        flash('Thank you! Your feedback was forwarded to Campus Security.', 'success')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'ADMIN':
        flash('Administrator privileges required.', 'danger')
        return redirect(url_for('index'))

    # Unclaimed items past 60 days
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    unclaimed_eligible = Item.query.filter(
        Item.item_type == 'FOUND',
        Item.status == 'OPEN',
        Item.created_at < retention_cutoff
    ).all()

    total_items = Item.query.count()
    lost_count = Item.query.filter_by(item_type='LOST', status='OPEN').count()
    found_count = Item.query.filter_by(item_type='FOUND', status='OPEN').count()
    archived_count = Item.query.filter(Item.status.in_(['ARCHIVED', 'AUCTION_SOLD'])).count()
    active_auctions_count = Item.query.filter_by(status='AUCTION_ACTIVE').count()
    
    pending_claims = Claim.query.filter_by(status='PENDING').all()
    approved_claims = Claim.query.filter_by(status='APPROVED').order_by(Claim.created_at.desc()).all()
    all_items = Item.query.order_by(Item.is_high_alert.desc(), Item.created_at.desc()).all()
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()

    zone_stats = db.session.query(
        Item.location, func.count(Item.id)
    ).group_by(Item.location).order_by(func.count(Item.id).desc()).limit(5).all()

    return render_template(
        'admin.html',
        total_items=total_items,
        lost_count=lost_count,
        found_count=found_count,
        archived_count=archived_count,
        active_auctions_count=active_auctions_count,
        unclaimed_eligible=unclaimed_eligible,
        claims=pending_claims,
        approved_claims=approved_claims,
        items=all_items,
        feedbacks=feedbacks,
        zone_stats=zone_stats
    )

@app.route('/admin/claim/<int:claim_id>/<action>', methods=['POST'])
@login_required
def handle_claim(claim_id, action):
    if current_user.role != 'ADMIN':
        flash('Administrator privileges required.', 'danger')
        return redirect(url_for('index'))

    if action not in {'approve', 'reject'}:
        return jsonify({'error': 'Invalid action'}), 400

    claim = db.session.get(Claim, claim_id)
    if not claim:
        flash('Claim not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if claim.status != 'PENDING':
        flash('This claim has already been processed.', 'info')
        return redirect(url_for('admin_dashboard'))

    if action == 'approve':
        item = db.session.get(Item, claim.item_id)
        claim.status = 'APPROVED'
        if item:
            item.status = 'RESOLVED'
        Claim.query.filter(
            Claim.item_id == claim.item_id,
            Claim.id != claim.id,
            Claim.status == 'PENDING'
        ).update({Claim.status: 'REJECTED'}, synchronize_session=False)
        flash(f'Claim #{claim.id} approved.', 'success')
    else:
        claim.status = 'REJECTED'
        flash(f'Claim #{claim.id} rejected.', 'warning')

    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/claim/certificate/<int:claim_id>')
@login_required
def download_certificate(claim_id):
    claim = db.session.get(Claim, claim_id)
    if not claim:
        flash('Claim record not found.', 'danger')
        return redirect(url_for('index'))

    if current_user.role != 'ADMIN' and current_user.id != claim.claimant_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))

    if claim.status != 'APPROVED':
        flash('Clearance certificates are only generated for approved claims.', 'warning')
        return redirect(url_for('admin_dashboard' if current_user.role == 'ADMIN' else 'index'))

    item = db.session.get(Item, claim.item_id)
    pdf_buffer = generate_clearance_pdf(claim, item)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f'MUJ_Handover_Clearance_Claim_{claim.id}.pdf',
        mimetype='application/pdf'
    )

@app.route('/admin/export-csv')
@login_required
def export_security_csv():
    if current_user.role != 'ADMIN':
        flash('Administrator privileges required.', 'danger')
        return redirect(url_for('index'))

    items = Item.query.order_by(Item.created_at.desc()).all()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow([
        'Item ID', 'Type', 'Title', 'Category', 
        'Location', 'High Alert', 'Status', 'Date Reported', 'Reporter Email'
    ])

    for item in items:
        writer.writerow([
            f"MUJ-ITM-{item.id:04d}",
            item.item_type,
            item.title,
            item.category,
            item.location,
            'YES' if item.is_high_alert else 'NO',
            item.status,
            item.created_at.strftime('%Y-%m-%d %H:%M'),
            item.reporter.email if item.reporter else 'N/A'
        ])

    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    filename = f"MUJ_Security_Audit_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/admin/item/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    if current_user.role != 'ADMIN':
        flash('Administrator privileges required.', 'danger')
        return redirect(url_for('index'))

    item = db.session.get(Item, item_id)
    if not item:
        flash('Item not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if item.image_filename:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image_filename)
        if os.path.isfile(image_path):
            try:
                os.remove(image_path)
            except OSError as exc:
                app.logger.warning(f'Could not delete image: {exc}')

    db.session.delete(item)
    db.session.commit()
    flash('Item deleted permanently.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/item/<int:item_id>/update-location', methods=['POST'])
@login_required
def update_location(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404

    if item.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    try:
        lat = float(data.get('lat'))
        lng = float(data.get('lng'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Coordinates must be valid numbers.'}), 400

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({'error': 'Coordinates out of range.'}), 400

    item.current_lat, item.current_lng = lat, lng
    item.is_live_tracking = True
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/item/<int:item_id>/stop-location', methods=['POST'])
@login_required
def stop_location(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404

    if item.user_id != current_user.id and current_user.role != 'ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403

    item.is_live_tracking = False
    item.current_lat = None
    item.current_lng = None
    db.session.commit()
    return jsonify({'status': 'stopped'})

@app.route('/api/item/<int:item_id>/get-location', methods=['GET'])
@login_required
def get_location(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404

    if not item.is_live_tracking or item.current_lat is None:
        return jsonify({'is_tracking': False})

    return jsonify({
        'is_tracking': True,
        'lat': item.current_lat,
        'lng': item.current_lng
    })

@app.route('/track/<int:item_id>')
@login_required
def track_item_view(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        flash('Item not found.', 'danger')
        return redirect(url_for('index'))

    return render_template('track_item.html', item=item)

@app.route('/download-synopsis')
def download_synopsis():
    synopsis_path = os.path.join(app.root_path, 'MUJ_Campus_Radar_Synopsis.docx')
    if not os.path.exists(synopsis_path):
        flash('Synopsis file not found! Please run python3 generate_synopsis_docx.py first.', 'danger')
        return redirect(url_for('index'))

    return send_file(
        synopsis_path,
        as_attachment=True,
        download_name='MUJ_Campus_Radar_Synopsis.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
@app.route('/setup-admin-secret-2026')
def setup_admin_secret():
    db.create_all()  # Force create all tables first
    
    admin_email = 'divyanshusharma9352@gmail.com'
    user = User.query.filter_by(email=admin_email).first()
    
    if not user:
        user = User(
            name='Divyanshu Sharma',
            email=admin_email,
            password_hash=generate_password_hash('Admin@12345', method='pbkdf2:sha256'),
            role='ADMIN'
        )
        db.session.add(user)
    else:
        user.role = 'ADMIN'
        user.password_hash = generate_password_hash('Admin@12345', method='pbkdf2:sha256')
        
    db.session.commit()
    return f"<h1>Success! Database ready and Admin activated:</h1><p>Email: <b>{admin_email}</b><br>Password: <b>Admin@12345</b></p><p><a href='/login'>Click here to Login</a></p>"
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_DEBUG') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)