"""
Flask Landing — зеркало базы agr_base.xlsx
Отдает:
 - /landing — главный экран (сетка компаний, 4 показателя G,H,J,X)
 - /company/<slug> — карточка компании с источниками и скриншотами
 - /api/landing/companies — JSON списка
 - /api/landing/company/<slug> — JSON одной компании
 - /evidence/<slug>/<filename> — отдача скриншота с корректной обработкой кириллицы

Кириллица: файлы хранятся как есть (UTF-8). URL кодируется через encodeURIComponent на фронте
 и декодируется через urllib.parse.unquote на бэке. Слаг = ticker lower (латиница), поэтому
 путь безопасен. Маппинг slug -> папка берется из landing_data.json.
"""
import json
import urllib.parse
from pathlib import Path, PureWindowsPath
from flask import Flask, render_template, jsonify, request, send_file, abort, redirect
from landing_processor import build_landing_data, XLSX_PATH, DATA_DIR

BASE_DIR = Path(__file__).parent
LANDING_JSON = DATA_DIR / "landing_data.json"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'landing-secret'

# --- helpers ---
def load_landing_data():
    if not LANDING_JSON.exists():
        print(f"Landing JSON not found, building from {XLSX_PATH}")
        build_landing_data()
    with open(LANDING_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

# cache in memory
_companies_cache = None
_slug_to_company = {}
_slug_to_folder = {}

def get_cache():
    global _companies_cache, _slug_to_company, _slug_to_folder
    if _companies_cache is None:
        data = load_landing_data()
        _companies_cache = data
        for c in data:
            slug = c["slug"]
            _slug_to_company[slug] = c
            if c.get("folder"):
                folder_name = PureWindowsPath(c["folder"]).name
                local_folder = BASE_DIR / 'baza_v2' / '03_Отчетность_и_скриншоты' / folder_name
                _slug_to_folder[slug] = local_folder if local_folder.exists() else Path(c["folder"])
    return _companies_cache

# --- original routes kept for compatibility ---
from config import Config
from analyzer import CompanyAnalyzer
import warnings
warnings.filterwarnings('ignore')
Config.init_directories()
analyzer = CompanyAnalyzer()

@app.route('/')
def index():
    return redirect('/landing')

@app.route('/api/companies')
def get_companies():
    try:
        companies = analyzer.get_cached_results()
        if not companies:
            return jsonify({'status': 'no_data','message': 'Нет данных. Запустите анализ через /api/analyze'}), 200
        sort_by = request.args.get('sort_by', 'revenue')
        order = request.args.get('order', 'desc')
        if sort_by in Config.FINANCIAL_METRICS:
            companies = sorted(companies, key=lambda x: parse_numeric_value(x.get(sort_by, '0')), reverse=(order == 'desc'))
        return jsonify({'status': 'success','companies': companies,'count': len(companies),'metrics': Config.METRIC_LABELS})
    except Exception as e:
        return jsonify({'status': 'error','message': str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_companies():
    try:
        data = request.get_json() or {}
        force = data.get('force', False)
        results = analyzer.analyze_all_companies(force_reanalyze=force)
        return jsonify({'status': 'success','message': f'Проанализировано компаний: {len(results)}','companies': results,'count': len(results)})
    except Exception as e:
        return jsonify({'status': 'error','message': str(e)}), 500

@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    try:
        analyzer.clear_cache()
        return jsonify({'status': 'success','message': 'Кэш очищен'})
    except Exception as e:
        return jsonify({'status': 'error','message': str(e)}), 500

@app.route('/api/company/<filename>')
def get_company_details(filename):
    try:
        companies = analyzer.get_cached_results()
        company = next((c for c in companies if c.get('pdf_file') == filename), None)
        if company:
            return jsonify({'status': 'success','company': company})
        else:
            return jsonify({'status': 'error','message': 'Компания не найдена'}), 404
    except Exception as e:
        return jsonify({'status': 'error','message': str(e)}), 500

def parse_numeric_value(value_str: str) -> float:
    if not value_str or value_str in ['Нет данных', 'Ошибка', 'Не найдено']:
        return 0
    try:
        import re
        numbers = re.findall(r'[-\d,\.]+', str(value_str))
        if numbers:
            num_str = numbers[0].replace(',', '')
            return float(num_str)
    except:
        pass
    return 0

# --- LANDING ROUTES ---

@app.route('/landing')
def landing():
    return render_template('landing.html')

@app.route('/company/<slug>')
def company_page(slug):
    # allow palette
    cache = get_cache()
    if slug not in _slug_to_company:
        abort(404)
    return render_template('company.html', slug=slug, company=_slug_to_company[slug])

@app.route('/api/landing/companies')
def api_landing_companies():
    data = get_cache()
    # optional query: search, sort, sector
    q = request.args.get('q', '').strip().lower()
    sector = request.args.get('sector', '').strip()
    sort_by = request.args.get('sort_by', 'revenue')
    order = request.args.get('order', 'desc')
    filtered = data
    if q:
        filtered = [c for c in filtered if q in c['company'].lower() or q in c['ticker'].lower() or q in c['sector'].lower()]
    if sector and sector != 'all':
        filtered = [c for c in filtered if c['sector'] == sector]
    # sort
    key_map = {
        'revenue': lambda x: x['revenue'] if x['revenue'] is not None else -10**18,
        'profit': lambda x: x['net_profit'] if x['net_profit'] is not None else -10**18,
        'ebitda': lambda x: x['ebitda_report'] if x['ebitda_report'] is not None else -10**18,
        'debt': lambda x: x['net_debt'] if x['net_debt'] is not None else -10**18,
        'name': lambda x: x['company']
    }
    key_fn = key_map.get(sort_by, key_map['revenue'])
    reverse = (order == 'desc')
    # for name reverse logic differs
    if sort_by == 'name':
        reverse = (order == 'asc')  # keep asc natural? but keep as requested
        filtered = sorted(filtered, key=key_fn, reverse=(order == 'desc'))
    else:
        filtered = sorted(filtered, key=key_fn, reverse=reverse)
    # sectors list for filter UI
    sectors = sorted(list({c['sector'] for c in data if c['sector']}))
    return jsonify({'status': 'success', 'companies': filtered, 'count': len(filtered), 'sectors': sectors})

@app.route('/api/landing/company/<slug>')
def api_landing_company(slug):
    get_cache()
    comp = _slug_to_company.get(slug)
    if not comp:
        return jsonify({'status': 'error', 'message': 'Компания не найдена'}), 404
    return jsonify({'status': 'success', 'company': comp})

@app.route('/evidence/<slug>/<path:filename>')
def serve_evidence(slug, filename):
    """Отдает файл из evidence-папки. filename приходит URL-encoded; Flask уже декодирует, но делаем unquote на всякий."""
    get_cache()
    folder = _slug_to_folder.get(slug)
    if not folder:
        abort(404)
    # decode
    decoded = urllib.parse.unquote(filename)
    # security: prevent path traversal
    file_path = folder / "evidence" / decoded
    # also handle case where evidence root is directly folder (fallback)
    if not file_path.exists():
        # try without evidence subfolder
        alt = folder / decoded
        if alt.exists():
            file_path = alt
        else:
            # try case-insensitive search
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
    # normalize
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
        data = build_landing_data()
        global _companies_cache, _slug_to_company, _slug_to_folder
        _companies_cache = None
        _slug_to_company = {}
        _slug_to_folder = {}
        get_cache()
        return jsonify({'status': 'success', 'count': len(data)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# --- FMD LATEST EXPORT API ---
from io import BytesIO
import csv
import zipfile
import openpyxl
from flask import make_response

FMD_DATA_JSON = BASE_DIR / 'static' / 'data' / 'fmd_latest_data.json'

def _load_fmd_data():
    with open(FMD_DATA_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

def _safe_tickers(payload):
    available = {c['ticker'] for c in _load_fmd_data()['companies']}
    tickers = [str(x) for x in (payload.get('tickers') or []) if str(x) in available]
    return tickers

def _xlsx_financials(tickers, columns=None):
    data = _load_fmd_data()['companies']
    cs = [c for c in data if c['ticker'] in tickers]
    out = BytesIO(); wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Финансовые показатели'
    headers = ['Компания','Тикер','Отрасль','Валюта','Цена, RUB','EV / EBITDA','ND / EBITDA','P / E','Выручка 2025, млн','EBITDA 2025, млн','Чистая прибыль 2025, млн','Чистый долг 2025, млн']
    ws.append(headers)
    for c in cs:
        ws.append([c['company'],c['ticker'],c['sector'],c['currency'],c.get('price'),c.get('ev_ebitda'),c.get('nd_ebitda'),c.get('pe'),c.get('revenue'),c.get('ebitda'),c.get('net_profit'),c.get('net_debt')])
    hs=wb.create_sheet('История 2023-2025'); hs.append(['Компания','Тикер','Год','Валюта','Выручка, млн','EBITDA, млн','Чистая прибыль, млн','Чистый долг, млн'])
    for c in cs:
        for y in ('2023','2024','2025'):
            h=(c.get('history') or {}).get(y) or {}; hs.append([c['company'],c['ticker'],int(y),h.get('currency') or c['currency'],h.get('revenue'),h.get('ebitda'),h.get('net_profit'),h.get('net_debt')])
    for sheet in wb.worksheets:
        sheet.freeze_panes='A2'; sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]: cell.font=openpyxl.styles.Font(bold=True)
        for col in sheet.columns:
            letter=col[0].column_letter; sheet.column_dimensions[letter].width=min(30,max(12,max(len(str(x.value or '')) for x in col)+2))
    wb.save(out); out.seek(0); return out

def _xlsx_quotes(tickers):
    data = {c['ticker']:c for c in _load_fmd_data()['companies']}
    out=BytesIO(); wb=openpyxl.Workbook(); wb.remove(wb.active)
    for t in tickers:
        c=data[t]; ws=wb.create_sheet(t[:31]); ws.append(['Дата','Цена, RUB','Объем','Оборот, RUB','Сделки'])
        for r in c.get('market_series') or []: ws.append([r.get('date'),r.get('price'),r.get('volume'),r.get('turnover'),r.get('trades')])
        for cell in ws[1]: cell.font=openpyxl.styles.Font(bold=True)
        ws.freeze_panes='A2'
    if not wb.sheetnames: wb.create_sheet('Нет данных')
    wb.save(out); out.seek(0); return out

def _reports_zip(tickers, include_financials=False, include_quotes=False):
    by_ticker={c['ticker']:c for c in _load_fmd_data()['companies']}
    out=BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        if include_financials: z.writestr('FMD_financials.xlsx',_xlsx_financials(tickers).getvalue())
        if include_quotes: z.writestr('FMD_quotes.xlsx',_xlsx_quotes(tickers).getvalue())
        for t in tickers:
            c=by_ticker[t]; folder=BASE_DIR/'baza_v2'/'03_Отчетность_и_скриншоты'/str(c.get('folder_rel') or '')
            if folder.exists():
                for f in folder.rglob('*'):
                    if f.is_file() and f.name not in {'.DS_Store'}:
                        z.write(f, f'Отчетность/{t}/{f.relative_to(folder)}')
    out.seek(0); return out

@app.route('/api/fmd/export', methods=['POST'])
def api_fmd_export():
    payload=request.get_json(silent=True) or {}; kind=payload.get('type'); tickers=_safe_tickers(payload)
    if not tickers: return jsonify({'status':'error','message':'Пустая выборка'}),400
    if kind=='financials':
        bio=_xlsx_financials(tickers,payload.get('columns')); name='FMD_financials.xlsx'; mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif kind=='quotes':
        bio=_xlsx_quotes(tickers); name='FMD_quotes.xlsx'; mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif kind=='reports':
        bio=_reports_zip(tickers); name='FMD_reports.zip'; mime='application/zip'
    elif kind=='full':
        bio=_reports_zip(tickers,True,True); name='FMD_full_selection.zip'; mime='application/zip'
    else: return jsonify({'status':'error','message':'Неизвестный тип выгрузки'}),400
    return send_file(bio,as_attachment=True,download_name=name,mimetype=mime)

if __name__ == '__main__':
    # ensure data built
    get_cache()
    print(f"Landing data: {len(_companies_cache)} companies")
    print("Routes: /landing , /company/<slug> , /api/landing/companies , /evidence/<slug>/<file>")
    app.run(host='fmdlatest-production.up.railway.app', port=8080, debug=True)
