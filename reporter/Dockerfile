FROM python:2-onbuild
RUN echo "Asia/Manila" > /etc/timezone
RUN dpkg-reconfigure -f noninteractive tzdata
CMD ["python", "reporter.py"]
