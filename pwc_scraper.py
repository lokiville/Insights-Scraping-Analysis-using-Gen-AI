pip install tesseract pymupdf selenium beautifulsoup4

import os
os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"  # Tesseract data path (neeed for OCR)


import requests
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
    TimeoutException,
)
from bs4 import BeautifulSoup
import datetime
import time
import pymupdf  # PyMuPDF

def download_pdf_follow_redirects(url, save_dir):
    """Download PDF following redirects and save locally."""
    try:
        os.makedirs(save_dir, exist_ok=True)
        with requests.Session() as session:
            resp = session.head(url, allow_redirects=True)
            final_url = resp.url
            filename = os.path.basename(urlparse(final_url).path)
            if not filename.lower().endswith('.pdf'):
                filename += '.pdf'
            filepath = os.path.join(save_dir, filename)
            if os.path.exists(filepath):
                print(f"Already downloaded: {filename}")
                return filepath
            print(f"Downloading PDF from final URL: {final_url}")
            pdf_resp = session.get(final_url, stream=True)
            pdf_resp.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in pdf_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filepath
    except Exception as e:
        print(f"Failed to download PDF from {url}: {e}")
        return None

def extract_text_from_pdf_with_ocr(pdf_path):
    """
    Extract text from PDF using PyMuPDF,
    performing OCR on pages without selectable text.
    Requires Tesseract OCR installed on system.
    """
    text = ""
    try:
        doc = pymupdf.open(pdf_path)
        for page_num, page in enumerate(doc, start=1):
            page_text = page.get_text()
            if page_text.strip():
                text += page_text + "\n"
            else:
                # Perform OCR on image-based page
                try:
                    # get_textpage_ocr() triggers OCR and returns a TextPage object
                    tp = page.get_textpage_ocr()
                    ocr_text = page.get_text(textpage=tp)
                    if ocr_text.strip():
                        text += ocr_text + "\n"
                    else:
                        print(f"Warning: OCR returned empty text on page {page_num} of {pdf_path}")
                except Exception as ocr_err:
                    print(f"OCR failed on page {page_num} of {pdf_path}: {ocr_err}")
    except Exception as e:
        print(f"PDF extraction failed for {pdf_path}: {e}")
    return text.strip()

def scrape_pwc_articles_and_extract_text(base_url, pdf_save_dir='downloaded_pdfs'):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(base_url)
    wait = WebDriverWait(driver, 10)
    time.sleep(3)  # Initial wait for page load

    # Click "Load more" repeatedly until no more
    while True:
        try:
            load_more_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".collection__load-more"))
            )
            if load_more_btn.get_attribute('disabled'):
                break
            driver.execute_script("arguments[0].scrollIntoView();", load_more_btn)
            time.sleep(1)
            load_more_btn.click()
            time.sleep(3)  # Wait for new articles to load
        except (NoSuchElementException, TimeoutException, ElementClickInterceptedException):
            break

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()

    articles = []
    today = datetime.date.today()
    recent_date = today - datetime.timedelta(days=30)

    for a in soup.find_all('a', class_='collection__item-link'):
        time_tag = a.find('time')
        if not time_tag or not time_tag.has_attr('datetime'):
            continue
        date_str = time_tag['datetime']
        try:
            date_obj = datetime.datetime.strptime(date_str, '%d/%m/%y').date()
        except Exception:
            continue
        if date_obj < recent_date:
            continue

        title_tag = a.find('h4', class_='regular collection__item-heading')
        title = title_tag.get_text(strip=True) if title_tag else "No Title"
        link = a['href']
        article_url = link if link.startswith("http") else urljoin(base_url, link)

        # Download PDF (article_url redirects to PDF)
        pdf_path = download_pdf_follow_redirects(article_url, pdf_save_dir)
        pdf_content = ""
        if pdf_path:
            print(f"Extracting text from PDF: {pdf_path}")
            pdf_content = extract_text_from_pdf_with_ocr(pdf_path)

        articles.append({
            'title': title,
            'url': article_url,
            'publish_date': date_obj.strftime('%d/%m/%Y'),
            'pdf_path': pdf_path,
            'content': pdf_content
        })

    return articles

def save_articles_to_json(articles, filename="pwc_articles.json"):
    import json
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    base_url = "https://www.pwc.in/research-insights.html"
    articles = scrape_pwc_articles_and_extract_text(base_url)
    save_articles_to_json(articles)
    print(f"Extracted and saved {len(articles)} articles with PDF text.")
