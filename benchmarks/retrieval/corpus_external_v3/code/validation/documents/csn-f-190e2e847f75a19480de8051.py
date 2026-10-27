def reg_on_resume(self, callable_object, *args, **kwargs):
        
        persistent = kwargs.pop('persistent', False)
        event = self._create_event(callable_object, 'resume', persistent, *args, **kwargs)
        self.resume_callbacks.append(event)
        return event
