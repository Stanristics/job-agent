"""
Job scrapers for Indeed, StepStone, LinkedIn, and Xing.
- Searches across user-selected countries: Germany, Austria, Switzerland, Norway, Australia
- Filters to jobs posted in the last 24 hours only
- Skips jobs already in the database (handled by main.py via URL dedup)

NOTE ON COUNTRY COVERAGE PER PLATFORM:
- Indeed:    has localized domains for all 5 countries (de/at/ch/no/au)
- LinkedIn:  global, works for all 5 countries via location parameter
- StepStone: DACH-region only (Germany, Austria, Switzerland) — no Norway/Australia presence
- Xing:      DACH-region only (Germany, Austria, Switzerland) — no Norway/Australia presence
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

# ── Country configuration ───────────────────────────────────────────────────────
# Maps a country code to its Indeed domain, LinkedIn location string,
# and whether StepStone/Xing support it (DACH region only)
COUNTRY_CONFIG = {
    'germany':     {'indeed_domain': 'de.indeed.com',  'indeed_loc': 'Deutschland', 'linkedin_loc': 'Germany',     'dach': True,  'label': 'Germany'},
    'austria':     {'indeed_domain': 'at.indeed.com',  'indeed_loc': 'Österreich',  'linkedin_loc': 'Austria',     'dach': True,  'label': 'Austria'},
    'switzerland': {'indeed_domain': 'ch.indeed.com',  'indeed_loc': 'Schweiz',     'linkedin_loc': 'Switzerland', 'dach': True,  'label': 'Switzerland'},
    'norway':      {'indeed_domain': 'no.indeed.com',  'indeed_loc': 'Norge',       'linkedin_loc': 'Norway',      'dach': False, 'label': 'Norway'},
    'australia':   {'indeed_domain': 'au.indeed.com',  'indeed_loc': 'Australia',   'linkedin_loc': 'Australia',   'dach': False, 'label': 'Australia'},
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
                wait = random.uniform(2, 5) * (attempt + 1)
                logger.info(f"Retry {attempt + 1}/{max_retries} for {url} after {wait:.1f}s — {e}")
                time.sleep(wait)
            continue
    logger.warning(f"Request failed after {max_retries + 1} attempts: {url} — {last_error}")
    return None


def is_recent(date_str: str) -> bool:
    """Returns True if the date string suggests the job was posted within the last 24 hours."""
    if not date_str:
        return True
    s = date_str.lower().strip()
    recent_keywords = [
        'today', 'just posted', 'just now', 'heute', 'gerade',
        'soeben', 'vor wenigen', '1 day ago', 'an hour', 'hours ago',
        'hour ago', 'minute', 'stunde', 'stunden'
    ]
    for kw in recent_keywords:
        if kw in s:
            return True
    old_keywords = [
        '2 day', '3 day', '4 day', '5 day', '6 day', '7 day',
        'week', 'month', 'vor 2', 'vor 3', 'vor 4', 'vor 5',
        'vor 6', 'vor 7', 'woche', 'monat', '30+ days'
    ]
    for kw in old_keywords:
        if kw in s:
            return False
    return True


# ─── Indeed (works across all 5 countries via localized domains) ──────────────
def scrape_indeed(titles: list, country: str = 'germany') -> list:
    cfg = COUNTRY_CONFIG.get(country)
    if not cfg:
        return []

    jobs = []
    for title in titles:
        url = f"https://{cfg['indeed_domain']}/jobs"
        params = {
            'q': title,
            'l': cfg['indeed_loc'],
            'radius': '100',
            'fromage': '1',
            'sort': 'date',
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
                job_url = f"https://{cfg['indeed_domain']}" + link.get('href', '')
                jobs.append({
                    'title':       t.get_text(strip=True),
                    'company':     co.get_text(strip=True),
                    'location':    loc.get_text(strip=True) if loc else cfg['label'],
                    'source':      'Indeed',
                    'country':     cfg['label'],
                    'url':         job_url,
                    'description': '',
                    'salary':      sal.get_text(strip=True) if sal else '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"Indeed card parse error: {e}")
        time.sleep(random.uniform(1.5, 3))
    logger.info(f"Indeed ({cfg['label']}): found {len(jobs)} jobs from last 24h")
    return jobs


# ─── StepStone (DACH region only: Germany, Austria, Switzerland) ──────────────
def scrape_stepstone(titles: list, country: str = 'germany') -> list:
    cfg = COUNTRY_CONFIG.get(country)
    if not cfg or not cfg['dach']:
        return []  # StepStone doesn't operate in Norway/Australia

    # StepStone uses one .de domain but a 'where' country filter
    where_map = {'germany': 'Deutschland', 'austria': 'Österreich', 'switzerland': 'Schweiz'}
    where = where_map.get(country, 'Deutschland')

    jobs = []
    for title in titles:
        url = f'https://www.stepstone.de/jobs/{title.replace(" ", "-")}.html'
        params = {'where': where, 'radius': '30', 'ag': 'age_1', 'sort': 'date'}
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
                    'location':    loc.get_text(strip=True) if loc else cfg['label'],
                    'source':      'StepStone',
                    'country':     cfg['label'],
                    'url':         job_url,
                    'description': '',
                    'salary':      sal.get_text(strip=True) if sal else '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"StepStone card parse error: {e}")
        time.sleep(random.uniform(1.5, 3))
    logger.info(f"StepStone ({cfg['label']}): found {len(jobs)} jobs from last 24h")
    return jobs


# ─── LinkedIn (works across all 5 countries) ──────────────────────────────────
def scrape_linkedin(titles: list, country: str = 'germany') -> list:
    cfg = COUNTRY_CONFIG.get(country)
    if not cfg:
        return []

    jobs = []
    for title in titles:
        url = 'https://www.linkedin.com/jobs/search/'
        params = {
            'keywords': title,
            'location': cfg['linkedin_loc'],
            'f_TPR':    'r86400',
            'f_WT':     '2',
            'sortBy':   'DD',
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
                    'location':    loc.get_text(strip=True) if loc else cfg['label'],
                    'source':      'LinkedIn',
                    'country':     cfg['label'],
                    'url':         link.get('href', ''),
                    'description': '',
                    'salary':      '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"LinkedIn card parse error: {e}")
        time.sleep(random.uniform(2, 4))
    logger.info(f"LinkedIn ({cfg['label']}): found {len(jobs)} jobs from last 24h")
    return jobs


# ─── Xing (DACH region only: Germany, Austria, Switzerland) ──────────────────
def scrape_xing(titles: list, country: str = 'germany') -> list:
    cfg = COUNTRY_CONFIG.get(country)
    if not cfg or not cfg['dach']:
        return []  # Xing doesn't operate in Norway/Australia

    where_map = {'germany': 'Deutschland', 'austria': 'Österreich', 'switzerland': 'Schweiz'}
    where = where_map.get(country, 'Deutschland')

    jobs = []
    for title in titles:
        url = 'https://www.xing.com/jobs/search'
        params = {'keywords': title, 'location': where, 'radius': '50', 'published_at': 'last_day', 'sort': 'date'}
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
                    'location':    loc.get_text(strip=True) if loc else cfg['label'],
                    'source':      'Xing',
                    'country':     cfg['label'],
                    'url':         job_url,
                    'description': '',
                    'salary':      '',
                    'posted_date': date_text,
                })
            except Exception as e:
                logger.debug(f"Xing card parse error: {e}")
        time.sleep(random.uniform(1.5, 3))
    logger.info(f"Xing ({cfg['label']}): found {len(jobs)} jobs from last 24h")
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


# ─── Run all scrapers across selected countries ───────────────────────────────
def run_all_scrapers(titles: list, countries: list = None) -> list:
    """
    countries: list of country keys, e.g. ['germany', 'austria', 'switzerland', 'norway', 'australia']
    Defaults to ['germany'] if not specified.
    """
    if not countries:
        countries = ['germany']

    logger.info(f"🔍 Scraping last 24h jobs for: {titles} across countries: {countries}")
    all_jobs = []

    for country in countries:
        if country not in COUNTRY_CONFIG:
            logger.warning(f"Unknown country key: {country} — skipping")
            continue

        all_jobs += scrape_indeed(titles, country)
        all_jobs += scrape_stepstone(titles, country)   # auto-skips if not DACH
        all_jobs += scrape_linkedin(titles, country)
        all_jobs += scrape_xing(titles, country)          # auto-skips if not DACH

    # Deduplicate by URL
    seen, unique = set(), []
    for job in all_jobs:
        if job['url'] and job['url'] not in seen:
            seen.add(job['url'])
            unique.append(job)

    logger.info(f"✅ Total unique jobs across all selected countries: {len(unique)}")
    return unique
