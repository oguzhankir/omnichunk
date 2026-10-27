def station_selection_menu(self, error=None):
        
        self.screen.clear()

        if error:
            self.screen.print_error("{}\n".format(error))

        for i, station in enumerate(self.stations):
            i = "{:>3}".format(i)
            print("{}: {}".format(Colors.yellow(i), station.name))

        return self.stations[self.screen.get_integer("Station: ")]
