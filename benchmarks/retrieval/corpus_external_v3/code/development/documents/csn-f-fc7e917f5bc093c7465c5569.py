def set_permissions_in_context(self, context={}):
        

        context['has_view_permission'] = self.mongoadmin.has_view_permission(self.request)
        context['has_edit_permission'] = self.mongoadmin.has_edit_permission(self.request)
        context['has_add_permission'] = self.mongoadmin.has_add_permission(self.request)
        context['has_delete_permission'] = self.mongoadmin.has_delete_permission(self.request)
        return context
