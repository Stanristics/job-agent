"""
Local Form Filler — runs on your Mac only
-------------------------------------------
This connects to your Render-hosted Job Agent, pulls jobs you've approved
that require form applications, and opens a REAL visible browser window
on your Mac so you can watch it fill the form and review before submitting.

This does NOT run on Render — it only runs locally because it needs
a screen for you to see and approve.

USAGE:
    python local_form_filler.py

Then follow the on-screen menu.
"""

import asyncio
import requests
import os
import sys
from playwright.async_api import async_playwright

# ================================================================
#  CONFIGURATION
# ================================================================
RENDER_API_URL = "https://YOUR-APP-NAME.onrender.com"  # ← paste your Render URL here
CV_PATH = "/path/to/your/Stanley_Okoro_CV.pdf"           # ← paste your local CV file path here
# ================================================================


def detect_ats_platform(url: str) -> str:
    url_lower = url.lower()
    if 'linkedin.com' in url_lower:
        return 'linkedin'
    elif 'greenhouse.io' in url_lower:
        return 'greenhouse'
    elif 'myworkdayjobs.com' in url_lower or 'workday.com' in url_lower:
        return 'workday'
    elif 'lever.co' in url_lower:
        return 'lever'
    elif 'indeed.com' in url_lower:
        return 'indeed'
    else:
        return 'unknown'


def get_approved_jobs():
    """Fetch jobs marked 'approved' from your Render backend."""
    try:
        r = requests.get(f"{RENDER_API_URL}/jobs", params={"status": "approved"}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ Could not reach your Render API: {e}")
        print(f"   Check that RENDER_API_URL is correct: {RENDER_API_URL}")
        return []


def get_settings():
    try:
        r = requests.get(f"{RENDER_API_URL}/settings", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ Could not fetch settings: {e}")
        return {}


def mark_as_submitted(job_id):
    try:
        requests.post(f"{RENDER_API_URL}/jobs/{job_id}/submit", timeout=10)
        print("✅ Marked as submitted in your dashboard.")
    except Exception as e:
        print(f"⚠️  Could not update status remotely: {e}")


# ── Platform-specific fillers ───────────────────────────────────────────────────
async def fill_linkedin_easy_apply(page, applicant, cv_path):
    print("   → Detected LinkedIn. Looking for 'Easy Apply' button...")
    try:
        btn = page.locator('button:has-text("Easy Apply")').first
        await btn.click(timeout=8000)
        await page.wait_for_timeout(1500)

        for step in range(8):
            file_input = page.locator('input[type="file"]').first
            if await file_input.count() > 0 and cv_path and os.path.exists(cv_path):
                await file_input.set_input_files(cv_path)
                print("   → CV uploaded")
                await page.wait_for_timeout(800)

            phone_input = page.locator('input[id*="phoneNumber"]').first
            if await phone_input.count() > 0:
                await phone_input.fill(applicant.get('phone', ''))
                print("   → Phone filled")

            text_inputs = page.locator('input[type="text"]')
            count = await text_inputs.count()
            for i in range(count):
                inp = text_inputs.nth(i)
                label = (await inp.get_attribute('aria-label') or '').lower()
                if 'email' in label:
                    await inp.fill(applicant.get('email', ''))
                elif 'salary' in label or 'compensation' in label:
                    await inp.fill(applicant.get('salary_expectation', ''))
                elif 'notice' in label or 'available' in label:
                    await inp.fill(applicant.get('availability', 'Immediately'))

            submit_btn = page.locator('button:has-text("Submit application")').first
            review_btn = page.locator('button:has-text("Review")').first
            next_btn   = page.locator('button:has-text("Next")').first

            if await submit_btn.count() > 0:
                print("\n   🛑 Reached the final 'Submit application' step.")
                print("   The form is filled — please review it in the browser window")
                print("   and click Submit yourself when you're happy with it.\n")
                break
            elif await review_btn.count() > 0:
                await review_btn.click()
                await page.wait_for_timeout(1200)
            elif await next_btn.count() > 0:
                await next_btn.click()
                await page.wait_for_timeout(1200)
            else:
                break

        return True
    except Exception as e:
        print(f"   ❌ Error filling LinkedIn form: {e}")
        return False


async def fill_greenhouse_form(page, applicant, cv_path):
    print("   → Detected Greenhouse application form...")
    try:
        field_map = {
            'first_name': applicant.get('first_name', ''),
            'last_name':  applicant.get('last_name', ''),
            'email':      applicant.get('email', ''),
            'phone':      applicant.get('phone', ''),
        }
        for field_id, value in field_map.items():
            field = page.locator(f'input[id*="{field_id}"], input[name*="{field_id}"]').first
            if await field.count() > 0 and value:
                await field.fill(value)
                print(f"   → {field_id} filled")

        file_input = page.locator('input[type="file"]').first
        if await file_input.count() > 0 and cv_path and os.path.exists(cv_path):
            await file_input.set_input_files(cv_path)
            print("   → CV uploaded")

        cl_field = page.locator('textarea[id*="cover_letter"], textarea[name*="cover_letter"]').first
        if await cl_field.count() > 0:
            await cl_field.fill(applicant.get('cover_letter', ''))
            print("   → Cover letter filled")

        print("\n   🛑 Form filled — please review in the browser window and click Submit yourself.\n")
        return True
    except Exception as e:
        print(f"   ❌ Error filling Greenhouse form: {e}")
        return False


async def fill_workday_form(page, applicant, cv_path):
    print("   → Detected Workday application form...")
    try:
        file_input = page.locator('input[type="file"]').first
        if await file_input.count() > 0 and cv_path and os.path.exists(cv_path):
            await file_input.set_input_files(cv_path)
            print("   → CV uploaded (Workday may auto-fill other fields from this)")
            await page.wait_for_timeout(2000)

        email_field = page.locator('input[data-automation-id*="email"]').first
        if await email_field.count() > 0:
            await email_field.fill(applicant.get('email', ''))
            print("   → Email filled")

        phone_field = page.locator('input[data-automation-id*="phone"]').first
        if await phone_field.count() > 0:
            await phone_field.fill(applicant.get('phone', ''))
            print("   → Phone filled")

        print("\n   🛑 Basic fields filled. Workday forms vary a lot —")
        print("   please review carefully in the browser before submitting.\n")
        return True
    except Exception as e:
        print(f"   ❌ Error filling Workday form: {e}")
        return False


async def fill_lever_form(page, applicant, cv_path):
    print("   → Detected Lever application form...")
    try:
        full_name = f"{applicant.get('first_name','')} {applicant.get('last_name','')}".strip()
        field_map = {'name': full_name, 'email': applicant.get('email', ''), 'phone': applicant.get('phone', '')}
        for field_name, value in field_map.items():
            field = page.locator(f'input[name="{field_name}"]').first
            if await field.count() > 0 and value:
                await field.fill(value)
                print(f"   → {field_name} filled")

        file_input = page.locator('input[name="resume"]').first
        if await file_input.count() > 0 and cv_path and os.path.exists(cv_path):
            await file_input.set_input_files(cv_path)
            print("   → CV uploaded")

        print("\n   🛑 Form filled — please review in the browser window and click Submit yourself.\n")
        return True
    except Exception as e:
        print(f"   ❌ Error filling Lever form: {e}")
        return False


async def process_job(job, applicant, cv_path):
    """Open a visible browser, navigate to the job, and fill what it can."""
    platform = detect_ats_platform(job['url'])

    print(f"\n{'='*60}")
    print(f"📋 {job['title']} at {job['company']}")
    print(f"   {job['url']}")
    print(f"{'='*60}")

    if platform in ('unknown', 'indeed'):
        print(f"   ⚠️  This job uses a form type we can't safely auto-fill ({platform}).")
        print(f"   Please apply manually. Your cover letter is in the dashboard.\n")
        input("   Press Enter to continue to the next job...")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible browser window
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print(f"   Opening browser and navigating to job page...")
            await page.goto(job['url'], timeout=20000)
            await page.wait_for_timeout(2000)

            if platform == 'linkedin':
                await fill_linkedin_easy_apply(page, applicant, cv_path)
            elif platform == 'greenhouse':
                await fill_greenhouse_form(page, applicant, cv_path)
            elif platform == 'workday':
                await fill_workday_form(page, applicant, cv_path)
            elif platform == 'lever':
                await fill_lever_form(page, applicant, cv_path)

            print("   👀 Browser window is open. Review the filled form.")
            input("   Press Enter here AFTER you've reviewed/submitted it in the browser...")

            mark_now = input("   Mark this job as 'submitted' in your dashboard? (y/n): ").strip().lower()
            if mark_now == 'y':
                mark_as_submitted(job['id'])

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            await browser.close()


async def main():
    print("\n" + "="*60)
    print("  🤖 Job Agent — Local Form Filler")
    print("="*60)
    print(f"  Connecting to: {RENDER_API_URL}\n")

    if not os.path.exists(CV_PATH):
        print(f"⚠️  Warning: CV file not found at {CV_PATH}")
        print(f"   Update CV_PATH at the top of this script.\n")

    jobs = get_approved_jobs()
    if not jobs:
        print("No approved jobs found. Approve some jobs in your dashboard first.")
        return

    settings = get_settings()
    applicant = {
        'first_name': settings.get('applicant_name', '').split(' ')[0],
        'last_name':  ' '.join(settings.get('applicant_name', '').split(' ')[1:]),
        'email':      settings.get('applicant_email', ''),
        'phone':      settings.get('applicant_phone', ''),
        'salary_expectation': settings.get('salary_expectation', ''),
        'availability': settings.get('availability', 'Immediately'),
    }

    print(f"Found {len(jobs)} approved job(s) waiting for form submission.\n")

    for job in jobs:
        applicant['cover_letter'] = job.get('cover_letter', '')
        proceed = input(f"Process '{job['title']}' at {job['company']}? (y/n/skip all): ").strip().lower()
        if proceed == 'skip all':
            break
        if proceed != 'y':
            continue
        await process_job(job, applicant, CV_PATH)

    print("\n✅ Done processing approved jobs.")


if __name__ == "__main__":
    asyncio.run(main())
