from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag
def render_graph(report_job_info):
    html_content = report_job_info.report_file_graphs.read().decode()
    return mark_safe(html_content)