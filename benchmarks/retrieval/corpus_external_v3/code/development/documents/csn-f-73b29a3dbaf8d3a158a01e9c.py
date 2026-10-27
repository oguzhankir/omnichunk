def get_context_data(self, **kwargs):
        
        sEcho = self.query_data["sEcho"]

        context = super(BaseListView, self).get_context_data(**kwargs)
        queryset = context["object_list"]
        if queryset is not None:
            total_length = self.get_queryset_length(queryset)
            queryset = self.filter_queryset(queryset)
            display_length = self.get_queryset_length(queryset)

            queryset = self.sort_queryset(queryset)
            queryset = self.paging_queryset(queryset)
            values_list = self.convert_queryset_to_values_list(queryset)
            context = {
                "sEcho": sEcho,
                "iTotalRecords": total_length,
                "iTotalDisplayRecords": display_length,
                "aaData": values_list,
            }
        else:
            context = {
                "sEcho": sEcho,
                "iTotalRecords": 0,
                "iTotalDisplayRecords": 0,
                "aaData": [],
            }
        return context
