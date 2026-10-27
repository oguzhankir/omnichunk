def get_batch(self):
        
        if self.all_finished():
            return None

        batch_str = self.queue_result.get()
        batch = pickle.loads(batch_str)
        if batch is not None:
            return batch
        else:
            self.nb_workers_finished += 1
            if self.nb_workers_finished >= self.nb_workers:
                try:
                    self.queue_source.get(timeout=0.001)  # remove the None from the source queue
                except QueueEmpty:
                    pass
                return None
            else:
                return self.get_batch()
