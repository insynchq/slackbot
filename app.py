import os
import time
from functools import wraps

import arrow
import redis
from flask import abort, Flask, jsonify, request

app = Flask(__name__)
app.config.from_object("config")
db = redis.StrictRedis(
  host=os.environ.get("REDIS_PORT_6379_TCP_ADDR"),
)


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
      for event, keywords in mapping.items():
        words = set(request.form["text"].lower().split())
        if set(keywords.split(",")) & words:
          events.add(event)
      kwargs["events"] = events
      return f(*args, **kwargs)
    return wrapped
  return wrapper


@app.route("/meals", methods=["POST"])
@slack_hook(dict(
  count="ilan,bilang,count",
  lunch="lunch,l,tanghalian",
  merienda="merienda,m",
  dinner="dinner,d,hapunan",
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
    return jsonify(text=reply)

  user_id = request.form["user_id"]

  for meal in "lunch", "merienda", "dinner":
    if meal in events:
      db.sadd(key(meal, day), user_id)

  return jsonify(text="")


if __name__ == "__main__":
  app.run(host="0.0.0.0")

