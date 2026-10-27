def delay_exponential(base, growth_factor, attempts):
    
    if base == 'rand':
        base = random.random()
    elif base <= 0:
        raise ValueError("The 'base' param must be greater than 0, "
                         "got: {}".format(base))
    time_to_sleep = base * (growth_factor ** (attempts - 1))
    return time_to_sleep
