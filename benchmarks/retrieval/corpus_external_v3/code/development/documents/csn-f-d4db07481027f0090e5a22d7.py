def node_restart(self):
        
        log.info('Restart')
        res = self.__exchange('node.restart()')
        log.info(res)
        return res
