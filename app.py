import re
from functools import wraps

import arrow
import redis
import requests
from flask import abort, Flask, jsonify, request
from simpleflake import simpleflake

CHIKKA_API_URL = "https://post.chikka.com/smsapi/request"
DEFAULT_MEAL_USERS = set([
  "U025XRFHC",  # Marte
])
USER_PAT = re.compile("\<@([A-Z0-9]+)\>")

app = Flask(__name__)
app.config.from_object("config")
db = redis.StrictRedis(host="redis")

users = {
  user["id"]: user for user in requests.get(
    "https://slack.com/api/users.list",
    params=dict(token=app.config["SLACK_API_TOKEN"]),
  ).json()["members"]
}

channels = {
  channel["name"]: channel for channel in requests.get(
    "https://slack.com/api/channels.list",
    params=dict(token=app.config["SLACK_API_TOKEN"]),
  ).json()["channels"]
}


def key(*args):
  return ":".join(map(str, args))


def send_sms(mobile_number, message):
  requests.post(
    CHIKKA_API_URL,
    data=dict(
      message_type="SEND",
      mobile_number=mobile_number,
      shortcode=app.config["CHIKKA_SHORTCODE"],
      message_id=str(simpleflake()),
      message=message + '\n\n*',
      client_id=app.config["CHIKKA_CLIENT_ID"],
      secret_key=app.config["CHIKKA_SECRET_KEY"],
    )
  )


def slack_hook(mapping):
  def wrapper(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
      tokens = app.config["SLACK_TOKENS"]
      if request.form["token"] != tokens[f.__name__.upper()]:
        abort(403)

      words = []
      for word in request.form["text"].lower().split():
        words.append(re.sub("[^a-z0-9'_\-\+]", "", word))
      kwargs["words"] = words

      # Get events from triggers
      events = set()
      for event, keywords in mapping.items():
        if set(keywords.split(",")) & set(words):
          events.add(event)
      kwargs["events"] = events

      # Get tagged users
      kwargs["tagged_users"] = [
        users[user_id] for user_id in USER_PAT.findall(
          request.form["text"]
        )
      ]

      return f(*args, **kwargs)
    return wrapped
  return wrapper


@app.route("/report/<type>", methods=["POST"])
def report(type):
  day = arrow.now().floor("day")
  if day.weekday() > 3 and day.weekday() < 6:
    return jsonify(ok=True)
  weekday = arrow.locales.get_locale('en_us').day_name(
    day.replace(days=1).isoweekday()
  )
  timestamp = day.timestamp
  if type == "meals":
    message = "{}\n\n".format(weekday)
    for meal in "lunch", "merienda", "dinner":
      meal_users = db.smembers(key(meal, timestamp)) | DEFAULT_MEAL_USERS
      message += "{}: {}\n".format(
        meal.capitalize(),
        len(meal_users),
      )
    for mobile_number in app.config["MEALS_REPORT_NUMBERS"]:
      send_sms(mobile_number, message)
  return jsonify(ok=True)


@app.route("/meals", methods=["POST"])
@slack_hook(dict(
  count="ilan,bilang,count,sino",
  lunch="lunch,l,tanghalian",
  merienda="merienda,m",
  dinner="dinner,d,hapunan",
  cancel="hindi,not",
))
def meals(events, **kwargs):
  day = arrow.now().floor("day")
  weekday = arrow.locales.get_locale('en_us').day_name(
    day.replace(days=1).isoweekday()
  )
  timestamp = day.timestamp

  if "count" in events:
    reply = "*{}*\n\n".format(weekday)
    for meal in "lunch", "merienda", "dinner":
      meal_users = db.smembers(key(meal, timestamp)) | DEFAULT_MEAL_USERS
      reply += "{}: {}\n".format(
        meal.capitalize(),
        len(meal_users),
      )
      names = [
        users[user_id]["profile"]["first_name"]
        for user_id in meal_users if user_id in users
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


@app.route("/listahan", methods=["POST"])
@slack_hook(dict(
  owe="owe,owes,utang",
  self="sakin,me",
  others="ako,ko,i",
))
def listahan(words, events, tagged_users):
  amounts = []
  for word in words:
    try:
      amounts.append(float(word))
    except ValueError:
      pass

  user_id = request.form["user_id"]

  if not events:
    reply = ""
    for tagged_user in tagged_users:
      for amount in amounts:
        div_amount = amount / len(tagged_users)
        db.incrbyfloat(
          key("listahan", user_id, tagged_user["id"]),
          div_amount,
        )
        reply += "{}: {}\n".format(
          tagged_user["profile"]["first_name"],
          div_amount,
        )
    return jsonify(text=reply)

  if "owe" in events:

    if "self" in events:
      reply = ""
      for user in users.values():
        amount = db.get(key("listahan", user_id, user["id"]))
        if amount and float(amount):
          reply += "{} owes you {}\n".format(
            user["profile"]["first_name"],
            amount,
          )
      return jsonify(text=reply or "No one")

    if "others" in events:
      reply = ""
      for user in users.values():
        amount = db.get(key("listahan", user["id"], user_id))
        if amount and float(amount):
          reply += "You owe {} {}\n".format(
            user["profile"]["first_name"],
            amount,
          )
      return jsonify(text=reply or "No one")

  return jsonify(text="")


@app.route("/monito_monita", methods=["POST"])
@slack_hook(dict(
  set_number="number",
  draw="draw,bunot",
  send="send",
))
def monito_monita(words, events, **kwargs):
  if "set_number" in events:
    user_id = request.form["user_id"]
    number = None
    for word in words:
      try:
        if word.startswith("63"):
          number = int(word)
          break
      except ValueError:
        pass
    if number:
      db.set(
        key("monito_monita", "number", user_id),
        number,
      )
      return jsonify(text="Saved your number")

  if "draw" in events:
    pot = channels["monito_monita"]["members"]

    # Check numbers
    for user_id in pot:
      if not db.exists(
        key("monito_monita", "number", user_id)
      ):
        user = users[user_id]
        return jsonify(
          text="I don't have {}'s number yet".format(
            user["profile"]["first_name"],
          ),
        )

    # Clear previous draw
    db.delete(key("monito_monita"))

    # Draw
    for pair in [
      "{}:{}".format(
        user_id,
        pot[(i + 1) % len(pot)],
      ) for i, user_id in enumerate(pot)
    ]:
      db.sadd(key("monito_monita"), pair)

    return jsonify(text="Drawn!")

  if "send" in events:
    pairs = db.smembers(key("monito_monita"))
    if pairs:
      for pair in pairs:
        giver_id, givee_id = pair.split(":")
        givee = users[givee_id]
        mobile_number = db.get(
          key("monito_monita", "number", giver_id),
        )
        message = "Monito Monita\n\nYou drew {}!".format(
          givee["profile"]["first_name"],
        )
        send_sms(mobile_number, message)
      return jsonify(text="Sent!")

  return jsonify(text="")


if __name__ == "__main__":
  app.run(host="0.0.0.0")

