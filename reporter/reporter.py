import time

import requests
import schedule
import logging

logger = logging.getLogger("schedule")
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)


def report_meals():
  requests.post("http://slackbot:5000/report/meals")


if __name__ == "__main__":
  schedule.every().day.at("18:00").do(report_meals)
  while True:
    schedule.run_pending()
    time.sleep(10)

