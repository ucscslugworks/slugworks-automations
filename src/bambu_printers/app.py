import logging
import os

from flask import Flask, render_template, url_for

from src import constants, log
from src.bambu_printers import get_db

db = get_db()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.urandom(24).hex()
app.url_map.strict_slashes = True

logger = logging.getLogger("gunicorn.error")


@app.route("/", methods=["GET"])
def dashboard():
    printer_names = db.get_printer_list()
    # print(printer_names)
    # printer_data = [db.get_printer_data(name) for name, in printer_names]
    printer_data = []
    for (name,) in printer_names:
        data = db.get_printer_data(name)
        if not data or data["status"] == constants.PRINTER_OFFLINE:
            continue

        if data["status"] == constants.PRINTER_IDLE:
            data["status"] = "Printer Idle"
            data["percent_complete"] = 100
            data["time_remaining"] = 0
        elif data["gcode_state"] == constants.GCODE_PAUSE:
            data["status"] = "Print Paused"
        else:
            data["status"] = "Printing"

        colors = []
        for color in data["colors"].split(","):
            if color:
                colors.append(color)

        if data["print_id"] != constants.NO_PRINT_ID:
            data["cover"] = db.get_cover(data["print_id"])

        if "cover" not in data or not data["cover"]:
            data["cover"] = url_for("static", filename=f"{name}.png")

        printer_data.append(
            {
                "name": name,
                "status": data["status"],
                "progress": data["percent_complete"],
                "time": "%dh %02dm" % divmod(data["time_remaining"] / 60, 60),
                "cover": data["cover"],
                "colors": colors,
            }
        )
    # print(printer_data)
    return render_template("dashboard.html", printers=printer_data)


@app.route("/usage", methods=["GET"])
def usage():
    return "Hello, world!"


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5001)
