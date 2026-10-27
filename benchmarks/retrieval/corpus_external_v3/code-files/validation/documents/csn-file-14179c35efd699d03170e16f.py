#!/usr/bin/python
# -*- coding: utf8 -*-


import os
import os.path
import signal
import sys
import logging


class SignalHandler(object):
    
    restart_signals = (signal.SIGHUP, )
    abort_signals = (signal.SIGTERM, signal.SIGINT, signal.SIGQUIT)
    pause_signals = (signal.SIGTSTP, )
    resume_signals = (signal.SIGALRM, signal.SIGCONT)
    status_signals = (signal.SIGUSR1, 29)  # 29 == SIGINFO
    error_signals = (signal.SIGUSR2, )
    handled_signals = restart_signals + abort_signals + pause_signals + resume_signals + status_signals + error_signals

    def __init__(self, logger=logging, signals=handled_signals, handler=None):
        if handler is None:
            handler = self.default_handler
        self.log = logger
        self.log.info('Registering Signal Handler')
        self.exit_callbacks = []
        self.abort_callbacks = []
        self.status_callbacks = []
        self.resume_callbacks = []
        self.set_handler(signals, handler)

    def set_handler(self, signals, handler=signal.SIG_DFL):
        
        for sig in signals:
            self.log.debug("Creating handler for signal: {0}".format(sig))
            signal.signal(sig, handler)

    def pseudo_handler(self, signum, frame):
        
        self.log.warn("Received sigal {0} but system is already busy processing a previous signal, current frame: {1}".format(signum, str(frame)))

    def default_handler(self, signum, frame):
        
        self.log.debug("Signal handler called with signal: {0}".format(signum))
        # 1. If signal is HUP restart the python process
        # 2. If signal is TERM, INT or QUIT we try to cleanup then exit with -1
        # 3. If signal is STOP or TSTP we pause
        # 4. If signal is CONT or USR1 we continue
        # 5. If signal is INFO we print status
        # 6. If signal is USR2 we we abort and then exit with -1

        if signum in self.restart_signals:
            self.set_handler(self.handled_signals, self.pseudo_handler)
            self._cleanup()
            os.execl('python', 'python', * sys.argv)
        elif signum in self.abort_signals:
            self.abort(signum)
        elif signum in self.pause_signals:
            self.pause(signum)
        elif signum in self.resume_signals:
            self.resume(signum)
        elif signum in self.status_signals:
            self.status(signum)
        elif signum in self.error_signals:
            self.log.error('Signal handler received error signal from an external process, aborting')
            self.abort(signum)
        else:
            self.log.error("Unhandled signal received: {0}".format(signum))
            raise

    def pause(self, signum, seconds=0, callback_function=None):
        
        if callback_function is None:
            callback_function = self.default_handler
        if seconds > 0:
            self.log.info("Signal handler pausing for {0} seconds or until it receives SIGALRM or SIGCONT".format(seconds))
            signal.signal(signal.SIGALRM, callback_function)
            signal.alarm(seconds)
        else:
            self.log.info('Signal handler pausing until it receives SIGALRM or SIGCONT')
        signal.signal(signal.SIGCONT, callback_function)
        signal.pause()
        self.log.info('Signal handler resuming from pause')
        if signum == signal.SIGALRM:
            return True
        else:
            return False

    def abort(self, signum):
        
        self.log.info('Signal handler received abort request')
        self._abort(signum)
        self._exit(signum)
        os._exit(1)

    def status(self, signum):
        
        self.log.debug('Signal handler got status signal')
        new_status_callbacks = []
        for status_call in self.status_callbacks:
            # If callback is non persistent we remove it
            try:
                self.log.debug("Calling {0}({1},{2})".format(status_call['function'].__name__, status_call['args'], status_call['kwargs']))
            except AttributeError:
                self.log.debug("Calling unbound function/method {0}".format(str(status_call)))

            apply(status_call['function'], status_call['args'], status_call['kwargs'])
            if status_call['persistent']:
                new_status_callbacks.append(status_call)
        self.status_callbacks = new_status_callbacks
        self._resume(signum)

    def resume(self, signum):
        
        self._resume(signum)

    def _abort(self, signum):
        self.log.debug('Signal handler initiated abort/cleanup')
        current_handler = signal.getsignal(signum)
        new_abort_callbacks = []
        self.set_handler(self.abort_signals, self.pseudo_handler)
        for abort_call in self.abort_callbacks[:]:
            if not abort_call['persistent']:
                new_abort_callbacks.append(abort_call)
            self._log_event(abort_call)
            apply(abort_call['function'], abort_call['args'], abort_call['kwargs'])
        self.abort_callbacks = new_abort_callbacks
        self.set_handler(self.abort_signals, current_handler)

    def _exit(self, signum):
        self.log.info('Signal handler initiated exit')
        current_handler = signal.getsignal(signum)
        new_exit_callbacks = []
        self.set_handler(self.abort_signals, self.pseudo_handler)
        for exit_call in self.exit_callbacks[:]:
            if not exit_call['persistent']:
                new_exit_callbacks.append(exit_call)
            self._log_event(exit_call)
            apply(exit_call['function'], exit_call['args'], exit_call['kwargs'])
        self.exit_callbacks = new_exit_callbacks
        self.set_handler(self.abort_signals, current_handler)

    def _resume(self, signum):
        self.log.debug('Signal handler processing resume tasks')
        resume_handler = signal.getsignal(signum)
        pause_handler = signal.getsignal(signal.SIGTSTP)
        new_resume_callbacks = []
        self.set_handler(self.resume_signals, self.pseudo_handler)
        self.set_handler(self.pause_signals, self.pseudo_handler)
        for resume_call in self.resume_callbacks:
            if not resume_call['persistent']:
                new_resume_callbacks.append(resume_call)
            self._log_event(resume_call)
            apply(resume_call['function'], resume_call['args'], resume_call['kwargs'])
        self.resume_callbacks = new_resume_callbacks
        self.set_handler(self.resume_signals, resume_handler)
        self.set_handler(self.pause_signals, pause_handler)

    def _unreg_event(self, event_list, event):
        
        try:
            self.log.debug("Removing event {0}({1},{2})".format(event['function'].__name__, event['args'], event['kwargs']))
        except AttributeError:
            self.log.debug("Removing event {0}".format(str(event)))

        try:
            event_list.remove(event)
        except ValueError:
            try:
                self.log.warn("Unable to remove event {0}({1},{2}) , not found in list: {3}".format(event['function'].__name__, event['args'], event['kwargs'], event_list))
            except AttributeError:
                self.log.debug("Unable to remove event {0}".format(str(event)))
            raise KeyError('Unable to unregister the specified event from the signals specified')

    def _log_event(self, event):
        try:
            self.log.debug("Calling {0}({1},{2})".format(event['function'].__name__, event['args'], event['kwargs']))
        except AttributeError:
            self.log.debug("Calling unbound function/method {0}".format(str(event)))

    def _create_event(self, callable_object, signal_name, persistent, *args, **kwargs):
        try:
            self.log.debug("Registered function/method {0} to call on {1} signal".format(callable_object.__name__, signal_name))
        except AttributeError:
            self.log.debug("Registered unbound function/method {0} to call on {1} signal".format(callable_object, signal_name))

        return {'function': callable_object, 'args': args, 'kwargs': kwargs, 'persistent': persistent}

    def del_exit_event(self, event):
        self._unreg_event(self.exit_callbacks, event)

    def del_abort_event(self, event):
        self._unreg_event(self.abort_callbacks, event)

    def del_status_event(self, event):
        self._unreg_event(self.status_callbacks, event)

    def del_resume_event(self, event):
        self._unreg_event(self.resume_callbacks, event)

    def reg_on_exit(self, callable_object, *args, **kwargs):
        
        persistent = kwargs.pop('persistent', False)
        event = self._create_event(callable_object, 'exit', persistent, *args, **kwargs)
        self.exit_callbacks.append(event)
        return event

    def reg_on_abort(self, callable_object, *args, **kwargs):
        
        persistent = kwargs.pop('persistent', False)
        event = self._create_event(callable_object, 'abort', persistent, *args, **kwargs)
        self.abort_callbacks.append(event)
        return event

    def reg_on_status(self, callable_object, *args, **kwargs):
        
        persistent = kwargs.pop('persistent', False)
        event = self._create_event(callable_object, 'status', persistent, *args, **kwargs)
        self.status_callbacks.append(event)
        return event

    def reg_on_resume(self, callable_object, *args, **kwargs):
        
        persistent = kwargs.pop('persistent', False)
        event = self._create_event(callable_object, 'resume', persistent, *args, **kwargs)
        self.resume_callbacks.append(event)
        return event
