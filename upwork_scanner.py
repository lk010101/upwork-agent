import os
import json
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

KEYWORDS = [k.strip().lower() for k in os.environ.get("KEYWORDS", "python,fastapi,django").split(",")]
MIN_BUDGET = int(os.environ.get("MIN_BUDGET", "500"))
MY_PROFILE = os.environ.get("MY_PROFILE", "Senior Python developer with 5 years experience in FastAPI, Django, REST APIs.")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

SEEN_JOBS_FILE = "seen_jobs.json"


def load_seen_jobs() -> set:
    try:
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen_jobs(seen: set):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen), f)


async def fetch_jobs(search_query: str) -> list[dict]:
    url = f"https://www.upwork.com/nx/search/jobs?q={search_query}&sort=recency&amount=500-"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
            response = await http.get(url, headers=headers)
        if response.status_code != 200:
            logger.warning(f"Upwork вернул статус {response.status_code}")
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script_tag:
            logger.warning("Не нашли __NEXT_DATA__ на странице Upwork")
            return []
        data = json.loads(script_tag.string)
        results = (
            data.get("props", {})
                .get("pageProps", {})
                .get("initialData", {})
                .get("searchResults", {})
                .get("results", [])
        )
        for item in results:
            job = {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "description": item.get("snippet", ""),
                "url": f"https://www.upwork.com/jobs/{item.get('ciphertext', '')}",
                "budget": _extract_budget(item),
                "client_rating": str(item.get("client", {}).get("feedbackScore", "—")),
                "posted": item.get("createdOn", ""),
            }
            if job["id"]:
                jobs.append(job)
    except Exception as e:
        logger.error(f"Ошибка при парсинге Upwork: {e}")
    return jobs


def _extract_budget(item: dict) -> str:
    amount = item.get("amount", {})
    if amount.get("amount"):
        return f"${amount['amount']} (фиксированная)"
    min_r = item.get("hourlyBudgetMin")
    max_r = item.get("hourlyBudgetMax")
    if min_r or max_r:
        return f"${min_r or '?'}–${max_r or '?'}/час"
    return "не указан"


def score_job(job: dict) -> int:
    score = 0
    text = f"{job['title']} {job['description']}".lower()
    matched = sum(1 for kw in KEYWORDS if kw in text)
    score += min(matched * 15, 60)
    budget_str = job.get("budget", "")
    if "$" in budget_str:
        try:
            nums = [int(s.replace(",", "")) for s in budget_str.split()
                    if s.replace(",", "").replace("$", "").isdigit()]
            if nums and max(nums) >= MIN_BUDGET:
                score += 25
        except Exception:
            pass
    try:
        rating = float(job.get("client_rating", 0))
        if rating >= 4.5:
            score += 15
        elif rating >= 4.0:
            score += 8
    except Exception:
        pass
    return min(score, 100)


async def ai_evaluate_job(job: dict) -> tuple[int, str]:
    """Оценка вакансии через Gemini Flash (бесплатно)."""
    if not GEMINI_API_KEY:
        return 70, "Hi! I've reviewed your job posting and I'm confident I can deliver exactly what you need. My experience aligns well with your requirements. I'd love to discuss the details further."

    prompt = f"""You are a career consultant for Upwork freelancers.

MY PROFILE:
{MY_PROFILE}

JOB:
Title: {job['title']}
Description: {job['description']}
Budget: {job['budget']}
Client rating: {job['client_rating']}

Task:
1. Score the job relevance for my profile from 0 to 100.
2. Write a short (3-4 sentences) personalized proposal draft in English.

Reply ONLY with valid JSON, no markdown, no explanation:
{{"score": <0-100>, "draft": "<proposal text>"}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.post(url, json=payload)
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return int(result["score"]), result["draft"]
    except Exception as e:
        logger.error(f"Ошибка Gemini API: {e}")
        return 0, ""


async def scan_once(send_notification_fn):
    seen = load_seen_jobs()
    search_query = os.environ.get("UPWORK_QUERY", "python+developer")
    logger.info(f"🔍 Сканирую Upwork... запрос: {search_query}")
    jobs = await fetch_jobs(search_query)
    logger.info(f"Найдено вакансий: {len(jobs)}")

    new_count = 0
    for job in jobs:
        if job["id"] in seen:
            continue
        seen.add(job["id"])
        quick_score = score_job(job)
        if quick_score < 40:
            logger.info(f"⏭ Пропускаю (скор {quick_score}): {job['title'][:50]}")
            continue
        score, draft = await ai_evaluate_job(job)
        job["score"] = score
        if score >= 55:
            logger.info(f"✅ Релевантная вакансия (скор {score}): {job['title'][:50]}")
            await send_notification_fn(job, draft)
            new_count += 1
            await asyncio.sleep(2)
        else:
            logger.info(f"🟡 Не релевантно (скор {score}): {job['title'][:50]}")

    save_seen_jobs(seen)
    logger.info(f"✓ Готово. Отправлено уведомлений: {new_count}")


async def run_scanner(send_notification_fn, interval_minutes: int = 5):
    logger.info(f"Сканер запущен. Интервал: {interval_minutes} мин.")
    while True:
        try:
            await scan_once(send_notification_fn)
        except Exception as e:
            logger.error(f"Ошибка в цикле сканера: {e}")
        await asyncio.sleep(interval_minutes * 60)
