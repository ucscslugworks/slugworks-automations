# slugworks-id-cards

**IMPORTANT:** Please use a virtual environment to install the required packages. You can use the following commands to do so on a Linux system:

```bash
sudo apt install --upgrade python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-[device].txt
```
Where `[device]` is the device you are using (`control` or `reader`). Additionally, pip must be run as sudo for the `reader` devices so the NeoPixel library has the proper permissions to control the GPIO pins.

### NeoPixel Setup on Readers (Pi Zero)
(run from the `slugworks-access-cards` directory)
```bash
sudo apt install --upgrade python3-setuptools
source venv/bin/activate
cd ~
pip install --upgrade adafruit-python-shell
wget https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/master/raspi-blinka.py
sudo -E env PATH=$PATH python3 raspi-blinka.py
```
Then, cd (change directory) to the `slugworks-access-cards` directory and run the following command:
```bash
sudo python3 blinkatest.py
```
This should return a series of "ok!" messages. Next, run the following command to install and test the NeoPixel library:
```bash
sudo pip install --upgrade adafruit-circuitpython-neopixel
sudo python3 neopixeltest.py
```
This should light up the NeoPixels connected to the reader with a rainbow pattern. If this works, the NeoPixel library is set up correctly. (You may need to adjust the num_pixels and pixel_pin variables in the `neopixeltest.py` file to match the number of NeoPixels and the GPIO pin they are connected to.)

### Required JSON Files
- ID.json
```json
{
    "id": X
}
```
*"X" is the reader ID as used in the database Sheet, where 0 is the control device*
- token.json
  - Google login token, if this does not exist you will need an OAuth `credentials.json` from Google Cloud Console and a browser to authenticate the application. Run `python sheet.py` with the `credentials.json` file in the directory, and a browser window should open to ask for a Google login. Here, use an account with read/write access to the database Sheet. If running on a device with no GUI, create the token file on a different device with an available browser then copy it to the correct device.
