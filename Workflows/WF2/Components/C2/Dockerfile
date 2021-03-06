# https://stackoverflow.com/questions/32254497/create-keyspace-automatically-inside-docker-container-with-cassandra
# Code for this Dockerfile and entry-wrap.sh inspired by two of the answers in this stack overflow
FROM cassandra:latest

LABEL author="Carla Patricia Vazquez"
LABEL version="1.0.0"
LABEL maintainer="Carla Patricia Vazquez"
LABEL emai="cpv150030@utdallas.edu"
LABEL status="Development"

COPY ./src/schema.cql /opt/data/schema.cql

COPY ./src/entry-wrap.sh /entry-wrap.sh
RUN chmod a+x /entry-wrap.sh
ENTRYPOINT ["/entry-wrap.sh"]

COPY ./Pipfile Pipfile
COPY ./Pipfile.lock Pipfile.lock
COPY ./src/cass_wrapper.py cass_wrapper.py
COPY ./get-pip.py get-pip.py
COPY ./src/workflow-request.schema.json /src/workflow-request.schema.json

RUN python get-pip.py
RUN pip install pipenv
RUN pipenv install --system --deploy

# added health check to verify if cassandra is ready for connections
HEALTHCHECK --interval=5s --timeout=5s --start-period=10s --retries=3 \
    CMD cqlsh 127.0.0.1 || exit 1

CMD [ "cassandra", "-f"]