def get_days_span(self, month_index):
        
        is_first_month = month_index == 0
        is_last_month = month_index == self.__len__() - 1

        y = int(self.start_date.year + (self.start_date.month + month_index) / 13)
        m = int((self.start_date.month + month_index) % 12 or 12)
        total = calendar.monthrange(y, m)[1]

        if is_first_month and is_last_month:
            return (self.end_date - self.start_date).days + 1
        else:
            if is_first_month:
                return total - self.start_date.day + 1
            elif is_last_month:
                return self.end_date.day
            else:
                return total
