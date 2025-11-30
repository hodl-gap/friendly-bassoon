"""
Prompts for message categorization
"""

def get_categorization_prompt(message_text, message_date):
    """Prompt for categorizing telegram messages"""

    return f"""You are categorizing messages from a financial research Telegram channel.

**Message:**
Date: {message_date}
Text: {message_text}

**Categories:**

1. **greeting** - Simple announcements like "Daily recap 공유드립니다"
   - Just greetings/announcements with no content
   - Will be IGNORED

2. **schedule** - Economic calendar, data release schedules, Fed speech schedules
   - Lists of upcoming events with dates/times
   - Example: "(월) 22:30 뉴욕 제조업 지수..."
   - Will save raw text only

3. **event_announcement** - Event invitations, research forum announcements, advertisements
   - Company events, seminars, promotional content
   - Example: "2026년 하나증권 리서치 포럼 개최됩니다"
   - Will be IGNORED

4. **interview_meeting** - Fed official statements, FOMC minutes, central bank meeting summaries
   - Contains what officials/participants said
   - Lists opinions, views, statements from named individuals
   - Example: "제퍼슨 연준 이사: 12월 인하에 대해선 옵션을 열여두고 있음..."
   - Example: "FOMC 의사록 요약..."
   - Will extract structured data (who said what)

5. **data_update** - Raw data releases without interpretation
   - Just presents data/numbers without analysis or conclusions
   - Example: "비농업 고용 실제 119k / 컨센 53k..."
   - Example: "연속 실업수당 청구건수는 4년래 최고치"
   - Will save raw text only

6. **data_opinion** - Research analysis with data + interpretation
   - Contains specific data/indicators
   - Describes what happened to the data
   - Provides interpretation/conclusions
   - Example: "호주 10년물 금리 18bp 상승... RBA 기준금리 동결... 금리 인하 사이클 종료 가능성"
   - Will extract full structured analysis

7. **other** - Doesn't fit any of the above categories
   - Use this if you're uncertain or the message is ambiguous
   - Flag for manual review

**Your task:**
Categorize this message into ONE of the above categories.

**Output (JSON only):**
```json
{{
    "category": "one of: greeting|schedule|event_announcement|interview_meeting|data_update|data_opinion|other",
    "confidence": "high|medium|low",
    "reason": "1-2 sentence explanation"
}}
```

Return ONLY the JSON, nothing else."""
