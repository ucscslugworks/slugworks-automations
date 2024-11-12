from bpm.bambuconfig import BambuConfig
from bpm.bambuprinter import BambuPrinter
from bpm.bambutools import parseFan, parseStage

from src import constants, log
from src.bambu_printers.bambu_account import BambuAccount

HOSTNAME = "us.mqtt.bambulab.com"
PORT = 8883


class Printer:
    def __init__(self, account: BambuAccount, name: str, serial: str):
        self.logger = log.setup_logs("bambu_printer")

        self.name = name

        config = BambuConfig(
            hostname=HOSTNAME,
            access_code=account.get_token(),
            serial_number=serial,
            mqtt_username=account.get_username(),
            mqtt_port=PORT,
        )
        self.printer = BambuPrinter(config=config)

        self.tool_temp = 0
        self.tool_temp_target = 0
        self.bed_temp = 0
        self.bed_temp_target = 0
        self.fan_speed = 0
        self.gcode_state = constants.BAMBU_UNKNOWN
        self.speed_level = 0
        self.light_state = False

        self.current_stage = 0
        self.gcode_file = ""
        self.layer_count = 0
        self.current_layer = 0
        self.percent_complete = 0
        self.time_remaining = 0
        self.start_time = 0
        self.active_spool = 0
        self.spool_state = ""

        self.printer.on_update = self.on_update
        self.printer.start_session()

        self.logger.info(f"init: Initialized printer {self.name}.")

    def on_update(self, printer):
        self.tool_temp = printer.tool_temp
        self.tool_temp_target = printer.tool_temp_target
        self.bed_temp = printer.bed_temp
        self.bed_temp_target = printer.bed_temp_target
        self.fan_speed = parseFan(printer.fan_speed)

        if printer.gcode_state == "FAILED":
            self.gcode_state = constants.BAMBU_FAILED
        elif printer.gcode_state == "RUNNING":
            self.gcode_state = constants.BAMBU_RUNNING
        elif printer.gcode_state == "PAUSE":
            self.gcode_state = constants.BAMBU_PAUSE
        elif printer.gcode_state == "IDLE":
            self.gcode_state = constants.BAMBU_IDLE
        elif printer.gcode_state == "FINISH":
            self.gcode_state = constants.BAMBU_FINISH
        else:
            self.gcode_state = constants.BAMBU_UNKNOWN

        self.speed_level = printer.speed_level
        self.light_state = printer.light_state

        self.current_stage = parseStage(printer.current_stage)
        self.gcode_file = printer.gcode_file
        self.layer_count = printer.layer_count
        self.current_layer = printer.current_layer
        self.percent_complete = printer.percent_complete
        self.time_remaining = printer.time_remaining * 60
        self.start_time = printer.start_time * 60
        self.active_spool = printer.active_spool
        self.spool_state = printer.spool_state
        self.logger.info(f"on_update: {self.name}")

    def cancel(self):
        # self.printer.stop_printing()
        self.logger.info(f"cancel: {self.name}")

    def get_status(self):
        return self.gcode_state
    
    def stop_thread(self):
        self.printer.quit()
        self.logger.info(f"stop_thread: {self.name}")