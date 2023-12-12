import logging
from .api import EventsManager

def delete_event_rule(sender, instance, *args, **kwargs):
    event_rule = instance.event_rule
    event_bridge_client = EventsManager()
    event_bridge_client.delete_rule(event_rule.name)