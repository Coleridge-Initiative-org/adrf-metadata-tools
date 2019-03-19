###############
ADRF Metabase
###############

Tools for handling metadata associated with administrative data sets.

--------------
Requirements
--------------

- PostgreSQL 9.5

- Python 3.5

- See requirements.txt (``pip install -r requirements.txt``)

-----------------------
Prepare the database
-----------------------

Create superuser ``metaadmin`` and store credentials in ``.pgpass`` file.

Grant ``metaadmin`` login privilege.

Create schema ``metabase``.

Sample codes::

    CREATE ROLE metaadmin WITH LOGIN SUPERUSER;

    CREATE SCHEMA metabase;

------------------------
Run migration script
------------------------

Currently there is only one version of the database. You can create all the
tables by running::

    alembic upgrade head

To revert the migration, run::

    alembic downgrade base

-----------
Run Tests
-----------

Tests require `testing.postgresql <https://github.com/tk0miya/testing.postgresql>`_.

``pip install testing.postgresql``

Run tests with the following command under the root directory of the project::

    pytest tests/

----------
Build docs
----------

Under the ``./docs/`` directory, run::

    sphinx-apidoc -o source/ ../metabase --force --separate

    make html
    


---------------------
Optional Docker Usage
---------------------

Build the container
-------------------

Inside the home directory for the repo ``adrf-metabase``, run::

``docker build -t metabase .``

Enter built image
-----------------

Get the image id with ``docker image ls`` and run::

``docker run -it {image_id} /bin/bash``

Inside the container
--------------------

You will enter the running image as the root user. You may need to start the postgres server again.

``su postgres``
``service postgresql start``
``exit``

Then you will want to switch to the metabase-user (as you cannot run pytest as the root user)

``su metabase-user``
``cd /home/metabase-user/adrf-metabase``

Run the database create tables

``alembic upgrade head``

Then run the pytests

``pytest tests/``

If everything runs fine (alembic will not provide any output, pytests might have some warnings, but should not have errors), run ``example.py``

``python3 example.py``

You should see the output::

``data_table_id is 1 for table data.example``





