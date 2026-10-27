def recurse(self, full_matrix=False):
        
        for n in self.tree.get_nonterminals(order='postorder'):
            n_leaves = len(n._ii)
            if full_matrix: M = np.zeros((n_leaves, n_leaves), dtype=float)
            r = np.zeros(n_leaves, dtype=float)
            c_count = 0
            for c in n:
                ssq = self.branch_variance(c)
                nc = len(c._ii)
                if c.is_terminal():
                    if full_matrix:
                        M[c_count, c_count] = 1.0/ssq
                    r[c_count] = 1.0/ssq
                else:
                    if full_matrix:
                        M[c_count:c_count+nc, c_count:c_count+nc] = c.cinv - ssq*np.outer(c.r,c.r)/(1+ssq*c.s)
                    r[c_count:c_count+nc] = c.r/(1+ssq*c.s)
                c_count += nc

            if full_matrix: n.cinv = M
            n.r = r #M.sum(axis=1)
            n.s = n.r.sum()
