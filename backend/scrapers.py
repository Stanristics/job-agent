"""
Job scrapers for Indeed, StepStone, LinkedIn, and Xing.
- Searches all of Germany
- Filters to jobs posted in the last 24 hours only
- Skips jobs already in the database (handled by main.py via URL dedup)
"""

import requests
from bs4 import BeautifulSoup
import time
import random
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}

def _get(url, params=None, max_retries=2, timeout=30):
    """
    Fetch a URL with retry logic. Cloud server IPs (like Render's) are often
    rate-limited or temporarily blocked by job sites — retrying with a short
    delay sometimes succeeds where the first attempt times out or fails.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = random.uniform(2, 5) * (attempt + 1)  # increasing backoff
                logger.info(f"Retry {attempt + 1}/{max_retries} for {url} after {wait:.1f}s — {e}")
                time.sleep(wait)
            continue
    logger.warning(f"Request failed after {max_retries + 1} attempts: {url} — {last_error}")
    return None

def is_recent(date_str: str) -> bool:
    """
    Returns True if the date string suggests the job was posted
    within the last 24 hours. Handles common formats like:
    'Today', 'Just posted', 'Heute', '1 day ago', '23 hours ago', etc.
    """
    if not date_str:
        return True  # if no date, include it to be safe
    s = date_str.lower().strip()
    recent_keywords = [
        'today', 'just posted', 'just now', 'heute', 'gerade',
        'soeben', 'vor wenigen', '1 day ago', 'an hour', 'hours ago',
        'hour ago', 'minute', 'stunde', 'stunden'
    ]
    for kw in recent_keywords:
        if kw in s:
            return True
    # Filter out anything clearly older
    old_keywords = [
        '2 day', '3 day', '4 day', '5 day', '6 day', '7 day',
        'week', 'month', 'vor 2', 'vor 3', 'vor 4', 'vor 5',
        'vor 6', 'vor 7', 'woche', 'monat', '30+ days'
    ]
    for kw in old_keywords:
        if kw in s:
            return False
    return True  # default include if unclear


# ─── Indeed ───────────────────────────────────────────────────────────────────
def scrape_indeed(titles: list, location: str = 'Deutschland') -> list:
    jobs = []
    for title in titles:
        url = 'https://de.indeed.com/jobs'
        params = {
            'q': title,
            'l': location,
            'radius': '100',
            'fromage': '1',   # posted in last 1 day
            'sort': 'date',   # newest first
        }
        r = _get(url, params)
        if not r:
            continue
        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.select('div.job_seen_beacon')
        for card in cards:
            try:
                t    = card.select_one('h2.jobTitle span[title]')
                co   = card.select_one('span.companyName')
                loc  = card.select_one('div.companyLocation')
                link = card.select_one('h2.jobTitle a')
                sal  = card.select_one('div.metadata.salary-snippet-container')
                date = card.select_one('span.date')
                if not (t and co and link):
                    continue
                date_text = date.get_text(strip=True) if date else ''
                if not is_recent(date_text):
                    continue
                job_url = 'https://de.indeed.com' + link.get('href', '')
                jobs.append({
                    'title':       t.get_text(strip=True),
                    'company':     co.get_text(strip=True),
                    'location':    loc.get_text(strip=True) if loc else 'Germany',
                    'source':      'Indeed',
                    'url':         job_url,
                    'description': '',
                    'salary':      sal.get_text(strip=True) if sal else '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"Indeed card parse error: {e}")
        time.sleep(random.uniform(1.5, 3))
    logger.info(f"Indeed: found {len(jobs)} jobs from last 24h")
    return jobs


# ─── StepStone ────────────────────────────────────────────────────────────────
def scrape_stepstone(titles: list, location: str = 'Deutschland') -> list:
    jobs = []
    for title in titles:
        url = f'https://www.stepstone.de/jobs/{title.replace(" ", "-")}.html'
        params = {
            'where': 'Deutschland',
            'radius': '30',
            'ag': 'age_1',    # last 24 hours filter
            'sort': 'date',
        }
        r = _get(url, params)
        if not r:
            continue
        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.select('article[data-at="job-item"]')
        for card in cards:
            try:
                t    = card.select_one('[data-at="job-item-title"]')
                co   = card.select_one('[data-at="job-item-company-name"]')
                loc  = card.select_one('[data-at="job-item-location"]')
                link = card.select_one('a[data-at="job-item-title"]')
                sal  = card.select_one('[data-at="job-item-salary"]')
                date = card.select_one('[data-at="job-item-posting-date"]')
                if not (t and link):
                    continue
                date_text = date.get_text(strip=True) if date else ''
                if not is_recent(date_text):
                    continue
                href = link.get('href', '')
                job_url = href if href.startswith('http') else 'https://www.stepstone.de' + href
                jobs.append({
                    'title':       t.get_text(strip=True),
                    'company':     co.get_text(strip=True) if co else '',
                    'location':    loc.get_text(strip=True) if loc else 'Germany',
                    'source':      'StepStone',
                    'url':         job_url,
                    'description': '',
                    'salary':      sal.get_text(strip=True) if sal else '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"StepStone card parse error: {e}")
        time.sleep(random.uniform(1.5, 3))
    logger.info(f"StepStone: found {len(jobs)} jobs from last 24h")
    return jobs


# ─── LinkedIn ─────────────────────────────────────────────────────────────────
def scrape_linkedin(titles: list, location: str = 'Germany') -> list:
    jobs = []
    for title in titles:
        url = 'https://www.linkedin.com/jobs/search/'
        params = {
            'keywords': title,
            'location': 'Germany',
            'f_TPR':    'r86400',  # last 24 hours (86400 seconds)
            'f_WT':     '2',       # include remote
            'sortBy':   'DD',      # sort by date
        }
        r = _get(url, params)
        if not r:
            continue
        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.select('div.base-card')
        for card in cards:
            try:
                t    = card.select_one('h3.base-search-card__title')
                co   = card.select_one('h4.base-search-card__subtitle')
                loc  = card.select_one('span.job-search-card__location')
                link = card.select_one('a.base-card__full-link')
                date = card.select_one('time')
                if not (t and link):
                    continue
                date_text = date.get('datetime', '') if date else ''
                # LinkedIn datetime is ISO format e.g. "2024-06-15"
                if date_text:
                    try:
                        posted = datetime.strptime(date_text[:10], '%Y-%m-%d')
                        if posted < datetime.now() - timedelta(days=1):
                            continue
                    except:
                        pass
                jobs.append({
                    'title':       t.get_text(strip=True),
                    'company':     co.get_text(strip=True) if co else '',
                    'location':    loc.get_text(strip=True) if loc else 'Germany',
                    'source':      'LinkedIn',
                    'url':         link.get('href', ''),
                    'description': '',
                    'salary':      '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"LinkedIn card parse error: {e}")
        time.sleep(random.uniform(2, 4))
    logger.info(f"LinkedIn: found {len(jobs)} jobs from last 24h")
    return jobs


# ─── Xing ─────────────────────────────────────────────────────────────────────
def scrape_xing(titles: list, location: str = 'Deutschland') -> list:
    jobs = []
    for title in titles:
        url = 'https://www.xing.com/jobs/search'
        params = {
            'keywords': title,
            'location': 'Deutschland',
            'radius':   '50',
            'published_at': 'last_day',  # last 24 hours
            'sort':     'date',
        }
        r = _get(url, params)
        if not r:
            continue
        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.select('[data-testid="job-listing-item"]')
        for card in cards:
            try:
                t    = card.select_one('[data-testid="job-listing-item-title"]')
                co   = card.select_one('[data-testid="job-listing-item-company-name"]')
                loc  = card.select_one('[data-testid="job-listing-item-location"]')
                link = card.select_one('a')
                date = card.select_one('time, [data-testid="job-listing-item-date"]')
                if not (t and link):
                    continue
                date_text = date.get_text(strip=True) if date else ''
                if not is_recent(date_text):
                    continue
                href = link.get('href', '')
                job_url = href if href.startswith('http') else 'https://www.xing.com' + href
                jobs.append({
                    'title':       t.get_text(strip=True),
                    'company':     co.get_text(strip=True) if co else '',
                    'location':    loc.get_text(strip=True) if loc else 'Germany',
                    'source':      'Xing',
                    'url':         job_url,
                    'description': '',
                    'salary':      '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"Xing card parse error: {e}")
        time.sleep(random.uniform(1.5, 3))
    logger.info(f"Xing: found {len(jobs)} jobs from last 24h")
    return jobs


# ─── Fetch full job description ───────────────────────────────────────────────
def fetch_description(url: str, source: str) -> str:
    r = _get(url)
    if not r:
        return ''
    soup = BeautifulSoup(r.text, 'html.parser')
    selectors = {
        'Indeed':    ['#jobDescriptionText', '.jobsearch-jobDescriptionText'],
        'StepStone': ['.at-section-text-description', '[data-at="job-description"]'],
        'LinkedIn':  ['.description__text', '.show-more-less-html__markup'],
        'Xing':      ['.job-description', '[data-testid="job-description"]'],
    }
    for sel in selectors.get(source, []):
        el = soup.select_one(sel)
        if el:
            return el.get_text(separator='\n', strip=True)[:3000]
    main = soup.select_one('main') or soup.select_one('article') or soup.body
    return main.get_text(separator='\n', strip=True)[:3000] if main else ''


# ─── Run all scrapers ─────────────────────────────────────────────────────────
def run_all_scrapers(titles: list, location: str = 'Germany') -> list:
    logger.info(f"🔍 Scraping last 24h jobs for: {titles}")
    all_jobs = []
    all_jobs += scrape_indeed(titles, 'Deutschland')
    all_jobs += scrape_stepstone(titles, 'Deutschland')
    all_jobs += scrape_linkedin(titles, 'Germany')
    all_jobs += scrape_xing(titles, 'Deutschland')

    # Deduplicate by URL
    seen, unique = set(), []
    for job in all_jobs:
        if job['url'] and job['url'] not in seen:
            seen.add(job['url'])
            unique.append(job)

    logger.info(f"✅ Total unique jobs from last 24h: {len(unique)}")
    return unique
