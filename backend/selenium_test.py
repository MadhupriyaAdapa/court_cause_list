from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Chrome options (headless optional)
chrome_options = Options()
chrome_options.add_argument("--headless")  # runs Chrome in background

# Use your correct ChromeDriver path
service = Service(r"C:\Users\madhu\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe")
driver = webdriver.Chrome(service=service, options=chrome_options)

# Test by opening the cause list page
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/?p=cause_list/")
print(driver.title)  # should print page title

driver.quit()
