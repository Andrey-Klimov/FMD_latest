"""
Главный модуль приложения для анализа финансовой отчетности МСФО с использованием GigaChat AI
"""
import sys
import os
from pathlib import Path
from colorama import init, Fore, Style
from tabulate import tabulate
import warnings
import json
from datetime import datetime

# Подавляем предупреждения SSL для GigaChat
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Импорт наших модулей
from config import Config
from pdf_processor import PDFProcessor
from gigachat_client import GigaChatClient

# Инициализация colorama для цветного вывода
init(autoreset=True)


def print_header():
    """Выводит красивый заголовок приложения"""
    header = f"""
{Fore.CYAN}{Style.BRIGHT}{'='*70}
  АНАЛИЗАТОР ФИНАНСОВОЙ ОТЧЕТНОСТИ МСФО
  Powered by GigaChat AI
{'='*70}{Style.RESET_ALL}
"""
    print(header)


def print_step(step_num: int, message: str):
    """Выводит информацию о текущем шаге выполнения"""
    print(f"\n{Fore.YELLOW}{'─'*70}")
    print(f"{Fore.YELLOW}[Шаг {step_num}] {Fore.WHITE}{Style.BRIGHT}{message}")
    print(f"{Fore.YELLOW}{'─'*70}{Style.RESET_ALL}")


def print_success(message: str):
    """Выводит сообщение об успешном выполнении"""
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def print_error(message: str):
    """Выводит сообщение об ошибке"""
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")


def print_info(message: str):
    """Выводит информационное сообщение"""
    print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")


def print_warning(message: str):
    """Выводит предупреждение"""
    print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")


def display_results_table(results: dict):
    """
    Отображает результаты анализа в виде красивой таблицы
    
    Args:
        results: Словарь с финансовыми показателями
    """
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*70}")
    print(f"{Fore.CYAN}{Style.BRIGHT}  📊 РЕЗУЛЬТАТЫ АНАЛИЗА")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*70}{Style.RESET_ALL}\n")
    
    # Таблица с общей информацией
    info_data = [
        [f"{Fore.CYAN}Компания:{Style.RESET_ALL}", results.get('company', 'Не определено')],
        [f"{Fore.CYAN}Отчетный период:{Style.RESET_ALL}", results.get('period', 'Не определено')]
    ]
    
    print(tabulate(
        info_data,
        tablefmt="fancy_grid",
        colalign=("left", "left")
    ))
    
    print()
    
    # Таблица с финансовыми показателями
    financial_data = [
        ["Показатель", "Значение"],
        ["─" * 35, "─" * 45],
        [f"{Fore.GREEN}💰 Выручка{Style.RESET_ALL}", results.get('revenue', 'Не найдено')],
        [f"{Fore.BLUE}📈 Чистая прибыль{Style.RESET_ALL}", results.get('net_profit', 'Не найдено')],
        [f"{Fore.MAGENTA}📊 EBITDA{Style.RESET_ALL}", results.get('ebitda', 'Не найдено')],
        [f"{Fore.YELLOW}📉 P/E{Style.RESET_ALL}", results.get('pe_ratio', 'Не найдено')]
    ]
    
    print(tabulate(
        financial_data,
        headers="firstrow",
        tablefmt="fancy_grid",
        colalign=("left", "right")
    ))
    
    # Примечания
    if results.get('notes'):
        print(f"\n{Fore.YELLOW}📝 Примечания:{Style.RESET_ALL}")
        print(f"   {results['notes']}")
    
    print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}\n")


def display_raw_response(raw_text: str):
    """
    Отображает полный необработанный ответ от GigaChat
    
    Args:
        raw_text: Полный текст ответа
    """
    print(f"\n{Fore.MAGENTA}{'─'*70}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}📄 ПОЛНЫЙ ОТВЕТ GIGACHAT:{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'─'*70}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{raw_text}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'─'*70}{Style.RESET_ALL}\n")


def save_results(results: dict, pdf_name: str):
    """
    Сохраняет результаты анализа в файлы
    
    Args:
        results: Словарь с результатами
        pdf_name: Имя анализируемого PDF файла
    """
    try:
        # Создаем папку для результатов
        results_dir = Config.BASE_DIR / "results"
        results_dir.mkdir(exist_ok=True)
        
        # Генерируем имя файла с timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_company_name = results.get('company', 'unknown')[:30].replace(' ', '_').replace('"', '').replace('/', '_')
        
        # Сохраняем в JSON
        json_filename = f"{safe_company_name}_{timestamp}.json"
        json_path = results_dir / json_filename
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print_success(f"JSON сохранен: {json_filename}")
        
        # Сохраняем в TXT (человекочитаемый формат)
        txt_filename = f"{safe_company_name}_{timestamp}.txt"
        txt_path = results_dir / txt_filename
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("РЕЗУЛЬТАТЫ АНАЛИЗА ФИНАНСОВОЙ ОТЧЕТНОСТИ МСФО\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Исходный файл: {pdf_name}\n")
            f.write(f"Дата анализа: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("-" * 70 + "\n")
            f.write("ОБЩАЯ ИНФОРМАЦИЯ:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Компания: {results.get('company', 'Не определено')}\n")
            f.write(f"Отчетный период: {results.get('period', 'Не определено')}\n\n")
            f.write("-" * 70 + "\n")
            f.write("ФИНАНСОВЫЕ ПОКАЗАТЕЛИ:\n")
            f.write("-" * 70 + "\n")
            f.write(f"Выручка: {results.get('revenue', 'Не найдено')}\n")
            f.write(f"Чистая прибыль: {results.get('net_profit', 'Не найдено')}\n")
            f.write(f"EBITDA: {results.get('ebitda', 'Не найдено')}\n")
            f.write(f"P/E: {results.get('pe_ratio', 'Не найдено')}\n\n")
            
            if results.get('notes'):
                f.write("-" * 70 + "\n")
                f.write("ПРИМЕЧАНИЯ:\n")
                f.write("-" * 70 + "\n")
                f.write(f"{results['notes']}\n\n")
            
            f.write("-" * 70 + "\n")
            f.write("ПОЛНЫЙ ОТВЕТ GIGACHAT:\n")
            f.write("-" * 70 + "\n")
            f.write(results.get('raw_response', 'Нет данных'))
        
        print_success(f"TXT сохранен: {txt_filename}")
        print_info(f"Папка с результатами: {results_dir}")
        
    except Exception as e:
        print_error(f"Ошибка при сохранении результатов: {str(e)}")


def main():
    """Основная функция приложения"""
    
    print_header()
    
    try:
        # ====================================================================
        # Шаг 1: Проверка конфигурации
        # ====================================================================
        print_step(1, "Проверка конфигурации и учетных данных")
        
        try:
            Config.validate()
            print_success("Конфигурация корректна")
            print_info(f"PDF файл: {Config.PDF_PATH.name}")
            print_info(f"Модель GigaChat: {Config.GIGACHAT_MODEL}")
            print_info(f"Temperature: {Config.TEMPERATURE}")
            print_info(f"Max tokens: {Config.MAX_TOKENS}")
            
        except ValueError as e:
            print_error("Ошибка конфигурации!")
            print(f"\n{Fore.RED}{str(e)}{Style.RESET_ALL}\n")
            print_info("Проверьте:")
            print_info("1. Файл .env существует в папке проекта")
            print_info("2. В .env указаны GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET")
            print_info("3. PDF файл 'rosneft test.pdf' находится в папке проекта")
            input("\nНажмите Enter для выхода...")
            sys.exit(1)
        
        # ====================================================================
        # Шаг 2: Тестирование подключения к GigaChat
        # ====================================================================
        print_step(2, "Проверка подключения к GigaChat API")
        
        try:
            client = GigaChatClient()
            
            # Получаем токен для проверки авторизации
            print_info("Проверка авторизации...")
            token = client._get_access_token()
            print_success("Авторизация успешна!")
            
        except Exception as e:
            print_error("Ошибка подключения к GigaChat API!")
            print(f"\n{Fore.RED}{str(e)}{Style.RESET_ALL}\n")
            print_info("Возможные причины:")
            print_info("1. Неверный CLIENT_SECRET в файле .env")
            print_info("2. Нет доступа к интернету")
            print_info("3. API GigaChat временно недоступен")
            input("\nНажмите Enter для выхода...")
            sys.exit(1)
        
        # ====================================================================
        # Шаг 3: Извлечение текста из PDF
        # ====================================================================
        print_step(3, "Извлечение текста из PDF документа")
        
        try:
            processor = PDFProcessor(Config.PDF_PATH)
            
            # Показываем информацию о файле
            metadata = processor.get_metadata()
            print_info(f"Размер файла: {metadata['size_mb']} МБ")
            print_info(f"Страниц в документе: {metadata['total_pages']}")
            
            # Извлекаем текст
            raw_text = processor.extract_text(max_pages=Config.MAX_PAGES_TO_PROCESS)
            
            # Проверяем размер и обрезаем если нужно
            if len(raw_text) > Config.MAX_TEXT_LENGTH:
                print_warning(
                    f"Текст слишком большой ({len(raw_text):,} символов). "
                    f"Обрезается до {Config.MAX_TEXT_LENGTH:,} символов..."
                )
                processed_text = PDFProcessor.truncate_text(raw_text, Config.MAX_TEXT_LENGTH)
                print_info(f"Размер после обрезки: {len(processed_text):,} символов")
            else:
                processed_text = raw_text
                print_success(f"Размер текста ({len(processed_text):,} символов) в пределах лимита")
            
        except FileNotFoundError:
            print_error(f"PDF файл не найден: {Config.PDF_PATH}")
            print_info(f"Убедитесь, что файл находится в: {Config.BASE_DIR}")
            input("\nНажмите Enter для выхода...")
            sys.exit(1)
            
        except Exception as e:
            print_error(f"Ошибка при обработке PDF: {str(e)}")
            import traceback
            print(f"\n{Fore.RED}Детали ошибки:{Style.RESET_ALL}")
            print(traceback.format_exc())
            input("\nНажмите Enter для выхода...")
            sys.exit(1)
        
        # ====================================================================
        # Шаг 4: Анализ с помощью GigaChat
        # ====================================================================
        print_step(4, "Анализ отчетности с помощью GigaChat AI")
        
        print_info("⏰ Отправка запроса к GigaChat...")
        print_info("💡 Это займет 30-90 секунд, пожалуйста подождите...")
        
        try:
            results = client.analyze_financial_report(processed_text)
            print_success("Анализ завершен успешно!")
            
        except Exception as e:
            print_error(f"Ошибка при работе с GigaChat API: {str(e)}")
            import traceback
            print(f"\n{Fore.RED}Детали ошибки:{Style.RESET_ALL}")
            print(traceback.format_exc())
            input("\nНажмите Enter для выхода...")
            sys.exit(1)
        
        # ====================================================================
        # Шаг 5: Отображение результатов
        # ====================================================================
        print_step(5, "Вывод результатов анализа")
        
        # Показываем таблицу с результатами
        display_results_table(results)
        
        # ====================================================================
        # Дополнительные опции
        # ====================================================================
        print(f"{Fore.CYAN}{'─'*70}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{Style.BRIGHT}ДОПОЛНИТЕЛЬНЫЕ ОПЦИИ{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'─'*70}{Style.RESET_ALL}\n")
        
        # Предложение показать полный ответ
        try:
            show_raw = input(f"{Fore.YELLOW}Показать полный ответ GigaChat? (y/n): {Style.RESET_ALL}").strip().lower()
            if show_raw in ['y', 'yes', 'д', 'да']:
                display_raw_response(results.get('raw_response', 'Ответ не найден'))
        except KeyboardInterrupt:
            print("\n")
        
        # Предложение сохранить результаты
        try:
            save_input = input(f"{Fore.CYAN}Сохранить результаты в файлы? (y/n): {Style.RESET_ALL}").strip().lower()
            if save_input in ['y', 'yes', 'д', 'да']:
                save_results(results, Config.PDF_PATH.name)
        except KeyboardInterrupt:
            print("\n")
        
        # Финальное сообщение
        print(f"\n{Fore.GREEN}{Style.BRIGHT}{'='*70}")
        print(f"{Fore.GREEN}{Style.BRIGHT}✅ АНАЛИЗ ЗАВЕРШЕН УСПЕШНО!")
        print(f"{Fore.GREEN}{Style.BRIGHT}{'='*70}{Style.RESET_ALL}\n")
        
        print(f"{Fore.CYAN}Спасибо за использование анализатора МСФО отчетности!{Style.RESET_ALL}\n")
        
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}⚠ Работа программы прервана пользователем{Style.RESET_ALL}\n")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n{Fore.RED}{'='*70}")
        print(f"{Fore.RED}❌ КРИТИЧЕСКАЯ ОШИБКА")
        print(f"{Fore.RED}{'='*70}{Style.RESET_ALL}\n")
        print(f"{Fore.RED}{str(e)}{Style.RESET_ALL}\n")
        
        import traceback
        print(f"{Fore.RED}Полная трассировка ошибки:{Style.RESET_ALL}")
        print(traceback.format_exc())
        
        input("\nНажмите Enter для выхода...")
        sys.exit(1)


if __name__ == "__main__":
    # Настройка кодировки для Windows
    if sys.platform == 'win32':
        try:
            # Устанавливаем UTF-8 для консоли Windows
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except:
            pass
    
    # Запуск основной программы
    main()