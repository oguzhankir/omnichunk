def _format_iso_time(self, time):
    
    if isinstance(time, str):
      return time
    elif isinstance(time, datetime):
      return time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    else:
      return None
