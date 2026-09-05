import os
import io
import csv
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message as EmailMessage
from sqlalchemy import func
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from models import db, User, Item, Claim, Message, Feedback
from ml_engine import match_items, extract_dominant_color_name

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-bca-portal'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lost_and_found.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Image uploads
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Mail config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'iyerv259@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'ywdr jabt Idtl wogt')
app.config['MAIL_DEFAULT_SENDER'] = 'iyerv259@gmail.com'

mail = Mail(app)
db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'git remote set-url origin https://github.com/DivyanshuSharma6/lost-and-found-.git
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_match_notification(recipient_email, item_title, match_score):
    try:
        msg = EmailMessage(
            subject="[Campus Radar] High Similarity Match Found!",
            recipients=[recipient_email],
            body=f"Hello,\n\nA newly reported item has a {match_score}% description match with your item '{item_title}'.\n\nLog in to Campus Radar to review and initiate handover."
        )
        mail.send(msg)
    except Exception as e:
        print(f"Email delivery skipped (Mock Mode Active): {e}")

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

# --- Routes ---

@app.route('/')
def index():
    # Only show items that are OPEN and NOT stuck in pending payment
    items = Item.query.filter(
        Item.status == 'OPEN',
        Item.payment_status != 'PENDING'
    ).order_by(
        Item.is_high_alert.desc(),
        Item.created_at.desc()
    ).all()
    return render_template('index.html', items=items)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

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
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/report', methods=['GET', 'POST'])
@login_required
def report_item():
    if request.method == 'POST':
        item_type = request.form.get('item_type')
        title = request.form.get('title', '').strip()
        category = request.form.get('category')
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        is_urgent = request.form.get('high_alert') == 'yes'

        # Server-side duplicate prevention check (within last 30 seconds)
        recent_cutoff = datetime.utcnow() - timedelta(seconds=30)
        duplicate_check = Item.query.filter(
            Item.user_id == current_user.id,
            Item.title == title,
            Item.location == location,
            Item.created_at >= recent_cutoff
        ).first()

        if duplicate_check:
            if is_urgent and duplicate_check.payment_status == 'PENDING':
                return redirect(url_for('payment_gateway', item_id=duplicate_check.id))
            flash('This report was already submitted.', 'info')
            return redirect(url_for('index'))

        image_filename = None
        color_detected = ""
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                original_name = secure_filename(file.filename)
                image_filename = f"{uuid.uuid4().hex[:8]}_{original_name}"
                saved_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                file.save(saved_path)
                color_detected = extract_dominant_color_name(saved_path)

        final_desc = f"{description} (Detected color: {color_detected})" if color_detected else description

        new_item = Item(
            user_id=current_user.id,
            item_type=item_type,
            title=title,
            category=category,
            location=location,
            description=final_desc,
            image_filename=image_filename,
            is_high_alert=False,
            payment_status='PENDING' if is_urgent else 'FREE'
        )
        db.session.add(new_item)
        db.session.commit()

        if is_urgent:
            return redirect(url_for('payment_gateway', item_id=new_item.id))

        target_type = 'LOST' if item_type == 'FOUND' else 'FOUND'
        candidate_pool = Item.query.filter_by(item_type=target_type, status='OPEN').all()
        query_text = f"{title} {final_desc} {location} {color_detected}"
        matches = match_items(query_text, candidate_pool)

        for m in matches:
            if m['score'] >= 70.0 and m['item'].reporter.email:
                send_match_notification(m['item'].reporter.email, m['item'].title, m['score'])

        if matches:
            return render_template('matches.html', new_item=new_item, matches=matches)

        flash('Item reported successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('report.html')

@app.route('/payment/<int:item_id>')
@login_required
def payment_gateway(item_id):
    item = Item.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        flash('Unauthorized payment access.', 'danger')
        return redirect(url_for('index'))
    return render_template('payment.html', item=item)

@app.route('/payment/confirm/<int:item_id>', methods=['POST'])
@login_required
def confirm_payment(item_id):
    item = Item.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        return redirect(url_for('index'))

    item.payment_status = 'PAID'
    item.is_high_alert = True
    db.session.commit()

    flash('Payment verified! Listing pinned with High-Alert Priority.', 'success')
    return redirect(url_for('index'))

@app.route('/item/delete/<int:item_id>', methods=['POST'])
@login_required
def user_delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.user_id != current_user.id and current_user.role != 'ADMIN':
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('index'))

    Message.query.filter_by(item_id=item.id).delete()
    Claim.query.filter_by(item_id=item.id).delete()

    if item.image_filename:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image_filename)
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except Exception as e:
                print(f"Error removing file: {e}")

    db.session.delete(item)
    db.session.commit()
    flash('Item removed successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/chat/<int:item_id>/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def chat(item_id, receiver_id):
    item = Item.query.get_or_404(item_id)
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            msg = Message(
                item_id=item_id,
                sender_id=current_user.id,
                receiver_id=receiver_id,
                content=content
            )
            db.session.add(msg)
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
    item = Item.query.get_or_404(item_id)
    if request.method == 'POST':
        proof = request.form.get('proof_description')
        claim = Claim(
            item_id=item.id,
            claimant_id=current_user.id,
            proof_description=proof
        )
        db.session.add(claim)
        db.session.commit()
        flash('Claim submitted. Awaiting verification.', 'info')
        return redirect(url_for('index'))
    return render_template('claim.html', item=item)

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    name = request.form.get('name', 'Anonymous')
    email = request.form.get('email', 'not-provided@muj.manipal.edu')
    category = request.form.get('category', 'General')
    msg_text = request.form.get('message', '')

    if msg_text:
        feedback_entry = Feedback(
            user_name=name,
            user_email=email,
            category=category,
            message=msg_text
        )
        db.session.add(feedback_entry)
        db.session.commit()
        flash('Feedback submitted successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'ADMIN':
        flash('Administrator access required.', 'danger')
        return redirect(url_for('index'))

    expiration_threshold = datetime.utcnow() - timedelta(days=30)
    expired_items = Item.query.filter(Item.created_at < expiration_threshold, Item.status == 'OPEN').all()
    for exp_item in expired_items:
        exp_item.status = 'ARCHIVED'
    if expired_items:
        db.session.commit()

    total_items = Item.query.count()
    lost_count = Item.query.filter_by(item_type='LOST', status='OPEN').count()
    found_count = Item.query.filter_by(item_type='FOUND', status='OPEN').count()
    archived_count = Item.query.filter_by(status='ARCHIVED').count()
    
    pending_claims = Claim.query.filter_by(status='PENDING').all()
    approved_claims = Claim.query.filter_by(status='APPROVED').order_by(Claim.created_at.desc()).all()
    all_items = Item.query.order_by(Item.is_high_alert.desc(), Item.created_at.desc()).all()

    zone_stats = db.session.query(
        Item.location, func.count(Item.id)
    ).group_by(Item.location).order_by(func.count(Item.id).desc()).limit(5).all()

    return render_template(
        'admin.html',
        total_items=total_items,
        lost_count=lost_count,
        found_count=found_count,
        archived_count=archived_count,
        claims=pending_claims,
        approved_claims=approved_claims,
        items=all_items,
        zone_stats=zone_stats
    )

@app.route('/admin/claim/<int:claim_id>/<action>')
@login_required
def handle_claim(claim_id, action):
    if current_user.role != 'ADMIN':
        return redirect(url_for('index'))

    claim = Claim.query.get_or_404(claim_id)
    if action == 'approve':
        claim.status = 'APPROVED'
        item = Item.query.get(claim.item_id)
        if item:
            item.status = 'RESOLVED'
        flash(f'Claim #{claim.id} approved.', 'success')
    elif action == 'reject':
        claim.status = 'REJECTED'
        flash(f'Claim #{claim.id} rejected.', 'warning')

    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/claim/certificate/<int:claim_id>')
@login_required
def download_certificate(claim_id):
    claim = Claim.query.get_or_404(claim_id)
    if current_user.role != 'ADMIN' and current_user.id != claim.claimant_id:
        flash('Unauthorized access to clearance document.', 'danger')
        return redirect(url_for('index'))
        
    item = Item.query.get_or_404(claim.item_id)
    pdf_buffer = generate_clearance_pdf(claim, item)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"MUJ_Handover_Clearance_Claim_{claim.id}.pdf",
        mimetype='application/pdf'
    )

@app.route('/admin/export-csv')
@login_required
def export_security_csv():
    if current_user.role != 'ADMIN':
        flash('Administrator access required.', 'danger')
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

@app.route('/admin/item/delete/<int:item_id>')
@login_required
def delete_item(item_id):
    if current_user.role != 'ADMIN':
        return redirect(url_for('index'))

    item = Item.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted.', 'secondary')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/item/<int:item_id>/update-location', methods=['POST'])
@login_required
def update_location(item_id):
    item = Item.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    item.current_lat = data.get('lat')
    item.current_lng = data.get('lng')
    item.is_live_tracking = True
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/item/<int:item_id>/get-location', methods=['GET'])
@login_required
def get_location(item_id):
    item = Item.query.get_or_404(item_id)
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
    item = Item.query.get_or_404(item_id)
    return render_template('track_item.html', item=item)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)