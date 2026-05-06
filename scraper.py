import requests
import time
import bot

def parse_avito():
    print("Parsing Avito hardware with requests...")
    bot.send_message("Found new GPU!")
    time.sleep(5)

if __name__ == "__main__":
    parse_avito()
