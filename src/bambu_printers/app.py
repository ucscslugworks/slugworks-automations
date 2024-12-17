import datetime
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
    data = db.get_usage()
    if not data:
        return render_template("usage.html", usage=[])

    today = datetime.datetime.now().date()
    dates = [
        (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)
    ]
    colors = [c[:6] for c in data[0][1:]]
    indexed = {date: u for date, *u in data[1]}
    organized = {color: [] for color in colors}
    for date in dates:
        if date in indexed:
            for i, u in enumerate(indexed[date]):
                organized[colors[i]].append(0 if u is None else u)
        else:
            for color in colors:
                organized[color].append(0)

    organized = {color: u for color, u in organized.items() if any(u)}
    colors = list(organized.keys())

    return render_template("usage.html", labels=dates, usage=organized)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
