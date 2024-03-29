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
