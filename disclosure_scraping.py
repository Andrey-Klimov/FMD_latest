import os
import asyncio
import logging
import json
import csv
import httpx
import uuid
from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page, expect

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("disclosure_log.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
GIGACHAT_CLIENT_SECRET = "MDE5ZTE3ODctMTE2Yy03MzUzLWJiMzYtZWY2MmJkMGUxMGFiOjJhMWU4M2U3LTM5OGItNDVmMi04MjM2LTViN2U5OWYzNGI5Yw=="
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"

COMPANIES = [
    "ЛУКОЙЛ",
    "ГАЗПРОМ",
    "ЯНДЕКС",
    "Т-Техно",
    "Татнефть"
]

DOWNLOAD_DIR = r"C:\MSFO analyst\downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

CSV_PATH = r"C:\MSFO analyst\baza.csv"

# Глобальные переменные браузера
browser: Browser = None
page: Page = None
playwright_instance = None


# ============================================================
# ЗАГРУЗКА БАЗЫ
# ============================================================
def load_company_links(csv_path: str, company_list: list) -> dict:
    """
    Загружает CSV и возвращает словарь:
    { 'название_компании': {'msfo_url': '...', 'emit_url': '...'} }
    """
    result = {}
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            sample = f.readline()
            f.seek(0)
            delimiter = ';' if ';' in sample else ','
            reader = csv.DictReader(f, delimiter=delimiter)
            fieldnames = [col.strip() for col in reader.fieldnames]
            name_col = None
            msfo_col = None
            emit_col = None
            for col in fieldnames:
                col_lower = col.lower()
                if 'наименование' in col_lower or 'компани' in col_lower:
                    name_col = col
                if 'мсфо' in col_lower or 'ifrs' in col_lower:
                    msfo_col = col
                if 'эмитент' in col_lower or 'emit' in col_lower:
                    emit_col = col
            if not all([name_col, msfo_col, emit_col]):
                # fallback
                logger.warning("Не удалось определить столбцы по имени, используем порядок индексов (0,2,3)")
                with open(csv_path, 'r', encoding='utf-8-sig') as f2:
                    lines = f2.readlines()
                    header = lines[0].strip().split(delimiter)
                    for i, col in enumerate(header):
                        col_lower = col.lower()
                        if 'наименование' in col_lower or 'компани' in col_lower:
                            name_col = i
                        if 'мсфо' in col_lower or 'ifrs' in col_lower:
                            msfo_col = i
                        if 'эмитент' in col_lower or 'emit' in col_lower:
                            emit_col = i
                    if name_col is None:
                        name_col = 0
                    if msfo_col is None:
                        msfo_col = 2
                    if emit_col is None:
                        emit_col = 3
                    for line in lines[1:]:
                        parts = [p.strip() for p in line.strip().split(delimiter)]
                        if len(parts) <= max(name_col, msfo_col, emit_col):
                            continue
                        name = parts[name_col]
                        msfo = parts[msfo_col]
                        emit = parts[emit_col]
                        if name and msfo and emit:
                            result[name] = {'msfo_url': msfo, 'emit_url': emit}
            else:
                for row in reader:
                    name = row.get(name_col, '').strip()
                    msfo = row.get(msfo_col, '').strip()
                    emit = row.get(emit_col, '').strip()
                    if name and msfo and emit:
                        result[name] = {'msfo_url': msfo, 'emit_url': emit}
        filtered = {k: v for k, v in result.items() if k in company_list}
        logger.info(f"Загружены ссылки для {len(filtered)} компаний из CSV")
        return filtered
    except Exception as e:
        logger.error(f"Ошибка загрузки CSV: {e}")
        return {}


# ============================================================
# КЛИЕНТ GIGACHAT
# ============================================================
class GigaChatClient:
    def __init__(self, credentials: str, scope: str):
        self.credentials = credentials
        self.scope = scope
        self.access_token = None

    async def get_access_token(self) -> bool:
        try:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.post(
                    "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                    headers={
                        "Authorization": f"Basic {self.credentials}",
                        "RqUID": str(uuid.uuid4()),
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    data={"scope": self.scope}
                )
            if response.status_code == 200:
                self.access_token = response.json().get("access_token")
                logger.info("✓ OAuth токен получен")
                return True
            else:
                logger.error(f"Ошибка получения токена: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Исключение при получении токена: {e}")
            return False

    async def chat(self, messages: list, temperature: float = 0.0, max_tokens: int = 1200) -> str | None:
        if not self.access_token:
            ok = await self.get_access_token()
            if not ok:
                return None
        payload = {
            "model": "GigaChat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "profanity_check": False
        }
        try:
            async with httpx.AsyncClient(verify=False, timeout=120.0) as client:
                response = await client.post(
                    "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            elif response.status_code == 401:
                logger.warning("Токен истёк, обновляем...")
                ok = await self.get_access_token()
                if ok:
                    return await self.chat(messages, temperature, max_tokens)
                return None
            else:
                logger.error(f"Ошибка GigaChat: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Исключение при запросе к GigaChat: {e}")
            return None


# ============================================================
# PLAYWRIGHT ИНСТРУМЕНТЫ (улучшенные)
# ============================================================
class PlaywrightTools:

    SCHEMA = {
        "navigate": {
            "description": "Переход по URL. Аргументы: {\"url\": \"https://...\"}",
            "required_keys": ["url"]
        },
        "get_page_info": {
            "description": "Получить список ссылок на PDF-файлы с указанием года. Аргументы: {}",
            "required_keys": []
        },
        "download_by_href": {
            "description": "Скачать файл по URL (ссылка на файл или на страницу файла). Аргументы: {\"href\": \"...\", \"company\": \"название\", \"doc_type\": \"МСФО или Эмитент\"}",
            "required_keys": ["href", "company", "doc_type"]
        },
        "wait": {
            "description": "Подождать N секунд. Аргументы: {\"seconds\": 2}",
            "required_keys": ["seconds"]
        },
        "handle_captcha": {
            "description": "Проверить наличие капчи и приостановить выполнение до её решения. Аргументы: {}",
            "required_keys": []
        }
    }

    @staticmethod
    def normalize_input(action_name: str, raw_input) -> dict:
        schema = PlaywrightTools.SCHEMA.get(action_name, {})
        required_keys = schema.get("required_keys", [])
        if isinstance(raw_input, dict):
            return raw_input
        if isinstance(raw_input, str) and required_keys:
            return {required_keys[0]: raw_input}
        if isinstance(raw_input, (int, float)) and required_keys:
            return {required_keys[0]: raw_input}
        return {}

    async def navigate(self, url: str) -> str:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            # Проверяем капчу
            captcha_result = await self.handle_captcha()
            if "капча" in captcha_result.lower():
                return captcha_result
            return f"✓ Перешли на {url}"
        except Exception as e:
            return f"✗ Ошибка навигации: {e}"

    async def handle_captcha(self) -> str:
        """Проверяет наличие капчи и останавливает выполнение до ручного решения."""
        try:
            # Ищем элементы капчи (часто встречается картинка с капчей или iframe)
            captcha_frame = await page.frame_locator("iframe[src*='captcha']").first
            if captcha_frame:
                logger.warning("Обнаружена капча! Пожалуйста, решите её вручную в браузере.")
                # Ждём, пока пользователь решит капчу (например, нажав Enter в консоли)
                input("Нажмите Enter после решения капчи...")
                # Проверяем, что капча исчезла
                await asyncio.sleep(2)
                return "✓ Капча решена"
            # Альтернативно, ищем по тексту
            if await page.locator("text=капча").count() > 0:
                logger.warning("Обнаружена капча! Пожалуйста, решите её вручную.")
                input("Нажмите Enter после решения капчи...")
                return "✓ Капча решена"
            return "✓ Капча не обнаружена"
        except Exception as e:
            logger.error(f"Ошибка при проверке капчи: {e}")
            return "✗ Ошибка проверки капчи"

    async def get_page_info(self) -> str:
        """Собирает все ссылки, которые ведут на PDF или страницу файла, с указанием года."""
        try:
            await self.handle_captcha()
            await page.wait_for_load_state("networkidle", timeout=10000)
            # Ищем все ссылки
            links = await page.query_selector_all("a")
            file_links = []
            for link in links:
                try:
                    href = await link.get_attribute("href") or ""
                    text = (await link.inner_text()).strip()
                    # Если ссылка содержит .pdf или portal/file.aspx или portal/files/
                    if ".pdf" in href.lower() or "/portal/file" in href.lower() or "/portal/files" in href.lower():
                        # Пытаемся извлечь год из текста или href
                        year = None
                        for y in ["2025", "2024", "2023"]:
                            if y in text or y in href:
                                year = y
                                break
                        file_links.append({
                            "href": href,
                            "text": text[:100],
                            "year": year if year else "unknown"
                        })
                except Exception as e:
                    continue
            if not file_links:
                return "✗ Не найдено ни одной ссылки на файлы."
            result = f"Найдено {len(file_links)} ссылок на файлы:\n"
            for i, fl in enumerate(file_links[:20]):
                result += f"  {i+1}. {fl['text']} -> {fl['href']} (год: {fl['year']})\n"
            return result
        except Exception as e:
            return f"✗ Ошибка получения информации: {e}"

    async def download_by_href(self, href: str, company: str, doc_type: str) -> str:
        """Скачивает файл по ссылке. Если ссылка ведёт на страницу файла, переходит и ищет кнопку скачивания."""
        try:
            await self.handle_captcha()
            full_url = href if href.startswith("http") else f"https://www.e-disclosure.ru{href}"
            logger.info(f"Попытка скачать: {full_url}")

            # Если ссылка ведёт на страницу файла (portal/file.aspx), переходим и ищем кнопку скачивания
            if "/portal/file.aspx" in full_url:
                await page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2)
                await self.handle_captcha()
                # Ищем ссылку на скачивание PDF (обычно это ссылка с текстом "Скачать" или на .pdf)
                download_link = await page.query_selector("a[href*='.pdf']")
                if not download_link:
                    download_link = await page.query_selector("a:has-text('Скачать')")
                if not download_link:
                    # пробуем найти любой href с .pdf
                    all_links = await page.query_selector_all("a")
                    for link in all_links:
                        href_attr = await link.get_attribute("href") or ""
                        if ".pdf" in href_attr.lower():
                            download_link = link
                            break
                if not download_link:
                    return "✗ Не удалось найти кнопку скачивания на странице файла."
                # Кликаем с перехватом
                async with page.expect_download(timeout=120000) as dl_info:
                    await download_link.click()
                download = await dl_info.value
            else:
                # Прямая ссылка на PDF или portal/files/
                # Ищем элемент с этим href
                el = await page.query_selector(f'a[href="{href}"]')
                if not el:
                    el = await page.query_selector(f'a[href*="{href[:50]}"]')
                if not el:
                    # если не нашли, просто переходим по ссылке (может сразу скачать)
                    await page.goto(full_url, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    # Проверяем, не началась ли загрузка автоматически (нельзя перехватить)
                    return f"✓ Перешли по ссылке {full_url}, возможно файл скачался автоматически. Проверьте папку загрузок."
                async with page.expect_download(timeout=120000) as dl_info:
                    await el.click()
                download = await dl_info.value

            # Сохраняем
            safe_company = "".join(c for c in company if c.isalnum() or c in " _-").strip()
            safe_type = doc_type.replace(" ", "_")
            ext = os.path.splitext(download.suggested_filename)[1] or ".pdf"
            filename = f"{safe_company}_{safe_type}_{datetime.now().strftime('%Y%m%d')}{ext}"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.exists(filepath):
                base, ext2 = os.path.splitext(filename)
                filename = f"{base}_{datetime.now().strftime('%H%M%S')}{ext2}"
                filepath = os.path.join(DOWNLOAD_DIR, filename)
            await download.save_as(filepath)
            logger.info(f"✓ Файл сохранён: {filepath}")
            return f"✓ Файл скачан: {filepath}"
        except Exception as e:
            logger.error(f"Ошибка скачивания: {e}")
            return f"✗ Ошибка скачивания: {e}"

    async def wait(self, seconds: int = 2) -> str:
        await asyncio.sleep(int(seconds))
        return f"✓ Ожидание {seconds} сек."

    async def call(self, action_name: str, raw_input) -> str:
        kwargs = self.normalize_input(action_name, raw_input)
        logger.info(f"🔧 Инструмент: {action_name} | kwargs: {kwargs}")
        dispatch = {
            "navigate": lambda: self.navigate(**kwargs),
            "get_page_info": lambda: self.get_page_info(),
            "download_by_href": lambda: self.download_by_href(**kwargs),
            "wait": lambda: self.wait(**kwargs),
            "handle_captcha": lambda: self.handle_captcha(),
        }
        if action_name not in dispatch:
            return f"✗ Неизвестный инструмент: {action_name}"
        try:
            return await dispatch[action_name]()
        except Exception as e:
            return f"✗ Ошибка вызова {action_name}: {e}"


# ============================================================
# АГЕНТ (сокращённый промпт)
# ============================================================
SYSTEM_PROMPT_TEMPLATE = """Ты — агент для скачивания документов с e-disclosure.ru.

ЗАДАЧА для компании «{company}»:
- Скачать годовой отчёт МСФО за 2025 год (если нет, то 2024) по ссылке: {msfo_url}
- Скачать отчёт эмитента за 2025 год (если нет, то 2024) по ссылке: {emit_url}

АЛГОРИТМ ДЛЯ КАЖДОЙ ССЫЛКИ:
1. Перейди на страницу (navigate).
2. Если появилась капча, вызови handle_captcha и дождись ручного решения.
3. Используй get_page_info, чтобы найти все ссылки на файлы с годами.
4. Выбери ссылку с нужным годом (2025 или 2024) и скачай через download_by_href (укажи company и doc_type).
5. Если файл не найден, попробуй следующий год.

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
{tools}

ПРАВИЛА:
- Отвечай ТОЛЬКО JSON: {{"action": "имя", "action_input": {{...}}}} или {{"final_answer": "..."}}
- Не добавляй пояснений вне JSON.
- После скачивания каждого файла переходи к следующему.
- После выполнения всех задач ответь финальным сообщением.
"""

class Agent:
    def __init__(self, gigachat: GigaChatClient, tools: PlaywrightTools, company: str, msfo_url: str, emit_url: str):
        self.gigachat = gigachat
        self.tools = tools
        self.company = company
        self.msfo_url = msfo_url
        self.emit_url = emit_url
        self.history = []

    def _build_system_prompt(self) -> str:
        tools_desc = "\n".join(f"  {name}: {info['description']}" for name, info in PlaywrightTools.SCHEMA.items())
        return SYSTEM_PROMPT_TEMPLATE.format(
            company=self.company,
            msfo_url=self.msfo_url,
            emit_url=self.emit_url,
            tools=tools_desc
        )

    def _extract_json(self, text: str) -> dict | None:
        text = text.strip()
        try:
            return json.loads(text)
        except:
            pass
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except:
            return None

    async def run(self, max_iterations: int = 12) -> str:
        system_prompt = self._build_system_prompt()
        self.history = [{"role": "system", "content": system_prompt}]
        self.history.append({
            "role": "user",
            "content": f"Начни для {self.company}. Сначала перейди на страницу МСФО."
        })

        for iteration in range(1, max_iterations + 1):
            logger.info(f"\n--- Итерация {iteration}/{max_iterations} | {self.company} ---")
            response = await self.gigachat.chat(self.history, temperature=0.0, max_tokens=1200)
            if not response:
                logger.error("Нет ответа от GigaChat")
                break
            logger.info(f"LLM ответ: {response}")

            action_data = self._extract_json(response)
            if action_data is None:
                self.history.append({"role": "assistant", "content": response})
                self.history.append({"role": "user", "content": "Ответь строго JSON с action или final_answer."})
                continue

            if "final_answer" in action_data:
                return action_data["final_answer"]

            action_name = action_data.get("action", "")
            raw_input = action_data.get("action_input", {})
            tool_result = await self.tools.call(action_name, raw_input)
            logger.info(f"Результат: {tool_result}")

            self.history.append({"role": "assistant", "content": response})
            self.history.append({
                "role": "user",
                "content": f"Результат {action_name}: {tool_result}\nПродолжай."
            })

        return "Не удалось завершить за отведённое число шагов."


# ============================================================
# ИНИЦИАЛИЗАЦИЯ БРАУЗЕРА
# ============================================================
async def init_browser():
    global browser, page, playwright_instance
    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--no-sandbox"]
    )
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        accept_downloads=True,
    )
    page = await context.new_page()
    await page.set_extra_http_headers({"Accept-Language": "ru-RU,ru;q=0.9"})
    logger.info("✓ Браузер инициализирован")


# ============================================================
# ОБРАБОТКА ОДНОЙ КОМПАНИИ
# ============================================================
async def process_company(gigachat: GigaChatClient, company: str, links: dict) -> dict:
    msfo_url = links.get('msfo_url')
    emit_url = links.get('emit_url')
    if not msfo_url or not emit_url:
        return {"company": company, "status": "error", "error": "Отсутствуют ссылки в базе"}

    tools = PlaywrightTools()
    agent = Agent(gigachat, tools, company, msfo_url, emit_url)
    try:
        result = await agent.run(max_iterations=12)
        return {"company": company, "status": "success", "result": result}
    except Exception as e:
        logger.exception(f"Ошибка при обработке {company}")
        return {"company": company, "status": "error", "error": str(e)}


# ============================================================
# MAIN
# ============================================================
async def main():
    logger.info("=" * 55)
    logger.info("  ВЫГРУЗКА ДОКУМЕНТОВ (АГЕНТ + БАЗА + ОБРАБОТКА КАПЧИ)")
    logger.info("=" * 55)

    companies_links = load_company_links(CSV_PATH, COMPANIES)
    if not companies_links:
        logger.error("Не загружены ссылки для компаний. Проверьте CSV.")
        return

    await init_browser()
    gigachat = GigaChatClient(GIGACHAT_CLIENT_SECRET, GIGACHAT_SCOPE)
    await gigachat.get_access_token()

    results = []
    for company in COMPANIES:
        if company not in companies_links:
            logger.warning(f"Компания {company} не найдена в CSV, пропускаем.")
            continue
        result = await process_company(gigachat, company, companies_links[company])
        results.append(result)
        await asyncio.sleep(3)

    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()

    logger.info("\n" + "=" * 55)
    logger.info("ИТОГОВЫЙ ОТЧЁТ")
    for r in results:
        icon = "✓" if r["status"] == "success" else "✗"
        logger.info(f"\n{icon} {r['company']}:")
        if r["status"] == "error":
            logger.info(f"   Ошибка: {r['error']}")
        else:
            logger.info(f"   {r['result'][:300]}")
    logger.info(f"\n📁 Файлы: {os.path.abspath(DOWNLOAD_DIR)}")


if __name__ == "__main__":
    asyncio.run(main())