from datetime import date, datetime
from django import template
from dateutil.parser import parse

register = template.Library()


@register.simple_tag
def format_timestamp(datetime_obj) -> list:
    try:
        parsed = parse(str(datetime_obj))
        return parsed.strftime("%Y-%m-%d %I:%M %p")
    except Exception as e:
        return datetime_obj