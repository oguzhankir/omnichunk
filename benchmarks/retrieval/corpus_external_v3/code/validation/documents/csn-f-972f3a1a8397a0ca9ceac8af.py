def reg_on_status(self, callable_object, *args, **kwargs):
        
        persistent = kwargs.pop('persistent', False)
        event = self._create_event(callable_object, 'status', persistent, *args, **kwargs)
        self.status_callbacks.append(event)
        return event
