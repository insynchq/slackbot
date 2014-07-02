import os
import time
from functools import wraps

import arrow
import redis
import requests
from flask import abort, Flask, jsonify, request

app = Flask(__name__)
app.config.from_object("config")
db = redis.StrictRedis(
  host=os.environ.get("REDIS_PORT_6379_TCP_ADDR"),
)

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


@app.route("/meals", methods=["POST"])
@slack_hook(dict(
  count="ilan,bilang,count,sino",
  lunch="lunch,l,tanghalian",
  merienda="merienda,m",
  dinner="dinner,d,hapunan",
  cancel="hindi,not",
))
def meals(events):
  day = arrow.now().ceil("day").timestamp

  if "count" in events:
    reply = ""
    for meal in "lunch", "merienda", "dinner":
      reply += "{}: {}\n".format(
        meal.capitalize(),
        db.scard(key(meal, day)),
      )
      names = [
        users[user_id]["profile"]["first_name"]
        for user_id in
        db.smembers(key(meal, day))
      ]
      for user_id in sorted(names):
        reply += "    - {}\n".format(
        )
    return jsonify(text=reply)

  user_id = request.form["user_id"]

  for meal in "lunch", "merienda", "dinner":
    if meal in events:
      if "cancel" in events:
        db.srem(key(meal, day), user_id)
      else:
        db.sadd(key(meal, day), user_id)

  return jsonify(text="")


if __name__ == "__main__":
  app.run(host="0.0.0.0")

