FROM ubuntu
RUN apt-get -y install python python-setuptools
RUN easy_install -U pip
RUN pip install Flask
RUN pip install requests
RUN pip install redis
RUN pip install arrow
RUN echo "Asia/Manila" > /etc/timezone
RUN dpkg-reconfigure -f noninteractive tzdata
WORKDIR /slackbot
CMD ["python", "app.py"]
