"""
Модуль для обработки PDF файлов и извлечения текста
"""
import pdfplumber
from pathlib import Path
from typing import Optional, List


class PDFProcessor:
    """Класс для работы с PDF документами"""
    
    def __init__(self, pdf_path: Path):
        """
        Инициализация процессора PDF
        
        Args:
            pdf_path: Путь к PDF файлу
            
        Raises:
            FileNotFoundError: Если файл не найден
        """
        self.pdf_path = Path(pdf_path)
        
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF файл не найден: {self.pdf_path}")
        
        if not self.pdf_path.is_file():
            raise ValueError(f"Указанный путь не является файлом: {self.pdf_path}")
    
    def extract_text(self, max_pages: Optional[int] = None, verbose: bool = False) -> str:
        """
        Извлекает текст из PDF файла
        
        Args:
            max_pages: Максимальное количество страниц для обработки
            verbose: Выводить ли подробную информацию
            
        Returns:
            Извлеченный текст из PDF
        """
        text_parts = []
        
        try:
            if verbose:
                print(f"📄 Обработка: {self.pdf_path.name}")
            
            with pdfplumber.open(self.pdf_path) as pdf:
                total_pages = len(pdf.pages)
                pages_to_process = min(max_pages or total_pages, total_pages)
                
                if verbose:
                    print(f"   Страниц: {pages_to_process}/{total_pages}")
                
                for page_num in range(pages_to_process):
                    try:
                        page = pdf.pages[page_num]
                        page_text = page.extract_text()
                        
                        if page_text and page_text.strip():
                            text_parts.append(
                                f"\n{'='*60}\n"
                                f"СТРАНИЦА {page_num + 1}\n"
                                f"{'='*60}\n"
                                f"{page_text}"
                            )
                        
                        # Прогресс каждые 10 страниц
                        if verbose and (page_num + 1) % 10 == 0:
                            print(f"   Обработано: {page_num + 1}/{pages_to_process}")
                    
                    except Exception:
                        continue
                
                if verbose:
                    print(f"   ✓ Готово: {len(text_parts)} страниц")
                
        except Exception as e:
            raise Exception(f"Ошибка при чтении PDF: {str(e)}")
        
        if not text_parts:
            raise Exception("Не удалось извлечь текст из PDF")
        
        return "\n".join(text_parts)
    
    @staticmethod
    def truncate_text(text: str, max_length: int, keep_start_ratio: float = 0.7) -> str:
        """
        Умно обрезает текст до максимальной длины
        
        Args:
            text: Исходный текст
            max_length: Максимальная длина
            keep_start_ratio: Доля начала текста
            
        Returns:
            Обрезанный текст
        """
        if len(text) <= max_length:
            return text
        
        start_length = int(max_length * keep_start_ratio)
        end_length = max_length - start_length
        
        start_text = text[:start_length]
        end_text = text[-end_length:] if end_length > 0 else ""
        
        truncation_notice = (
            f"\n\n{'='*70}\n"
            f"⚠️ ТЕКСТ ОБРЕЗАН (удалено {len(text) - max_length:,} символов)\n"
            f"{'='*70}\n\n"
        )
        
        return f"{start_text}{truncation_notice}{end_text}"
    
    def get_metadata(self) -> dict:
        """Получает метаданные PDF файла"""
        metadata = {
            'filename': self.pdf_path.name,
            'size_mb': round(self.pdf_path.stat().st_size / (1024 * 1024), 2),
        }
        
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                metadata['total_pages'] = len(pdf.pages)
        except Exception:
            metadata['total_pages'] = 0
        
        return metadata