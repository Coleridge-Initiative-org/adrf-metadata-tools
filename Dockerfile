from ubuntu:18.04


# Install the basics
RUN apt update
RUN apt install -y tree vim curl python3 python3-pip git

# add metabase-user user as we don't want to run everything as root
RUN useradd -ms /bin/bash metabase-user

# switch back to root user
USER root 

# clone the repo - for now we'll use the version with chapinhall as it's the most up-to-date
RUN git clone https://github.com/chapinhall/adrf-metabase /home/metabase-user/adrf-metabase

# Install requirements.txt
COPY ./requirements.txt /
RUN pip3 install -r /requirements.txt

# Install additional packages that will be needed for testing
RUN pip3 install testing.postgresql pytest pandas psycopg2-binary

# Set this so docker build doesn't hand on tzdata config https://askubuntu.com/questions/909277/avoiding-user-interaction-with-tzdata-when-installing-certbot-in-a-docker-contai
ENV DEBIAN_FRONTEND=noninteractive

# install postgres 9.5
# lifted and modified from https://docs.docker.com/engine/examples/postgresql_service/
RUN apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ precise-pgdg main" > /etc/apt/sources.list.d/pgdg.list
RUN apt-get update && apt-get install -y software-properties-common postgresql-9.5 postgresql-contrib-9.5 postgresql-client-9.5


# Switch to postgres user to add metabase admin and schema and data schema for example.py
USER postgres

RUN    /etc/init.d/postgresql start &&\
    psql --command "CREATE USER metaadmin with password 'imalittleteapot';" &&\
    psql --command "grant all privileges on database postgres to metaadmin;" &&\
    psql --command "alter user metaadmin with superuser;" &&\
    psql --command "create schema metabase;" &&\
    psql --command "create schema data;"

# Run service so it's up when we enter the interactive terminal (though this doesn't seem to work for now)
RUN service postgresql start


# Switch to metabase-user to set up the pgpass file for testing

USER metabase-user
WORKDIR /home/metabase-user
RUN echo "localhost:5432:postgres:metaadmin:imalittleteapot" > ~/.pgpass
RUN chmod 600 ~/.pgpass

# Switch back to root user so we can switch to postgres or metabase-user as needed
USER root
