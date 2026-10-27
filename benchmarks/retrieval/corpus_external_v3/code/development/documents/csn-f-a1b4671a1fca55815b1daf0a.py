def as_dict(self):
        

        return {
            "destination": self.destination,
            "packet_transmit": self.packet_transmit,
            "packet_receive": self.packet_receive,
            "packet_loss_count": self.packet_loss_count,
            "packet_loss_rate": self.packet_loss_rate,
            "rtt_min": self.rtt_min,
            "rtt_avg": self.rtt_avg,
            "rtt_max": self.rtt_max,
            "rtt_mdev": self.rtt_mdev,
            "packet_duplicate_count": self.packet_duplicate_count,
            "packet_duplicate_rate": self.packet_duplicate_rate,
        }
