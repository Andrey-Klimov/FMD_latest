"""
Модуль для анализа множества компаний
"""
import json
from pathlib import Path
from typing import List, Dict
from config import Config
from pdf_processor import PDFProcessor
from gigachat_client import GigaChatClient
import time


class CompanyAnalyzer:
    """Класс для анализа финансовой отчетности компаний"""
    
    def __init__(self):
        self.gigachat_client = GigaChatClient()
        self.cache_file = Config.CACHE_FILE
        self.cache = self._load_cache()
    
    def _load_cache(self) -> dict:
        """Загружает кэш результатов анализа"""
        if Config.CACHE_ENABLED and self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_cache(self):
        """Сохраняет кэш результатов"""
        if Config.CACHE_ENABLED:
            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Ошибка сохранения кэша: {e}")
    
    def analyze_company(self, pdf_path: Path, use_cache: bool = True) -> Dict:
        """
        Анализирует одну компанию
        
        Args:
            pdf_path: Путь к PDF файлу
            use_cache: Использовать ли кэш
            
        Returns:
            Словарь с результатами анализа
        """
        pdf_name = pdf_path.name
        
        # Проверяем кэш
        if use_cache and pdf_name in self.cache:
            print(f"   ✓ Используется кэш для {pdf_name}")
            return self.cache[pdf_name]
        
        try:
            # Обработка PDF
            print(f"   📄 Обработка {pdf_name}...")
            processor = PDFProcessor(pdf_path)
            text = processor.extract_text(
                max_pages=Config.MAX_PAGES_TO_PROCESS,
                verbose=False
            )
            
            # Обрезка текста если нужно
            if len(text) > Config.MAX_TEXT_LENGTH:
                text = PDFProcessor.truncate_text(text, Config.MAX_TEXT_LENGTH)
            
            # Анализ через GigaChat
            print(f"   🤖 Анализ через GigaChat...")
            company_name = pdf_path.stem.replace('_', ' ').title()
            result = self.gigachat_client.analyze_financial_report(text, company_name)
            
            # Добавляем метаданные
            result['pdf_file'] = pdf_name
            result['company_display_name'] = result.get('company', company_name)
            result['analyzed_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Сохраняем в кэш
            self.cache[pdf_name] = result
            self._save_cache()
            
            print(f"   ✓ Готово: {result['company_display_name']}")
            
            return result
            
        except Exception as e:
            print(f"   ✗ Ошибка при анализе {pdf_name}: {str(e)}")
            
            # Возвращаем заглушку с ошибкой
            return {
                'pdf_file': pdf_name,
                'company': pdf_path.stem.replace('_', ' ').title(),
                'company_display_name': pdf_path.stem.replace('_', ' ').title(),
                'period': 'Ошибка анализа',
                'revenue': 'Ошибка',
                'net_profit': 'Ошибка',
                'net_debt': 'Ошибка',
                'ebitda': 'Ошибка',
                'notes': f'Ошибка: {str(e)}',
                'error': True,
                'analyzed_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def analyze_all_companies(self, force_reanalyze: bool = False) -> List[Dict]:
        """
        Анализирует все компании из папки PDF
        
        Args:
            force_reanalyze: Пересканировать даже если есть кэш
            
        Returns:
            Список результатов анализа
        """
        pdf_files = list(Config.PDF_DIR.glob("*.pdf"))
        
        if not pdf_files:
            raise Exception(f"В папке {Config.PDF_DIR} нет PDF файлов")
        
        print(f"\n{'='*70}")
        print(f"АНАЛИЗ ФИНАНСОВОЙ ОТЧЕТНОСТИ")
        print(f"{'='*70}")
        print(f"Найдено PDF файлов: {len(pdf_files)}\n")
        
        results = []
        
        for i, pdf_file in enumerate(pdf_files, 1):
            print(f"[{i}/{len(pdf_files)}] {pdf_file.name}")
            
            result = self.analyze_company(
                pdf_file,
                use_cache=not force_reanalyze
            )
            results.append(result)
            
            # Небольшая задержка между запросами
            if i < len(pdf_files):
                time.sleep(1)
        
        print(f"\n{'='*70}")
        print(f"✅ Анализ завершен: {len(results)} компаний")
        print(f"{'='*70}\n")
        
        return results
    
    def get_cached_results(self) -> List[Dict]:
        """
        Возвращает результаты из кэша
        
        Returns:
            Список результатов из кэша
        """
        return list(self.cache.values())
    
    def clear_cache(self):
        """Очищает кэш"""
        self.cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()
        print("Кэш очищен")