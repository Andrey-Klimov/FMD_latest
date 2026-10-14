"""
Клиент для работы с GigaChat API
"""
import requests
import uuid
import time
from typing import Dict
from config import Config


class GigaChatClient:
    """Клиент для взаимодействия с GigaChat API"""
    
    def __init__(self):
        self.access_token = None
        self.token_expires_at = 0
        self.auth_data = Config.GIGACHAT_CLIENT_SECRET
    
    def _get_access_token(self) -> str:
        """Получает access token через OAuth 2.0"""
        
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
        
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'RqUID': str(uuid.uuid4()),
                'Authorization': f'Basic {self.auth_data}'
            }
            
            payload = {'scope': Config.GIGACHAT_SCOPE}
            
            response = requests.post(
                Config.GIGACHAT_AUTH_URL,
                headers=headers,
                data=payload,
                verify=False,
                timeout=Config.AUTH_TIMEOUT
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            expires_in = token_data.get('expires_in', 1800)
            self.token_expires_at = time.time() + expires_in - 60
            
            return self.access_token
            
        except Exception as e:
            raise Exception(f"Ошибка получения токена: {str(e)}")
    
    def analyze_financial_report(self, report_text: str, company_name: str = "") -> Dict:
        """
        Анализирует финансовую отчетность
        
        Args:
            report_text: Текст отчета
            company_name: Название компании (опционально)
            
        Returns:
            Словарь с финансовыми показателями
        """
        token = self._get_access_token()
        prompt = self._create_analysis_prompt(report_text, company_name)
        
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}',
            }
            
            payload = {
                'model': Config.GIGACHAT_MODEL,
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            'Ты - эксперт по финансовому анализу и МСФО. '
                            'Извлекай финансовые показатели с максимальной точностью. '
                            'Все числа указывай точно как в отчете.'
                        )
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'temperature': Config.TEMPERATURE,
                'top_p': Config.TOP_P,
                'max_tokens': Config.MAX_TOKENS,
            }
            
            response = requests.post(
                Config.GIGACHAT_API_URL,
                headers=headers,
                json=payload,
                verify=False,
                timeout=Config.API_TIMEOUT
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                answer_text = result['choices'][0]['message']['content']
                return self._parse_gigachat_response(answer_text)
            else:
                raise Exception("Некорректный ответ от API")
            
        except Exception as e:
            raise Exception(f"Ошибка при запросе к GigaChat: {str(e)}")
    
    def _create_analysis_prompt(self, report_text: str, company_name: str = "") -> str:
        """Создает промпт для анализа"""
        
        company_hint = f" компании {company_name}" if company_name else ""
        
        prompt = f"""
Проанализируй финансовую отчетность по МСФО{company_hint} и извлеки следующие показатели:

📊 ТРЕБУЕМЫЕ ПОКАЗАТЕЛИ:

1. **Выручка (Revenue)** - общая выручка от продаж
2. **Чистая прибыль (Net Profit)** - прибыль после всех вычетов
3. **Чистый долг (Net Debt)** - долгосрочные и краткосрочные заимствования минус денежные средства
4. **EBITDA** - прибыль до процентов, налогов и амортизации

🎯 ИНСТРУКЦИИ:

✓ Используй данные за ПОСЛЕДНИЙ ПОЛНЫЙ отчетный период (2023 год)
✓ Все суммы в ИСХОДНОЙ валюте с единицами (например: "1,234,567 млн руб.")
✓ Для Чистого долга: Долгосрочные займы + Краткосрочные займы - Денежные средства
✓ Если показатель не найден, укажи "Нет данных"

📝 ФОРМАТ ОТВЕТА (строго):
Компания: [название]
Период: [год]
Выручка: [сумма валюта]
Чистая прибыль: [сумма валюта]
Чистый долг: [сумма валюта]
EBITDA: [сумма валюта]
Примечания: [если есть]

text


ОТЧЕТНОСТЬ:

{report_text}

Проведи анализ:
"""
        return prompt
    
    def _parse_gigachat_response(self, response_text: str) -> Dict:
        """Парсит ответ GigaChat"""
        
        result = {
            'company': 'Не определено',
            'period': 'Не определено',
            'revenue': 'Нет данных',
            'net_profit': 'Нет данных',
            'net_debt': 'Нет данных',
            'ebitda': 'Нет данных',
            'notes': '',
            'raw_response': response_text
        }
        
        lines = response_text.split('\n')
        
        for line in lines:
            line_clean = line.strip()
            line_lower = line_clean.lower()
            
            if not line_clean or line_clean.startswith('---'):
                continue
            
            if ':' in line_clean:
                try:
                    key_part, value_part = line_clean.split(':', 1)
                    key_lower = key_part.lower().strip()
                    value = value_part.strip()
                    
                    if 'компани' in key_lower or 'company' in key_lower:
                        result['company'] = value
                    elif 'период' in key_lower or 'period' in key_lower:
                        result['period'] = value
                    elif 'выручка' in key_lower or 'revenue' in key_lower:
                        result['revenue'] = value
                    elif 'чистая прибыль' in key_lower or 'net profit' in key_lower:
                        result['net_profit'] = value
                    elif 'чистый долг' in key_lower or 'net debt' in key_lower:
                        result['net_debt'] = value
                    elif 'ebitda' in key_lower:
                        result['ebitda'] = value
                    elif 'примечани' in key_lower or 'note' in key_lower:
                        result['notes'] = value
                
                except ValueError:
                    continue
        
        return result
