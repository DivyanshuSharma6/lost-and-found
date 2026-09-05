# MUJ Campus Radar - Lost & Found Portal

An AI-driven campus asset recovery web application built for Manipal University Jaipur (MUJ).

## Tech Stack
- **Backend**: Python / Flask, Flask-SQLAlchemy, Flask-Login
- **Database**: SQLite
- **Machine Learning & CV**: Scikit-Learn (TF-IDF Match Engine), Pillow (Color Extraction)
- **Frontend**: Bootstrap 5, Leaflet.js (Live GPS Tracking)
- **Utilities**: ReportLab (Clearance PDF generation)

## Features
- **TF-IDF NLP Matching**: Automated lost-and-found similarity scoring.
- **Computer Vision Color Tagging**: Auto-extracts primary color attributes from item photos.
- **Live GPS Tracking**: Safe on-campus location broadcasting via Leaflet.js.
- **Emergency High-Alert**: Priority tier with simulated UPI checkout.
- **Admin Operations**: Hotspot analytics, 30-day auto-archiving, security audit CSV exports, and official clearance PDF certificates.

## Setup Instructions

1. Clone repository:
   ```bash
   git clone <your-repo-url>
   cd lost_and_found_bca