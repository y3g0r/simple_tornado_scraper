FROM python:3.4

WORKDIR /app

RUN apt-get update && apt-get install -y mysql-client

COPY ./* ./
RUN pip install -r requirements.txt

EXPOSE 8888

CMD bash docker_entrypoint.sh

# docker run --name some-mysql -e MYSQL_ROOT_PASSWORD=password -d mysql:latest