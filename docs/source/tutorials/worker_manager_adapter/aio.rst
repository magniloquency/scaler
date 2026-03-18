All-in-One Entry Point (scaler_aio)
====================================

``scaler_aio`` boots the full Scaler stack — scheduler and one or more worker managers — from a single TOML
configuration file.

Usage
-----

.. code-block:: bash

    scaler_aio --config <file>

Each recognised section in the config file spawns a separate process. Unrecognised sections are ignored.
If no recognised sections are found, ``scaler_aio`` exits with an error.

Example Configuration
---------------------

.. code-block:: toml

    [scheduler]
    object_storage_address = "tcp://127.0.0.1:6379"
    logging_level = "INFO"
    policy_content = "allocate=even_load; scaling=vanilla"

    [native_worker_manager]
    max_task_concurrency = 4

With this file:

.. code-block:: bash

    scaler_aio --config stack.toml

This starts the scheduler and one native worker manager as separate processes.

Array-of-Tables (Multiple Managers of the Same Type)
------------------------------------------------------

Use the TOML ``[[section]]`` array-of-tables syntax to spawn multiple instances of the same adapter type:

.. code-block:: toml

    [scheduler]
    object_storage_address = "tcp://127.0.0.1:6379"

    [[native_worker_manager]]
    max_task_concurrency = 2

    [[native_worker_manager]]
    max_task_concurrency = 4

This spawns two native worker manager processes with different concurrency limits.

Recognised Section Names
-------------------------

The following section names are recognised:

.. list-table::
   :header-rows: 1

   * - TOML Section
     - Component started
   * - ``[scheduler]``
     - Scaler scheduler
   * - ``[native_worker_manager]``
     - Native (local subprocess) manager
   * - ``[symphony_worker_manager]``
     - IBM Symphony manager
   * - ``[ecs_worker_manager]``
     - AWS ECS manager
   * - ``[aws_hpc_worker_manager]``
     - AWS Batch manager
   * - ``[orb_worker_adapter]``
     - ORB (EC2) adapter
