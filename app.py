import os
import time
from functools import wraps

import arrow
import redis
import requests
from flask import abort, Flask, jsonify, request

SEMAPHORE_API_URL = "http://www.semaphore.co/api/sms"

app = Flask(__name__)
app.config.from_object("config")
db = redis.StrictRedis(host="redis")

users = dict()
for user in requests.get(
  "https://slack.com/api/users.list",
  params=dict(token=app.config["SLACK_API_TOKEN"]),
).json()["members"]:
  users[user["id"]] = user


def key(*args):
  return ":".join(map(str, args))


def slack_hook(mapping):
  def wrapper(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
      tokens = app.config["SLACK_TOKENS"]
      if request.form["token"] != tokens[f.__name__.upper()]:
        abort(403)
      events = set()
      words = set(request.form["text"].lower().split())
      for event, keywords in mapping.items():
        if set(keywords.split(",")) & words:
          events.add(event)
      kwargs["events"] = events
      return f(*args, **kwargs)
    return wrapped
  return wrapper


@app.route("/report/<type>", methods=["POST"])
def report(type):
  day = arrow.now().floor("day")
  if day.weekday() > 3 or day.weekday() < 6:
    return jsonify(ok=True)
  weekday = arrow.locales.get_locale('en_us').day_name(
    day.replace(days=1).isoweekday()
  )
  timestamp = day.timestamp
  if type == "meals":
    message = "{}\n\n".format(weekday)
    for meal in "lunch", "merienda", "dinner":
      message += "{}: {}\n".format(
        meal.capitalize(),
        db.scard(key(meal, timestamp)),
      )
    requests.post(
      SEMAPHORE_API_URL,
      data=dict(
        api=app.config["SEMAPHORE_API_TOKEN"],
        number=app.config["MEALS_REPORT_NUMBER"],
        message=message,
      )
    )
  return jsonify(ok=True)


@app.route("/meals", methods=["POST"])
@slack_hook(dict(
  count="ilan,bilang,count,sino",
  lunch="lunch,l,tanghalian",
  merienda="merienda,m",
  dinner="dinner,d,hapunan",
  cancel="hindi,not",
))
def meals(events):
  day = arrow.now().floor("day")
  weekday = arrow.locales.get_locale('en_us').day_name(
    day.replace(days=1).isoweekday()
  )
  timestamp = day.timestamp

  if "count" in events:
    reply = "*{}*\n\n".format(weekday)
    for meal in "lunch", "merienda", "dinner":
      reply += "{}: {}\n".format(
        meal.capitalize(),
        db.scard(key(meal, timestamp)),
      )
      names = [
        users[user_id]["profile"]["first_name"]
        for user_id in
        db.smembers(key(meal, timestamp))
      ]
      reply += "  {}\n".format(", ".join(sorted(names)))
    return jsonify(text=reply)

  user_id = request.form["user_id"]

  for meal in "lunch", "merienda", "dinner":
    if meal in events:
      if "cancel" in events:
        db.srem(key(meal, timestamp), user_id)
      else:
        db.sadd(key(meal, timestamp), user_id)

  return jsonify(text="")


if __name__ == "__main__":
  app.run(host="0.0.0.0")

