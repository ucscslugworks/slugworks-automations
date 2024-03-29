# slugworks-id-cards

**IMPORTANT:** Please use a virtual environment to install the required packages. You can use the following commands to do so on a Linux system:

```bash
sudo apt install python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

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

# TODO:
- CAD an enclosure for the readers
- test the LEDs - make sure we can write colors to ~10cm of LEDs from the zero
  - red for not accepted, green for accepted
- split the microusb wire & solder the LEDs to the wire - cut the LEDs to size
- move canvas.py to use the users endpoint instead of students - check for staff and update the staff sheet
- canvas status sheet
  - last updated date/time
  - currently updating
- replace the student & staff card setup pages w/ one card setup page - the set_uid() function should automatically update in either the students or staff sheet depending on what the user is
- page to get info about the card currently scanning - name, cruzid, accesses
- add a login to all the pages
  - cached would be nice but less important
- network setup between control Pi & nick's optiplex over a usb-a to usb-a cable
- log UI
- "update all zeros" button if not already done
- "canvas update now" button - trigger update all devices when done

## low priority
- alarms - read status of magnet switch on a zero's gpio pins
- tag-out card for alarms
- secondary (or more) UIDs per user
  - possibly just treat each UID box as a list (in string form)?
  - list all UIDs in box, delimit with spaces or something
- turn the flask pages into json-endpoint-based, so that they auto refresh without reloading/change things about themselves
  - ex. overwrite checkbox only appears if an issue occurs that requires it (and error text appears automatically too)
    - ex. password comparison against security requirements
  - ex. no need to reload the dashboard, data will update automatically
- LED colors