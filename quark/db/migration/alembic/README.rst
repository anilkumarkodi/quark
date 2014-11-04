Generic single-database configuration.

See http://alembic.readthedocs.org/en/latest/tutorial.html for more usage.


Examples:
=========

- Applying Migration Locally (using sqlite3)

.. code-block:: bash

    $ quark-db-manage --database-connection sqlite:////home/vagrant/dev/quark.db
        upgrade 1284c81cf727

    INFO  [alembic.migration] Context impl SQLiteImpl.                                    
    INFO  [alembic.migration] Will assume non-transactional DDL.                          
    INFO  [alembic.migration] Running upgrade 4358d1b8cc75 -> 1284c81cf727, 
    create lswitch and lswitch port orphaned tables


- Checking Current Version Locally After Migration

.. code-block:: bash

    $ quark-db-manage --database-connection sqlite:////home/vagrant/dev/quark.db
        current

    INFO  [alembic.migration] Context impl SQLiteImpl.
    INFO  [alembic.migration] Will assume non-transactional DDL.
    Current revision for sqlite:////home/vagrant/dev/quark.db: 
    4358d1b8cc75 -> 1284c81cf727 (head), 
    create lswitch and lswitch port orphaned tables


Using Neutron.conf
=================

If you prefer to use a `neutron.conf` instead of passing args it would look like this

.. code-block:: bash

    [database]
    connection=sqlite:///home/vagrant/dev/quark.db

and you would use it like so

.. code-block:: bash
    
    $ quark-db-manage --config-file /home/vagrant/dev/neutron.conf
        upgrade 1284c81cf727

    INFO  [alembic.migration] Context impl SQLiteImpl.                                    
    INFO  [alembic.migration] Will assume non-transactional DDL.                          
    INFO  [alembic.migration] Running upgrade 4358d1b8cc75 -> 1284c81cf727, 
    create lswitch and lswitch port orphaned tables

Database Migration version problem 

    -Create new version file and give the version number from alembic_version table
    example :
        revision = '1f71e54a85e7'
        down_revision = None
    And then in initial_version.py file down_revision should be set to version number from alembic_version table
    example:    
        revision = '1817eef6373c'
        down_revision = '1f71e54a85e7'
        
    then run migrations upgrats head 
        example:
            quark-db-manage --config-file /etc/neutron/neutron.conf upgrade HEAD

Workflow for creating a revision
================================

1. Modify quark/db/models.py with your added table/columns.
2. Run ``quark-db-manage ... upgrade head``.
3. Run ``quark-db-manage ... revision --autogenerate``.

