"""Explicit local handlers for standalone time and weather questions."""
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone


def weather_answer(city: str):
    url = "https://wttr.in/" + urllib.request.pathname2url(city) + "?format=j1&lang=zh"
    request = urllib.request.Request(url, headers={"User-Agent": "qwen-pc-demo"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    current = data["current_condition"][0]
    description = current["weatherDesc"][0]["value"].strip()
    place = f"{city}天气" if city else "当前位置天气"
    return (f"{place}：{description}，气温{current['temp_C']}°C，"
            f"体感{current['FeelsLikeC']}°C，湿度{current['humidity']}%。")


def local_answer(question: str):
    question = question.strip().rstrip("？?!。 ")
    if any(mark in question for mark in ("顺便", "然后", "并且", "另外", "再帮我", "以及")):
        return None
    if re.fullmatch(r"(?:现在|当前|今天)?(?:是)?(?:几点钟?|时间|日期|几号|几月几[日号]|星期几|周几)(?:是)?(?:多少|呢|了)?", question):
        now = datetime.now(timezone(timedelta(hours=8)))
        weekday = "一二三四五六日"[now.weekday()]
        return f"现在是北京时间 {now:%Y年%m月%d日 %H:%M:%S}，星期{weekday}。"
    city = next((name for name in ("沈阳", "北京", "上海", "广州", "深圳") if name in question), None)
    weather_question = question.replace(city, "") if city else question
    if re.fullmatch(r"(?:今天|现在|当前)?(?:的)?(?:天气|气温|温度)(?:怎么样|如何)?(?:呢|呀|吧)?", weather_question):
        try:
            # wttr.in resolves an empty location from the computer's public IP,
            # so queries such as "今天天气怎么样" still work without a city.
            return weather_answer(city or "")
        except Exception:
            return None
    return None
