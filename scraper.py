import urllib.request
import time

def parse_avito():
    print("Parsing Avito hardware...")
    try:
        req = urllib.request.urlopen("https://avito.ru")
        print("Success:", req.getcode())
    except Exception as e:
        print("Error:", e)
    time.sleep(2)

if __name__ == "__main__":
    while True:
        parse_avito()
