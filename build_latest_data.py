from pathlib import Path, PureWindowsPath
import json, math, openpyxl
ROOT=Path(__file__).resolve().parent
landing=json.loads((ROOT/'data/landing_data.json').read_text(encoding='utf-8'))
by_ticker={c['ticker']:c for c in landing}
wb=openpyxl.load_workbook(ROOT/'baza_v2/01_base/agr_base.xlsx', data_only=True, read_only=True)
ws=wb['Финансы 3 года']
history={}
for row in list(ws.values)[4:]:
    company,ticker,year,currency=row[:4]
    if not ticker or not isinstance(year,(int,float)): continue
    def n(v):
        return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) else None
    history.setdefault(str(ticker),{})[str(int(year))]={
        'currency':currency,
        'revenue': n(row[4]), 'net_profit':n(row[5]), 'ebitda':n(row[6]),
        'adjusted_ebitda':n(row[7]), 'ebitda_pre_ifrs16':n(row[8]), 'ebitdac':n(row[9]), 'oibda':n(row[10]),
        'net_debt':n(row[18]), 'source_file':row[19], 'source_page':row[20]
    }
wb.close()
companies=[]
for c in landing:
    t=c['ticker']; h=history.get(t,{})
    latest=(c.get('market') or {}).get('latest') or {}
    metrics=c.get('metrics') or {}
    folder_name=PureWindowsPath(c.get('folder') or '').name if c.get('folder') else ''
    def evidence(metric):
        m=metrics.get(metric) or {}
        return {
            'source':m.get('source') or '', 'source_file':m.get('source_file') or '', 'source_page':str(m.get('source_page') or ''),
            'evidence':m.get('evidence') or []
        }
    # 2025 main figures from historical workbook where possible; fall back to landing cache.
    y25=h.get('2025',{})
    revenue=y25.get('revenue') if y25.get('revenue') is not None else c.get('revenue')
    ebitda=y25.get('ebitda') if y25.get('ebitda') is not None else c.get('ebitda_report')
    profit=y25.get('net_profit') if y25.get('net_profit') is not None else c.get('net_profit')
    debt=y25.get('net_debt') if y25.get('net_debt') is not None else c.get('net_debt')
    ev=latest.get('ev_ebitda'); nd=latest.get('net_debt_ebitda'); pe=latest.get('pe')
    companies.append({
        'company':c['company'],'ticker':t,'slug':c['slug'],'sector':c['sector'],'currency':c['currency'],
        'folder_rel':folder_name,
        'price':latest.get('price'),'quote_date':latest.get('date'),
        'ev_ebitda':ev,'nd_ebitda':nd,'pe':pe,
        'revenue':revenue,'ebitda':ebitda,'net_profit':profit,'net_debt':debt,
        'history':h,
        'market_series':(c.get('market') or {}).get('series') or [],
        'sources':{
            'revenue':evidence('revenue'),'ebitda':evidence('ebitda'),'net_profit':evidence('net_profit'),'net_debt':evidence('net_debt')
        }
    })
out={'companies':companies,'sectors':sorted({x['sector'] for x in companies if x.get('sector')}),'financial_year':2025}
path=ROOT/'static/data/fmd_latest_data.json';path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(out,ensure_ascii=False,allow_nan=False),encoding='utf-8')
print('wrote',path,len(companies))
