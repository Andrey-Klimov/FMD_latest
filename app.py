"""
Flask веб-приложение для анализа финансовой отчетности
 + Landing зеркало agr_base.xlsx (G,H,J,X) с источниками и скриншотами
Кириллица: файлы отдаются через /evidence/<slug>/<filename> с URL-кодированием, без переименования
"""
from flask import Flask, render_template, jsonify, request, send_file, abort
from config import Config
from analyzer import CompanyAnalyzer
import warnings
import json
import urllib.parse
from pathlib import Path

# Подавляем предупреждения SSL
warnings.filterwarnings('ignore')

# Инициализация Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Создаем необходимые директории
Config.init_directories()

# Инициализация анализатора
analyzer = CompanyAnalyzer()


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/companies')
def get_companies():
    """
    API endpoint для получения списка компаний
    
    Query params:
        - sort_by: поле для сортировки (revenue, net_profit, net_debt, ebitda)
        - order: порядок сортировки (asc, desc)
    """
    try:
        # Получаем закэшированные результаты
        companies = analyzer.get_cached_results()
        
        # Если кэш пуст - запускаем анализ
        if not companies:
            return jsonify({
                'status': 'no_data',
                'message': 'Нет данных. Запустите анализ через /api/analyze'
            }), 200
        
        # Параметры сортировки
        sort_by = request.args.get('sort_by', 'revenue')
        order = request.args.get('order', 'desc')
        
        # Сортировка
        if sort_by in Config.FINANCIAL_METRICS:
            companies = sorted(
                companies,
                key=lambda x: parse_numeric_value(x.get(sort_by, '0')),
                reverse=(order == 'desc')
            )
        
        return jsonify({
            'status': 'success',
            'companies': companies,
            'count': len(companies),
            'metrics': Config.METRIC_LABELS
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_companies():
    """
    API endpoint для запуска анализа компаний
    
    Body params:
        - force: пересканировать даже если есть кэш (true/false)
    """
    try:
        data = request.get_json() or {}
        force = data.get('force', False)
        
        # Запускаем анализ
        results = analyzer.analyze_all_companies(force_reanalyze=force)
        
        return jsonify({
            'status': 'success',
            'message': f'Проанализировано компаний: {len(results)}',
            'companies': results,
            'count': len(results)
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    """API endpoint для очистки кэша"""
    try:
        analyzer.clear_cache()
        return jsonify({
            'status': 'success',
            'message': 'Кэш очищен'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/company/<filename>')
def get_company_details(filename):
    """Получить подробную информацию о компании"""
    try:
        companies = analyzer.get_cached_results()
        company = next(
            (c for c in companies if c.get('pdf_file') == filename),
            None
        )
        
        if company:
            return jsonify({
                'status': 'success',
                'company': company
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Компания не найдена'
            }), 404
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def parse_numeric_value(value_str: str) -> float:
    """
    Извлекает числовое значение из строки
    
    Args:
        value_str: Строка типа "1,234,567 млн руб."
        
    Returns:
        Числовое значение
    """
    if not value_str or value_str in ['Нет данных', 'Ошибка', 'Не найдено']:
        return 0
    
    try:
        # Убираем все кроме цифр, точек, запятых и минусов
        import re
        numbers = re.findall(r'[-\d,\.]+', str(value_str))
        if numbers:
            # Берем первое число
            num_str = numbers[0].replace(',', '')
            return float(num_str)
    except:
        pass
    
    return 0


# ===================== LANDING: зеркало базы agr_base.xlsx =====================
BASE_DIR = Path(__file__).parent
LANDING_JSON = BASE_DIR / "data" / "landing_data.json"
_landing_cache = None
_slug_to_company = {}
_slug_to_folder = {}

def _load_landing():
    global _landing_cache, _slug_to_company, _slug_to_folder
    if _landing_cache is not None:
        return _landing_cache
    if not LANDING_JSON.exists():
        try:
            from landing_processor import build_landing_data
            build_landing_data()
        except Exception as e:
            print(f"Landing build failed: {e}")
            _landing_cache = []
            return _landing_cache
    with open(LANDING_JSON, "r", encoding="utf-8") as f:
        _landing_cache = json.load(f)
    # Quotes are refreshed at most once per completed calendar day. If ISS is
    # unavailable, quote_service keeps and returns the latest successful cache.
    try:
        from quote_service import enrich_companies
        enrich_companies(_landing_cache)
    except Exception as e:
        print(f"MOEX quote refresh failed: {e}")
    for c in _landing_cache:
        _slug_to_company[c["slug"]] = c
        if c.get("folder"):
            _slug_to_folder[c["slug"]] = Path(c["folder"])
    return _landing_cache

@app.route('/landing')
def landing():
    return render_template('landing.html')

@app.route('/company/<slug>')
def company_page(slug):
    data = _load_landing()
    comp = _slug_to_company.get(slug)
    if not comp:
        abort(404)
    return render_template('company.html', slug=slug, company=comp)

@app.route('/api/landing/companies')
def api_landing_companies():
    data = _load_landing()
    q = request.args.get('q', '').strip().lower()
    sector = request.args.get('sector', '').strip()
    sort_by = request.args.get('sort_by', 'revenue')
    order = request.args.get('order', 'desc')
    filtered = data
    if q:
        filtered = [c for c in filtered if q in c['company'].lower() or q in c['ticker'].lower() or q in c['sector'].lower()]
    if sector and sector != 'all':
        filtered = [c for c in filtered if c['sector'] == sector]
    key_map = {
        'revenue': lambda x: x['revenue'] if x['revenue'] is not None else -10**18,
        'profit': lambda x: x['net_profit'] if x['net_profit'] is not None else -10**18,
        'ebitda': lambda x: x['ebitda_report'] if x['ebitda_report'] is not None else -10**18,
        'debt': lambda x: x['net_debt'] if x['net_debt'] is not None else -10**18,
        'pe': lambda x: ((x.get('market') or {}).get('latest') or {}).get('pe') if ((x.get('market') or {}).get('latest') or {}).get('pe') is not None else -10**18,
        'ev_ebitda': lambda x: ((x.get('market') or {}).get('latest') or {}).get('ev_ebitda') if ((x.get('market') or {}).get('latest') or {}).get('ev_ebitda') is not None else -10**18,
        'net_debt_ebitda': lambda x: ((x.get('market') or {}).get('latest') or {}).get('net_debt_ebitda') if ((x.get('market') or {}).get('latest') or {}).get('net_debt_ebitda') is not None else -10**18,
        'name': lambda x: x['company']
    }
    key_fn = key_map.get(sort_by, key_map['revenue'])
    if sort_by == 'name':
        filtered = sorted(filtered, key=key_fn, reverse=(order == 'desc'))
    else:
        filtered = sorted(filtered, key=key_fn, reverse=(order == 'desc'))
    sectors = sorted(list({c['sector'] for c in data if c['sector']}))
    return jsonify({'status': 'success', 'companies': filtered, 'count': len(filtered), 'sectors': sectors})

@app.route('/api/landing/company/<slug>')
def api_landing_company(slug):
    _load_landing()
    comp = _slug_to_company.get(slug)
    if not comp:
        return jsonify({'status': 'error', 'message': 'Компания не найдена'}), 404
    return jsonify({'status': 'success', 'company': comp})

@app.route('/evidence/<slug>/<path:filename>')
def serve_evidence(slug, filename):
    _load_landing()
    folder = _slug_to_folder.get(slug)
    if not folder:
        abort(404)
    decoded = urllib.parse.unquote(filename)
    file_path = folder / "evidence" / decoded
    if not file_path.exists():
        alt = folder / decoded
        if alt.exists():
            file_path = alt
        else:
            ev_dir = folder / "evidence"
            if ev_dir.exists():
                for p in ev_dir.iterdir():
                    if p.name == decoded or p.name.lower() == decoded.lower():
                        file_path = p
                        break
                else:
                    abort(404)
            else:
                abort(404)
    try:
        file_path = file_path.resolve()
        folder_resolved = folder.resolve()
        if not str(file_path).startswith(str(folder_resolved)):
            abort(403)
    except:
        pass
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_file(str(file_path))

@app.route('/api/landing/rebuild', methods=['POST'])
def rebuild_landing():
    try:
        from landing_processor import build_landing_data
        data = build_landing_data()
        global _landing_cache, _slug_to_company, _slug_to_folder
        _landing_cache = None
        _slug_to_company = {}
        _slug_to_folder = {}
        _load_landing()
        return jsonify({'status': 'success', 'count': len(data)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/landing/quotes/refresh', methods=['POST'])
def refresh_landing_quotes():
    """Force a fresh ISS request and rebuild daily valuation multiples."""
    try:
        global _landing_cache
        data = _load_landing()
        from quote_service import enrich_companies
        enrich_companies(data, force=True)
        LANDING_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        _landing_cache = data
        return jsonify({'status': 'success', 'count': len(data)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 502
# =================== END LANDING ===================

if __name__ == '__main__':
    # Пытаемся проверить конфиг, но лэндинг работает и без GigaChat
    try:
        Config.validate()
        print("\nConfig OK")
    except ValueError as e:
        print(f"\n[WARN] Config invalid (GigaChat/PDF not needed for landing):\n{e}\n")
        print("Продолжаем запуск лэндинга...")
    # Греем кэш лэндинга
    try:
        _load_landing()
        print(f"Landing ready: {len(_landing_cache)} companies")
        print(f"Landing: http://{Config.FLASK_HOST}:{Config.FLASK_PORT}/landing")
        print(f"API: http://{Config.FLASK_HOST}:{Config.FLASK_PORT}/api/landing/companies")
        print(f"Company example: http://{Config.FLASK_HOST}:{Config.FLASK_PORT}/company/lkoh")
    except Exception as e:
        print(f"Landing load error: {e}")
    app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG
    )
