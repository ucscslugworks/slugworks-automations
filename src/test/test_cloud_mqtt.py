from bpm.bambuconfig import BambuConfig
from bpm.bambuprinter import BambuPrinter
from bpm.bambutools import parseFan, parseStage

from src.bambu_printers.bambu_account import BambuAccount

account = BambuAccount("slugworks@ucsc.edu")

hostname = "us.mqtt.bambulab.com"
access_code = account.get_token()
serial_number = account.get_devices()["Scooby"]
username = account.get_username()

config = BambuConfig(
    hostname=hostname,
    access_code=access_code,
    serial_number=serial_number,
    mqtt_username=username,
    mqtt_port=8883,
)
printer = BambuPrinter(config=config)


def on_update(printer):
    print(
        f"tool=[{round(printer.tool_temp, 1)}/{round(printer.tool_temp_target, 1)}] "
        + f"bed=[{round(printer.bed_temp, 1)}/{round(printer.bed_temp_target, 1)}] "
        + f"fan=[{parseFan(printer.fan_speed)}] print=[{printer.gcode_state}] speed=[{printer.speed_level}] "
        + f"light=[{'on' if printer.light_state else 'off'}]"
    )

    print(
        f"stg_cur=[{parseStage(printer.current_stage)}] file=[{printer.gcode_file}] "
        + f"layers=[{printer.layer_count}] layer=[{printer.current_layer}] "
        + f"%=[{printer.percent_complete}] eta=[{printer.time_remaining} min] "
        + f"spool=[{printer.active_spool} ({printer.spool_state})]"
    )


printer.on_update = on_update
printer.start_session()

# go do other stuff
