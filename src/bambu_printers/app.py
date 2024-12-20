import colorsys
import datetime
import logging
import math
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
    return render_template("dashboard.html", printers=printer_data)


weeks_count = 10
COLORS = {
    "000000": "Black",
    "FFFFFF": "White",
    "5E43B7": "Basic Purple",
    "68724D": "Matte Dark Green",
    "A3D8E1": "Matte Ice Blue",
    "F99963": "Matte Mandarin Orange",
    "E8AFCF": "Matte Sakura Pink",
    "3F8E43": "Basic Green",
    "61C680": "Matte Grass Green",
    "E4BD68": "Basic Gold",
    "0A2989": "Basic Blue",
    "C12E1F": "Basic Red",
}


@app.route("/usage", methods=["GET"])
def usage():
    data = db.get_usage()
    if not data:
        return render_template("usage.html", usage=[])

    today = datetime.datetime.now().date()
    date_objs = [
        (today - datetime.timedelta(days=i)) for i in range((weeks_count + 1) * 7)
    ]
    dates = []
    counter = 0
    for i, date in enumerate(date_objs):
        if date.weekday() == 0:
            counter += 1
        if counter == weeks_count:
            break
        dates.append((date.strftime("%Y-%m-%d"), date.weekday()))
    dates.reverse()
    colors = [f"#{c[:6]}" for c in data[0][1:]]
    indexed = {date: u for date, *u in data[1]}
    organized = {color: [] for color in colors}

    for date, wkdy in dates:
        if date in indexed:
            for i, u in enumerate(indexed[date]):
                if wkdy == 6 or not organized[colors[i]]:
                    organized[colors[i]].append(0 if u is None else u)
                else:
                    organized[colors[i]][-1] += 0 if u is None else u
        else:
            for color in colors:
                if wkdy == 6 or not organized[color]:
                    organized[color].append(0)

    organized = {color: u for color, u in organized.items() if any(u)}
    colors = [c for c in colors if c in organized]
    colors.sort(key=step)
    colors.reverse()
    colors = [(c, c) if c[1:] not in COLORS else (c, COLORS[c[1:]]) for c in colors]

    labels = []
    start_date = ""
    max_val = 0
    rolling_sum = 0
    for i, date in enumerate(dates):
        if date[1] == 6 or i == len(dates) - 1:
            max_val = max([max_val, rolling_sum])
            rolling_sum = 0

            labels.append(f"{start_date} to {date[0]}")
        elif date[1] == 0:
            start_date = date[0]

        if date[0] in indexed:
            rolling_sum += sum([0 if v is None else v for v in indexed[date[0]]])

    return render_template(
        "usage.html", labels=labels, usage=organized, colors=colors, max=max_val * 1.1
    )


def step(hexrgb: str):
    hexrgb = hexrgb.lstrip("#")  # in case you have Web color specs
    r, g, b = (int(hexrgb[i : i + 2], 16) / 255.0 for i in range(0, 5, 2))
    lum = math.sqrt(0.241 * r + 0.691 * g + 0.068 * b)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)

    repetitions = 8
    h2 = int(h * repetitions)
    lum2 = int(lum * repetitions)
    v2 = int(v * repetitions)
    return (h2, lum, v2)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
