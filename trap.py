
class Trap:
    def __init__(self, token, serial, start_of_run, focus, version):
        self.token = token
        self.serial = serial
        self.start_of_run = start_of_run
        self.image_taken_today = False
        self.start_up_index = 0
        self.run_time = 0
        self.connectivity = False
        self.focus = focus
        self.version = version

    def set_was_image_taken_today(self, image_taken_today):
        self.image_taken_today = image_taken_today

    def set_startup_index(self, startup_index):
        self.start_up_index = startup_index

    def set_connectivity(self, connectivity):
        self.connectivity = connectivity

    def get_trap_id(self):
        return self.serial

    def get_trap_version(self):
        return self.version


