A full-stack tool using React (frontend) and Flask + Selenium (backend) to fetch daily court cause lists from the New Delhi district court website. Handles dynamic content, captchas, and generates full-page PDFs packaged in a ZIP for download.

Features

Dynamic Court Complex and Court Number selection

Date input automatically formatted

Captcha handling with live preview and refresh

PDF generation of full cause lists using Chrome DevTools Protocol

ZIP download of PDFs

Thread-safe session management for multiple users

Tech Stack

Frontend: React.js, HTML, CSS

Backend: Flask, Python, Selenium, ChromeDriver

Libraries: base64, uuid, threading, zipfile, flask-cors

Installation
Prerequisites

Python 3.x

Node.js & npm

Chrome browser and matching ChromeDriver

Backend Setup

Open terminal in backend folder:
cd backend

Install Python dependencies:
pip install -r requirements.txt

Run the backend server:
python app.py
Backend runs at http://localhost:5000

Frontend Setup

Open terminal in frontend folder:
cd frontend

Install Node dependencies:
npm install

Run React app:
npm start
Frontend runs at http://localhost:3000

Usage

Open the frontend in browser

Select Court Complex, Court Number, and Date

Click Get Captcha

Enter captcha and click Submit

Download ZIP containing PDF with full cause list

Notes

Make sure the ChromeDriver path in app.py matches your local installation

Requires an active internet connection

Large tables may take a few seconds to render before PDF generation
