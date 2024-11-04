FROM python:3.12-alpine

ADD . /home

WORKDIR /home

RUN pip install -r requirements.txt

CMD ["python", "./main.py"]
