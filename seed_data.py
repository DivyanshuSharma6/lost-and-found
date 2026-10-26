from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash
from app import app
from models import db, User, Item

sample_items = [
    {"type": "LOST", "cat": "Electronics", "title": "Apple AirPods Pro (2nd Gen)", "loc": "Central Library - 2nd Floor Reading Room", "desc": "White case with an anime sticker on the back. Left earbud was at 40% battery.", "alert": True},
    {"type": "FOUND", "cat": "Electronics", "title": "Dell 65W Type-C Laptop Charger", "loc": "Academic Block 1 - Room 204", "desc": "Black charger left plugged near the back row podium.", "alert": False},
    {"type": "LOST", "cat": "Electronics", "title": "iPad Air (Space Gray) with Apple Pencil", "loc": "Food Court 1 (FC-1) Booth Table", "desc": "Kept in a magnetic dark green folio case. Has student notes on GoodNotes.", "alert": True},
    {"type": "FOUND", "cat": "Electronics", "title": "boAt Bassheads Wired Earphones", "loc": "Old Mess Hall Counter", "desc": "Black and red wired earphones wrapped around a metal clip.", "alert": False},
    {"type": "LOST", "cat": "Electronics", "title": "Samsung Galaxy Watch 4", "loc": "Indoor Sports Complex Badminton Courts", "desc": "Black dial with a dark blue silicone strap.", "alert": False},
    {"type": "FOUND", "cat": "Electronics", "title": "Anker 20000mAh Power Bank", "loc": "Student Center Amphitheatre", "desc": "Black heavy power bank with dual USB ports and a short white cable.", "alert": False},
    {"type": "LOST", "cat": "Electronics", "title": "Logitech MX Master 3S Mouse", "loc": "Computer Lab 4 (AB-2)", "desc": "Pale gray ergonomic wireless mouse with a USB dongle missing.", "alert": False},
    {"type": "FOUND", "cat": "Electronics", "title": "OnePlus Nord Buds Case", "loc": "B1 Hostel Lobby", "desc": "White charging case only. No earbuds inside.", "alert": False},
    {"type": "LOST", "cat": "Electronics", "title": "Kindle Paperwhite (11th Gen)", "loc": "Library Lawn Benches", "desc": "Black device in a brown leather origami cover.", "alert": False},
    {"type": "FOUND", "cat": "Electronics", "title": "HP Wireless Keyboard", "loc": "Project Lab 102", "desc": "Slim black chiclet keyboard with missing battery door.", "alert": False},
    {"type": "LOST", "cat": "ID Cards & Wallets", "title": "MUJ Student ID Card - BCA Dept", "loc": "Gate 1 Turnstiles", "desc": "Lanyard with orange MUJ ribbon and transparent cardholder.", "alert": False},
    {"type": "FOUND", "cat": "ID Cards & Wallets", "title": "Brown Leather Tommy Hilfiger Wallet", "loc": "Main Cafeteria Billing Desk", "desc": "Contains metro card and hostel pass. Handed over for safe keeping.", "alert": True},
    {"type": "LOST", "cat": "ID Cards & Wallets", "title": "Black Cardholder with SBI Debit Card", "loc": "ATM Kiosk near Gate 2", "desc": "Contains driving license and debit card under initials A.S.", "alert": True},
    {"type": "FOUND", "cat": "ID Cards & Wallets", "title": "MUJ Campus RFID Access Card", "loc": "B3 Hostel Lift Ground Floor", "desc": "Blue campus RFID key fob card with serial ending in 4491.", "alert": False},
    {"type": "LOST", "cat": "ID Cards & Wallets", "title": "Wildcraft Canvas Tri-fold Wallet", "loc": "Football Ground Pavilion", "desc": "Navy blue wallet containing cash and a gym membership card.", "alert": False},
    {"type": "FOUND", "cat": "ID Cards & Wallets", "title": "HDFC Regalia Credit Card", "loc": "Nescafe Outlet Counter", "desc": "Found on the counter after evening rush. Name hidden for security verification.", "alert": False},
    {"type": "LOST", "cat": "Books & Notes", "title": "Operating Systems Concepts (Galvin, 10th Ed)", "loc": "Central Library Discussion Room 3", "desc": "Hardcover textbook with sticky notes on Chapter 5 (CPU Scheduling).", "alert": False},
    {"type": "FOUND", "cat": "Books & Notes", "title": "Classmate Spiral Notebook - Data Structures", "loc": "AB-1 Lecture Hall 101", "desc": "200-page blue spiral register filled with C++ code and tree diagrams.", "alert": False},
    {"type": "LOST", "cat": "Books & Notes", "title": "Black Moleskine Sketchbook", "loc": "Design Department Studio (FoD)", "desc": "Contains architectural perspective pencil sketches and portfolio ideas.", "alert": False},
    {"type": "FOUND", "cat": "Books & Notes", "title": "Calculus & Linear Algebra Reference Binder", "loc": "Math Tutoring Cell", "desc": "Ring binder folder with lecture printouts and assignment sheets.", "alert": False},
    {"type": "LOST", "cat": "Accessories", "title": "Titan Karishma Analog Men's Watch", "loc": "Gym Changing Room (Block B)", "desc": "Silver metal chain link strap with black rectangular dial.", "alert": False},
    {"type": "FOUND", "cat": "Accessories", "title": "Ray-Ban Aviator Sunglasses in Black Case", "loc": "Cricket Ground Spectator Stands", "desc": "Golden metal frame with dark green polarized lenses.", "alert": False},
    {"type": "LOST", "cat": "Accessories", "title": "Set of 3 Godrej Keys on MUJ Keychain", "loc": "Between Hostel Block B2 and Mess", "desc": "Three small keys with a red acrylic Manipal Jaipur keychain.", "alert": True},
    {"type": "FOUND", "cat": "Accessories", "title": "Milton 1000ml Stainless Steel Water Bottle", "loc": "Basketball Court Bleachers", "desc": "Matte black insulated flask with a minor dent on the bottom rim.", "alert": False},
    {"type": "LOST", "cat": "Accessories", "title": "Fastrack Black Rectangular Eyeglasses", "loc": "Auditorium Balcony Row F", "desc": "Prescription -2.5D spectacles in an embossed gray hard case.", "alert": False},
    {"type": "FOUND", "cat": "Accessories", "title": "Casio FX-991CW Scientific Calculator", "loc": "Exam Hall 301", "desc": "New model white/black scientific calculator with initials scratched on back.", "alert": False},
    {"type": "LOST", "cat": "Accessories", "title": "Gold Plated Kada / Bracelet", "loc": "Main Lawn Gazebo", "desc": "Smooth finished brass/gold-plated traditional wrist kada.", "alert": True},
    {"type": "FOUND", "cat": "Accessories", "title": "Navy Blue Decathlon Compact Umbrella", "loc": "Gate 1 Security Guard Desk", "desc": "Quechua manual folding umbrella left during evening rain.", "alert": False},
    {"type": "LOST", "cat": "Other", "title": "Yamaha FZ Bike Key with Leather Tag", "loc": "Student Parking Lot Area C", "desc": "Single ignition key with brown leather tag and small mini torch.", "alert": True},
    {"type": "FOUND", "cat": "Other", "title": "Yonex Nanoray 18i Badminton Racket", "loc": "Indoor Sports Complex Court 2", "desc": "Black and yellow racket with red grip tape.", "alert": False},
    {"type": "LOST", "cat": "Other", "title": "Cosmetics Pouch with Prescribed Medicines", "loc": "Girls Hostel Block G1 Common Lounge", "desc": "Floral zipped pouch containing asthma inhaler and daily medications.", "alert": True},
    {"type": "FOUND", "cat": "Other", "title": "Black Nike Gym Duffel Bag", "loc": "Synthetic Running Track Bench", "desc": "Contains clean gym towel, wrist wraps, and a shaker bottle.", "alert": False},
    {"type": "LOST", "cat": "Other", "title": "Lab Coat with Name Tag Embroidered", "loc": "Chemistry Lab 3rd Floor", "desc": "Standard white cotton full-sleeve apron with blue stitching on pocket.", "alert": False},
    {"type": "FOUND", "cat": "Other", "title": "Quechua 20L Backpack (Dark Gray)", "loc": "Bus Stop Shelter near Campus Exit", "desc": "Small daypack left on the concrete seat. Contains an empty tiffin box.", "alert": False},
    {"type": "LOST", "cat": "Other", "title": "Acoustic Guitar Capo & Dunlop Plectrums", "loc": "Music Club Jam Room (SAC)", "desc": "Silver metal trigger capo with small pouch of 5 medium guitar picks.", "alert": False}
]

def seed_database():
    with app.app_context():
        db.create_all()
        demo_user = User.query.filter_by(email="student@jaipur.manipal.edu").first()
        if not demo_user:
            demo_user = User(
                name="Aman Sharma",
                email="student@jaipur.manipal.edu",
                password_hash=generate_password_hash("Student@12345", method="pbkdf2:sha256"),
                role="USER"
            )
            db.session.add(demo_user)
            db.session.commit()
            print("Created default demo user: student@jaipur.manipal.edu")

        added_count = 0
        now = datetime.now(timezone.utc)
        for idx, data in enumerate(sample_items):
            exists = Item.query.filter_by(title=data["title"]).first()
            if not exists:
                item = Item(
                    user_id=demo_user.id,
                    item_type=data["type"],
                    title=data["title"],
                    category=data["cat"],
                    location=data["loc"],
                    description=data["desc"],
                    is_high_alert=data["alert"],
                    payment_status="DEMO_PAID" if data["alert"] else "FREE",
                    status="OPEN",
                    image_filename=None,
                    created_at=now - timedelta(hours=idx * 2)
                )
                db.session.add(item)
                added_count += 1

        db.session.commit()
        print(f"Successfully seeded {added_count} items into the database!")

if __name__ == "__main__":
    seed_database()
