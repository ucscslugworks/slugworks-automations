import time

from bpm.bambuconfig import BambuConfig
from bpm.bambuprinter import BambuPrinter
from bpm.bambutools import parseFan, parseStage

from src import constants, log
from src.bambu_printers import get_account, get_db

HOSTNAME = "us.mqtt.bambulab.com"
PORT = 8883

PRINTER_OBJECTS = dict()


def get_printer(name: str, serial: str):
    global PRINTER_OBJECTS

    if name in PRINTER_OBJECTS:
        p = PRINTER_OBJECTS[name]
        p.logger.info(f"get_printer: returned duplicate printer: {name}")
        return PRINTER_OBJECTS[name]
    else:
        printer = Printer(name, serial)
        PRINTER_OBJECTS[name] = printer
        printer.logger.info(f"get_printer: created new printer: {name}")
        return printer


class Printer:
    def __init__(self, name: str, serial: str):
        self.logger = log.setup_logs("bambu_printer", additional_handlers=[("bambu", log.INFO)])

        self.name = name

        account = get_account()
        config = BambuConfig(
            hostname=HOSTNAME,
            access_code=account.get_token(),
            serial_number=serial,
            mqtt_username=account.get_username(),
            mqtt_port=PORT,
        )
        self.printer = BambuPrinter(config=config)

        self.db = get_db()
        self.db.add_printer(name)

        self.last_update = -1
        self.tool_temp = -1
        self.tool_temp_target = -1
        self.bed_temp = -1
        self.bed_temp_target = -1
        self.fan_speed = -1
        self.gcode_state = constants.BAMBU_UNKNOWN
        self.speed_level = -1
        self.light_state = False

        self.current_stage = -1
        self.gcode_file = ""
        self.layer_count = -1
        self.current_layer = -1
        self.percent_complete = -1
        self.time_remaining = -1
        self.start_time = -1
        self.active_spool = -1
        self.spool_state = ""

        self.printer.on_update = self.on_update
        self.printer.start_session()

        self.logger.info(f"init: Initialized printer {self.name}.")

    def on_update(self, printer):
        self.last_update = int(time.time())
        self.tool_temp = float(printer.tool_temp)
        self.tool_temp_target = float(printer.tool_temp_target)
        self.bed_temp = float(printer.bed_temp)
        self.bed_temp_target = float(printer.bed_temp_target)
        self.fan_speed = int(parseFan(printer.fan_speed))

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

        self.speed_level = int(printer.speed_level)
        self.light_state = int(printer.light_state == "on")

        self.current_stage = str(parseStage(printer.current_stage))
        self.gcode_file = str(printer.gcode_file)
        self.layer_count = int(printer.layer_count)
        self.current_layer = int(printer.current_layer)
        self.percent_complete = int(printer.percent_complete)
        self.time_remaining = int(printer.time_remaining * 60)
        self.start_time = int(printer.start_time * 60)
        self.active_spool = int(printer.active_spool)
        try:
            self.spool_state = constants.PRINTER_SPOOL_STATES.index(printer.spool_state)
        except ValueError:
            self.spool_state = -1

        self.db.update_printer(
            self.name,
            last_update=self.last_update,
            gcode_state=self.gcode_state,
            tool_temp=self.tool_temp,
            tool_temp_target=self.tool_temp_target,
            bed_temp=self.bed_temp,
            bed_temp_target=self.bed_temp_target,
            fan_speed=self.fan_speed,
            speed_level=self.speed_level,
            light_state=self.light_state,
            current_stage=self.current_stage,
            gcode_file=self.gcode_file,
            layer_count=self.layer_count,
            current_layer=self.current_layer,
            percent_complete=self.percent_complete,
            time_remaining=self.time_remaining,
            start_time=self.start_time,
            end_time=self.start_time + self.time_remaining,
            active_spool=self.active_spool,
            spool_state=self.spool_state,
        )

        self.logger.info(f"on_update: {self.name}")

    def cancel(self):
        self.printer.stop_printing()
        self.db.update_printer(self.name, status=constants.PRINTER_IDLE)
        self.logger.info(f"cancel: {self.name}")

    def get_status(self):
        return self.gcode_state

    def stop_thread(self):
        self.printer.quit()
        self.logger.info(f"stop_thread: {self.name}")


if __name__ == "__main__":
    account = get_account()
    devices = account.get_devices()
    printer = get_printer("Shaggy", devices["Shaggy"])
    # printer2 = get_printer("Shaggy", devices["Shaggy"])
