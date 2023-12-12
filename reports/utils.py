from .api import EventsManager

class EventBridgeHandler():

    def _create_event_rule(self, rule_name, description, cron_expression):
        success = True
        try:
            response = EventsManager().create(
                rule_name,
                cron_expression,
                description
            )
            if 'exception' in response:
                msg = f'Failed creating event rule in AWS: {response.get("exception")}'
                response = {}
                success = False
            else:
                msg = 'Successfuly created rule in AWS'
        except Exception as e:
            msg = f'Failed creating event rule in AWS: {e}'
            response = {}
            success = False
        return response, msg, success