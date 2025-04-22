import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import pdfplumber
import io
import trafilatura

def parse_date(date_string):
    """Parse date string like '19 Feb, 2025' to datetime object."""
    return datetime.strptime(date_string, '%d %b, %Y')

def extract_pdf_text(pdf_url):
    """Download PDF from URL and extract text content."""
    try:
        response = requests.get(pdf_url)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = ''
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + '\n'
            return text.strip()
    except Exception as e:
        print(f"Failed to extract PDF text from {pdf_url}: {e}")
        return ''

def extract_article_content(article_url):
    """
    Extract main article content using trafilatura.baseline and PDF content with BeautifulSoup.
    Returns publication date (datetime or None), extracted text, and PDF text.
    """
    try:
        response = requests.get(article_url)
        response.raise_for_status()
        html = response.text

        # Using trafilatura.baseline() on raw HTML string
        # Returns (lxml_element, extracted_text, length)
        postbody, extracted_text, length = trafilatura.baseline(html)

        # Extract publication date from page using BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        date_span = soup.find('span', id='heroCsiMonth')
        if date_span:
            try:
                pub_date = parse_date(date_span.text.strip())
            except Exception:
                pub_date = None
        else:
            pub_date = None

        # Extract PDF content (first PDF link found)
        pdf_content = ''
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.lower().endswith('.pdf'):
                pdf_url = href if href.startswith('http') else f"https://kpmg.com{href}"
                pdf_content = extract_pdf_text(pdf_url)
                break  # Only first PDF

        return pub_date, extracted_text, pdf_content
    except Exception as e:
        print(f"Failed to extract article content from {article_url}: {e}")
        return None, '', ''

def scrape_articles(topic_url, today, days_delta, scraped_articles):
    """Scrape article metadata from topic page and extract full content."""
    articles = []
    response = requests.get(topic_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    for teaser_div in soup.find_all('div', class_='cmp-teaser'):
        data_layer = teaser_div.get('data-cmp-data-layer')
        if not data_layer:
            continue
        try:
            data_json = json.loads(data_layer)
            key = next(iter(data_json))
            article_data = data_json[key]
        except (json.JSONDecodeError, StopIteration):
            continue
        
        pub_date_str_iso = article_data.get('repo:modifyDate')
        pub_date = None
        if pub_date_str_iso:
            try:
                pub_date = datetime.strptime(pub_date_str_iso, '%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                pub_date = None
        
        if pub_date is None:
            date_span = teaser_div.find('span', id='heroCsiMonth')
            if date_span:
                try:
                    pub_date = parse_date(date_span.text.strip())
                except ValueError:
                    pub_date = None
        
        if pub_date is None or today - pub_date > days_delta:
            continue
        
        title = article_data.get('dc:title', '').strip()
        title_header = teaser_div.find('h2', class_='cmp-teaser__title')
        if title_header:
            title_link = title_header.find('a')
            if title_link:
                url_path = title_link['href']
                full_url = f"https://kpmg.com{url_path}" if url_path.startswith('/') else url_path
            else:
                full_url = ''
        else:
            full_url = ''
        
        if full_url and "https://kpmg.com/in/en/insights" in full_url and full_url not in scraped_articles:
            article_pub_date, content, pdf_content = extract_article_content(full_url)
            final_pub_date = article_pub_date if article_pub_date else pub_date
            
            articles.append({
                'title': title,
                'url': full_url,
                'date_published': final_pub_date.strftime('%d %b, %Y') if final_pub_date else '',
                'content': content,
                'pdf_content': pdf_content
            })
            scraped_articles.add(full_url)
    return articles

def main():
    main_url = "https://kpmg.com/in/en/insights.html"
    today = datetime(2025, 4, 17)
    days_delta = timedelta(days=30)
    
    response = requests.get(main_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Collect topic URLs from main insights page
    topic_urls = []
    for a_tag in soup.find_all('a', class_='topic-pill'):
        topic_path = a_tag['href']
        full_topic_url = f"https://kpmg.com{topic_path}" if topic_path.startswith('/') else topic_path
        topic_urls.append(full_topic_url)
    
    all_articles = []
    scraped_articles = set()

    for url in topic_urls:
        articles = scrape_articles(url, today, days_delta, scraped_articles)
        all_articles.extend(articles)

    # Save all articles to JSON file
    with open('kpmg_articles.json', 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"Extracted {len(all_articles)} articles with trafilatura.baseline content.")

if __name__ == "__main__":
    main()
