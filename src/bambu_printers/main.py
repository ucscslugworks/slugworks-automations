from src.bambu_printers.account import BambuAccount

from src.log import setup_logs
logger = setup_logs("bambu-printers")

a = BambuAccount("slugworks@ucsc.edu", logger)
print(a.get_devices())