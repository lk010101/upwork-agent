import os
import json
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

KEYWORDS = [k.strip().lower() for k in os.environ.get("KEYWORDS", "webflow,figma,cms").split(",")]
MIN_BUDGET = int(os.environ.get("MIN_BUDGET", "300"))
MY_PROFILE = os.environ.get("MY_PROFILE", "Webflow developer specializing in Figma to Webflow conversions and Webflow CMS.")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SEEN_JOBS_FILE = "seen_jobs.json"

# Upwork GraphQL endpoint
GRAPHQL_URL = "https://www.upwork.com/api/graphql/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Upwork-Accept-Language": "en-US",
    "Referer": "https://www.upwork.com/",
    "Origin": "https://www.upwork.com",
}


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
    """Получает вакансии через Upwork GraphQL API."""
    query = """
    query JobSearch($query: String!, $paging: PagingInput) {
      jobSearch(
        marketplaceJobFilter: {
          searchExpression: { q: $query }
          contractTypeFilter: { contractTypes: [FIXED, HOURLY] }
        }
        paging: $paging
        sorting: { field: RECENCY, order: DESCENDING }
      ) {
        results {
          id
          title
          description
          publishedOn
          amount { amount currencyCode }
          hourlyBudgetMin
          hourlyBudgetMax
          ciphertext
          client {
            feedbackScore
            totalHires
            totalReviews
          }
        }
      }
    }
    """
    variables = {
        "query": search_query,
        "paging": {"offset": 0, "count": 30}
    }

    jobs = []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            response = await http.post(
                GRAPHQL_URL,
                headers=HEADERS,
                json={"query": query, "variables": variables}
            )

        if response.status_code != 200:
            logger.warning(f"GraphQL вернул статус {response.status_code}, пробую резервный метод...")
            return await fetch_jobs_rss(search_query)

        data = response.json()
        results = data.get("data", {}).get("jobSearch", {}).get("results", [])

        for item in results:
            job = {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "description": (item.get("description") or "")[:500],
                "url": f"https://www.upwork.com/jobs/{item.get('ciphertext', '')}",
                "budget": _extract_budget(item),
                "client_rating": str(item.get("client", {}).get("feedbackScore", "—")),
                "posted": item.get("publishedOn", ""),
            }
            if job["id"]:
                jobs.append(job)

        logger.info(f"GraphQL: получено {len(jobs)} вакансий")

    except Exception as e:
        logger.error(f"Ошибка GraphQL: {e}, пробую резервный метод...")
        return await fetch_jobs_rss(search_query)

    return jobs


async def fetch_jobs_rss(search_query: str) -> list[dict]:
    """Резервный метод — поиск через RSS-подобный endpoint."""
    import xml.etree.ElementTree as ET

    url = f"https://www.upwork.com/ab/feed/jobs/rss?q={search_query}&sort=recency&paging=0%3B10&api_params=1&securityToken=&userUid=&orgUid="
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as http:
            response = await http.get(url)

        if response.status_code == 200:
            root = ET.fromstring(response.text)
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                description = item.findtext("description", "").strip()[:500]
                pub_date = item.findtext("pubDate", "")
                job_id = link.split("~")[-1] if "~" in link else link[-20:]
                jobs.append({
                    "id": job_id,
                    "title": title,
                    "description": description,
                    "url": link,
                    "budget": "не указан",
                    "client_rating": "—",
                    "posted": pub_date,
                })
            logger.info(f"RSS: получено {len(jobs)} вакансий")
        else:
            logger.warning(f"RSS вернул статус {response.status_code}")
    except Exception as e:
        logger.error(f"Ошибка RSS: {e}")

    return jobs


def _extract_budget(item: dict) -> str:
    amount = item.get("amount", {})
    if amount and amount.get("amount"):
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
    score += min(matched * 20, 60)
    try:
        rating = float(job.get("client_rating", 0))
        if rating >= 4.5:
            score += 15
        elif rating >= 4.0:
            score += 8
    except Exception:
        pass
    # Если бюджет не указан — не штрафуем
    if "не указан" not in job.get("budget", ""):
        score += 10
    return min(score, 100)


async def ai_evaluate_job(job: dict) -> tuple[int, str]:
    if not GEMINI_API_KEY:
        # Без API — возвращаем базовый черновик
        score = score_job(job)
        draft = (
            f"Hi! I'm a Webflow developer specializing in Figma to Webflow conversions and CMS setups. "
            f"I've reviewed your project and I'm confident I can deliver pixel-perfect results. "
            f"I'd love to discuss the details — feel free to reach out!"
        )
        return score, draft

    prompt = f"""You are a career consultant for Upwork freelancers.

MY PROFILE:
{MY_PROFILE}

JOB POSTING:
Title: {job['title']}
Description: {job['description']}
Budget: {job['budget']}
Client rating: {job['client_rating']}

Instructions:
1. Score the relevance of this job for my profile from 0 to 100.
2. Write a short (3-4 sentences) personalized proposal in English.

Reply ONLY with valid JSON, no markdown:
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
        score = score_job(job)
        return score, "Hi! I specialize in Figma to Webflow development and CMS setups. I'd love to help with your project — let's connect!"


async def scan_once(send_notification_fn):
    seen = load_seen_jobs()
    search_query = os.environ.get("UPWORK_QUERY", "webflow+developer")
    logger.info(f"🔍 Сканирую Upwork... запрос: {search_query}")

    jobs = await fetch_jobs(search_query)
    logger.info(f"Найдено вакансий: {len(jobs)}")

    new_count = 0
    for job in jobs:
        if job["id"] in seen:
            continue
        seen.add(job["id"])

        quick_score = score_job(job)
        if quick_score < 20:
            logger.info(f"⏭ Пропускаю (скор {quick_score}): {job['title'][:50]}")
            continue

        score, draft = await ai_evaluate_job(job)
        job["score"] = score

        if score >= 40:
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
