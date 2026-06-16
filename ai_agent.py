"""
AI layer — uses Groq (free) to:
1. Score each job against Stanley's CV and preferences
2. Generate a tailored cover letter
"""

from groq import Groq
import json
import logging
import os

logger = logging.getLogger(__name__)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Using LLaMA 3.3 70B — best free model on Groq for this task
MODEL = "llama-3.3-70b-versatile"

CV_SUMMARY = """
Name: Stanley Chukwuma Okoro
Role: Data Scientist | AI & Machine Learning
Location: Munich, Germany (open to all of Germany)

Education:
- M.Sc. Statistics and Data Science, LMU Munich (Completed April 2026)
- B.Sc. Statistics, Imo State University

Experience:
- Data Scientist (Working Student) at AYESSI, Munich (Oct 2023 – Present)
  • Built RAG-powered AI chatbot reducing first-response time from hours to seconds
  • Developed Python data pipelines automating ingestion, cleaning, transformation
  • Conducted EDA on user behaviour data informing product decisions
  • Designed Tableau dashboards for real-time KPI tracking

Skills:
- Programming: Python, SQL, R
- AI/ML: LLM Fine-Tuning, NLP, Deep Learning, Predictive Modelling,
         Recommendation Systems, A/B Testing, Forecasting, RAG
- Frameworks: PyTorch, Hugging Face Transformers, LangChain, n8n, Microsoft Copilot
- Visualisation: Tableau, KPI Reporting, EDA
- Languages: English (Native), German (B1)

Projects:
- Fine-tuned DeepSeek LLM on 10,000+ conflict reports (92% extraction accuracy)
- BERT-based risk classifier improving compliance efficiency by 35%
- Multilingual BERT for low-resource Igbo-language NLP

Certifications:
- RAG Agents: Build Apps & GPTs with APIs/MCP, LangChain & n8n
- Machine Learning A-Z: AI, Python & R (2025)

Preferences:
- Salary: €90,000 – €95,000
- Availability: Immediately
- Job titles: Data Scientist, Data Analyst, ML Engineer
- Location: All of Germany (including remote)
"""


def score_job(job: dict) -> dict:
    """Score a job 0-100 and return reasoning."""
    prompt = f"""
You are a job matching assistant. Score how well this job matches the candidate's profile.

CANDIDATE PROFILE:
{CV_SUMMARY}

JOB POSTING:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Salary: {job.get('salary', 'Not specified')}
Description:
{job.get('description', 'No description available')[:2000]}

Return ONLY a JSON object with this exact format, no extra text:
{{
  "score": <integer 0-100>,
  "reason": "<2-3 sentence explanation of the score>",
  "highlights": ["<key matching point 1>", "<key matching point 2>", "<key matching point 3>"],
  "concerns": ["<concern 1 if any>"]
}}

Scoring guide:
- 80-100: Excellent match (skills, level, and domain align well)
- 60-79:  Good match (most skills match, minor gaps)
- 40-59:  Partial match (some relevant skills, notable gaps)
- 0-39:   Poor match (role is too senior, wrong field, or missing core skills)
"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        text = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        return {"score": 0, "reason": "Could not score this job.", "highlights": [], "concerns": []}


def generate_cover_letter(job: dict, settings: dict) -> str:
    """Generate a tailored cover letter for a job."""
    prompt = f"""
You are a professional cover letter writer. Write a concise, tailored cover letter for this job application.

CANDIDATE PROFILE:
{CV_SUMMARY}

JOB POSTING:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description:
{job.get('description', '')[:2000]}

APPLICATION DETAILS:
- Salary expectation: €{settings.get('salary_expectation', '90000-95000')}
- Availability: {settings.get('availability', 'Immediately')}
- Applicant phone: {settings.get('applicant_phone', '+49 017637224355')}

Write a professional cover letter in English. Requirements:
- 3 short paragraphs maximum
- Opening: express genuine interest, mention the specific role and company
- Middle: highlight 2-3 most relevant skills/experiences that match this specific job
- Closing: state salary expectation, availability, and call to action
- Tone: confident but not arrogant, specific not generic
- Do NOT use filler phrases like "I am writing to apply..."
- Sign off as: Stanley Chukwuma Okoro

Return only the cover letter text, nothing else.
"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Cover letter error: {e}")
        return "Could not generate cover letter."


def process_job(job: dict, settings: dict) -> dict:
    """Score a job and generate a cover letter. Returns enriched job dict."""
    logger.info(f"Processing: {job['title']} at {job['company']}")
    scored    = score_job(job)
    min_score = int(settings.get('min_score', 60))

    job['match_score']  = scored.get('score', 0)
    job['match_reason'] = json.dumps({
        'reason':     scored.get('reason', ''),
        'highlights': scored.get('highlights', []),
        'concerns':   scored.get('concerns', []),
    })

    # Only generate cover letter for jobs above the minimum score threshold
    if job['match_score'] >= min_score:
        job['cover_letter'] = generate_cover_letter(job, settings)
    else:
        job['cover_letter'] = ''

    return job
