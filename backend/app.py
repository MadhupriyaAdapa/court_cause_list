import os
import io
import uuid
import zipfile
import shutil
import base64
import threading
from time import sleep
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------- CONFIG ----------
CHROME_DRIVER_PATH = r"C:\Users\madhu\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"
BASE_URL = "https://newdelhi.dcourts.gov.in/cause-list-%e2%81%84-daily-board/"
DOWNLOADS_ROOT = os.path.abspath("downloads")   # PDFs & zips
os.makedirs(DOWNLOADS_ROOT, exist_ok=True)
# ----------------------------

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()


def get_driver(headless=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1400,900")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    service = Service(CHROME_DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver


def screenshot_element_base64(element):
    png = element.screenshot_as_png
    return base64.b64encode(png).decode("ascii")


def print_page_to_pdf(driver):
    res = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
    return base64.b64decode(res["data"])


def safe_cleanup_session(session_id):
    with SESSIONS_LOCK:
        info = SESSIONS.pop(session_id, None)
    if not info:
        return
    try:
        driver = info.get("driver")
        if driver:
            driver.quit()
    except Exception:
        pass


# ---------------- ROUTES ----------------

# Fetch court complexes dynamically
@app.route("/api/court-complexes", methods=["GET"])
def court_complexes():
    driver = get_driver(headless=True)
    try:
        driver.get(BASE_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "est_code")))
        select_elem = driver.find_element(By.ID, "est_code")
        options = [
            {"value": o.get_attribute("value"), "label": o.text.strip()}
            for o in select_elem.find_elements(By.TAG_NAME, "option") 
            if o.get_attribute("value")
        ]
        driver.quit()
        return jsonify(options)
    except Exception as e:
        driver.quit()
        return jsonify({"error": str(e)}), 500


# Fetch court numbers dynamically for a given court complex
@app.route("/api/courts", methods=["GET"])
def courts():
    complex_value = request.args.get("complex")
    if not complex_value:
        return jsonify({"error": "complex query param required"}), 400

    driver = get_driver(headless=True)
    try:
        driver.get(BASE_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "est_code")))

        # Select the given court complex
        complex_select = driver.find_element(By.ID, "est_code")
        Select(complex_select).select_by_value(complex_value)
        sleep(0.5)  # small wait for JS to trigger

        # Wait for court options to populate (ignore the first empty option)
        court_select = WebDriverWait(driver, 10).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "#court option[value]:not([value=''])")
        )

        options = [
            {"value": o.get_attribute("value"), "label": o.text.strip()}
            for o in court_select
        ]

        driver.quit()
        return jsonify(options)

    except Exception as e:
        driver.quit()
        return jsonify({"error": str(e)}), 500


@app.route("/api/start-session", methods=["POST"])
def start_session():
    payload = request.json or {}
    date_value = payload.get("date")
    court_complex_value = payload.get("court_complex_value")
    court_number_value = payload.get("court_number_value")

    driver = get_driver(headless=False)  # can use headless=True if stable
    session_id = str(uuid.uuid4())
    session_folder = os.path.join(DOWNLOADS_ROOT, session_id)
    os.makedirs(session_folder, exist_ok=True)

    try:
        # Open page
        driver.get(BASE_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "est_code"))
        )

        # Select Court Complex
        complex_select = driver.find_element(By.ID, "est_code")
        if court_complex_value:
            Select(complex_select).select_by_value(court_complex_value)
            sleep(1)  # allow JS to update courts

        # Select Court Number
        court_select = driver.find_element(By.ID, "court")
        if court_number_value:
            Select(court_select).select_by_value(court_number_value)
            sleep(1)  # allow JS to refresh

        # Set Date
        date_elem = driver.find_element(By.ID, "date")
        if date_value:
            driver.execute_script("arguments[0].value = arguments[1];", date_elem, date_value)
            sleep(0.5)  # allow captcha to render

        # Captcha with retry
        captcha_el = None
        for _ in range(3):  # retry up to 3 times
            try:
                captcha_el = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "img#siwp_captcha_image_0"))
                )
                break
            except:
                sleep(1)

        if not captcha_el:
            driver.quit()
            return jsonify({"error": "Captcha not found after retries"}), 500

        captcha_b64 = screenshot_element_base64(captcha_el)

        # Store session
        with SESSIONS_LOCK:
            SESSIONS[session_id] = {"driver": driver, "folder": session_folder, "created": datetime.utcnow()}

        return jsonify({"session_id": session_id, "captcha_base64": captcha_b64}), 200

    except Exception as e:
        driver.quit()
        return jsonify({"error": str(e)}), 500

# Submit captcha, generate PDF & zip
@app.route("/api/submit-captcha", methods=["POST"])
def submit_captcha():
    payload = request.json or {}
    session_id = payload.get("session_id")
    captcha_text = payload.get("captcha_text")

    if not session_id or not captcha_text:
        return jsonify({"error": "session_id and captcha_text are required"}), 400

    with SESSIONS_LOCK:
        info = SESSIONS.get(session_id)
    if not info:
        return jsonify({"error": "invalid/expired session_id"}), 400

    driver = info["driver"]
    save_folder = info["folder"]

    try:
        # Enter captcha
        captcha_input = driver.find_element(By.ID, "siwp_captcha_value_0")
        captcha_input.clear()
        captcha_input.send_keys(captcha_text)
        sleep(0.3)

        # Click Search
        submit_btn = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Search']")
        submit_btn.click()

        # Wait for the results table to fully render
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#cnrResults table"))
        )
        sleep(1)  # allow JS to finish rendering

        # Optionally scroll table into view (ensures printToPDF captures it)
        table_el = driver.find_element(By.CSS_SELECTOR, "#cnrResults table")
        driver.execute_script("arguments[0].scrollIntoView();", table_el)
        sleep(0.5)

        # Print results to PDF
        pdf_bytes = driver.execute_cdp_cmd("Page.printToPDF", {
            "printBackground": True,
            "landscape": False,
            "paperWidth": 8.5,
            "paperHeight": 11,
            "marginTop": 0.4,
            "marginBottom": 0.4,
            "marginLeft": 0.4,
            "marginRight": 0.4,
            "preferCSSPageSize": True
        })
        pdf_data = base64.b64decode(pdf_bytes["data"])

        pdf_name = f"cause_{session_id}.pdf"
        pdf_path = os.path.join(save_folder, pdf_name)
        with open(pdf_path, "wb") as f:
            f.write(pdf_data)

        # Zip the PDF
        zip_name = os.path.join(DOWNLOADS_ROOT, f"{session_id}.zip")
        with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(pdf_path, pdf_name)

        # Cleanup driver
        driver.quit()
        with SESSIONS_LOCK:
            SESSIONS.pop(session_id, None)

        return jsonify({
            "ok": True,
            "session_id": session_id,
            "files": [pdf_name]
        }), 200

    except Exception as e:
        try:
            driver.quit()
        except Exception:
            pass
        with SESSIONS_LOCK:
            SESSIONS.pop(session_id, None)
        return jsonify({"error": str(e)}), 500

# Download zip
@app.route("/api/download-zip", methods=["GET"])
def download_zip():
    sid = request.args.get("session_id")
    if not sid:
        return jsonify({"error": "session_id required"}), 400
    zip_path = os.path.join(DOWNLOADS_ROOT, f"{sid}.zip")
    if not os.path.exists(zip_path):
        return jsonify({"error": "zip not found"}), 404
    return send_file(zip_path, as_attachment=True, download_name=f"cause_lists_{sid}.zip")


# Cleanup
@app.route("/api/cleanup", methods=["POST"])
def cleanup():
    payload = request.json or {}
    sid = payload.get("session_id")
    if not sid:
        return jsonify({"error": "session_id required"}), 400

    with SESSIONS_LOCK:
        info = SESSIONS.pop(sid, None)

    if info:
        try:
            drv = info.get("driver")
            if drv:
                drv.quit()
        except Exception:
            pass
        try:
            shutil.rmtree(info.get("folder"), ignore_errors=True)
        except Exception:
            pass

    zipf = os.path.join(DOWNLOADS_ROOT, f"{sid}.zip")
    if os.path.exists(zipf):
        os.remove(zipf)

    return jsonify({"ok": True}), 200


# ---------------- Run ----------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
