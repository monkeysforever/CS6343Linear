FROM python:alpine3.11

LABEL author="Chris Scott"
LABEL version="1.0.0"
LABEL maintainer="Chris Scott"
LABEL email="cms190009@utdallas.edu"
LABEL status="Development"

ENV PYTHONBUFFERED 1
ENV PYTHONFAULTHANDLER 1

COPY . /app
WORKDIR /app

RUN pip install pipenv
RUN echo python3 --version
RUN pipenv install --system --deploy

EXPOSE 6000

ENV QUART_APP=src.order-processor:app

CMD quart run --port 6000 --host 0.0.0.0
