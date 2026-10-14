"""
Конфигурация приложения для анализа МСФО отчетности
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class Config:
    """Класс с настройками приложения"""
    
    # ========================================================================
    # Базовые пути
    # ========================================================================
    BASE_DIR = Path(__file__).parent.absolute()
    PDF_DIR = BASE_DIR / "pdf"
    DATA_DIR = BASE_DIR / "data"
    STATIC_DIR = BASE_DIR / "static"
    TEMPLATES_DIR = BASE_DIR / "templates"
    
    # ========================================================================
    # GigaChat API Credentials
    # ========================================================================
    GIGACHAT_CLIENT_ID = os.getenv('GIGACHAT_CLIENT_ID')
    GIGACHAT_CLIENT_SECRET = os.getenv('GIGACHAT_CLIENT_SECRET')
    GIGACHAT_SCOPE = os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')
    
    # ========================================================================
    # API Endpoints
    # ========================================================================
    GIGACHAT_AUTH_URL = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
    GIGACHAT_API_URL = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
    
    # ========================================================================
    # Настройки модели GigaChat
    # ========================================================================
    GIGACHAT_MODEL = 'GigaChat'
    TEMPERATURE = 0.05  # Очень низкая для максимальной точности
    MAX_TOKENS = 2048
    TOP_P = 0.1
    
    # ========================================================================
    # Настройки обработки PDF
    # ========================================================================
    MAX_TEXT_LENGTH = 30000
    MAX_PAGES_TO_PROCESS = 60
    
    # ========================================================================
    # Настройки кэширования
    # ========================================================================
    CACHE_FILE = DATA_DIR / "analysis_cache.json"
    CACHE_ENABLED = True
    
    # ========================================================================
    # Flask настройки
    # ========================================================================
    FLASK_HOST = 'fmdlatest.railway.internal'
    FLASK_PORT = 8080
    FLASK_DEBUG = True
    SECRET_KEY = 'your-secret-key-change-in-production'
    
    # ========================================================================
    # Таймауты
    # ========================================================================
    AUTH_TIMEOUT = 30
    API_TIMEOUT = 120
    
    # ========================================================================
    # Финансовые показатели для анализа
    # ========================================================================
    FINANCIAL_METRICS = [
        'revenue',        # Выручка
        'net_profit',     # Чистая прибыль
        'net_debt',       # Чистый долг
        'ebitda'          # EBITDA
    ]
    
    METRIC_LABELS = {
        'revenue': 'Выручка',
        'net_profit': 'Чистая прибыль',
        'net_debt': 'Чистый долг',
        'ebitda': 'EBITDA'
    }
    
    @classmethod
    def init_directories(cls):
        """Создает необходимые директории если их нет"""
        cls.PDF_DIR.mkdir(exist_ok=True)
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.STATIC_DIR.mkdir(exist_ok=True)
        cls.TEMPLATES_DIR.mkdir(exist_ok=True)
        (cls.STATIC_DIR / 'css').mkdir(exist_ok=True)
        (cls.STATIC_DIR / 'js').mkdir(exist_ok=True)
        (cls.STATIC_DIR / 'images').mkdir(exist_ok=True)
    
    @classmethod
    def validate(cls):
        """
        Проверяет наличие всех необходимых настроек
        
        Raises:
            ValueError: Если отсутствуют критичные настройки
        """
        errors = []
        
        if not cls.GIGACHAT_CLIENT_ID:
            errors.append("GIGACHAT_CLIENT_ID не установлен в .env файле")
        
        if not cls.GIGACHAT_CLIENT_SECRET:
            errors.append("GIGACHAT_CLIENT_SECRET не установлен в .env файле")
        
        if not cls.PDF_DIR.exists():
            errors.append(f"Папка с PDF файлами не найдена: {cls.PDF_DIR}")
        
        # Проверяем наличие PDF файлов
        pdf_files = list(cls.PDF_DIR.glob("*.pdf"))
        if not pdf_files:
            errors.append(f"В папке {cls.PDF_DIR} нет PDF файлов")
        
        if errors:
            error_message = "Ошибки конфигурации:\n" + "\n".join(f"  - {err}" for err in errors)
            raise ValueError(error_message)