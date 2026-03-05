Native Worker Adapter
=====================

The Native worker adapter provisions workers as local subprocesses on the same machine where the adapter is running. It supports both dynamic auto-scaling (default) and fixed-pool mode, where a set number of workers are pre-spawned at startup.

Getting Started
---------------

To start the Native worker adapter, use the ``scaler_worker_adapter_native`` command.

Example command:

.. code-block:: bash

    scaler_worker_adapter_native tcp://<SCHEDULER_IP>:8516 \
        --max-workers 4 \
        --logging-level INFO \
        --task-timeout-seconds 60

Equivalent configuration using a TOML file:

.. code-block:: bash

    scaler_worker_adapter_native tcp://<SCHEDULER_IP>:8516 --config config.toml

.. code-block:: toml

    # config.toml

    [native_worker_adapter]
    max_workers = 4
    logging_level = "INFO"
    task_timeout_seconds = 60

*   ``tcp://<SCHEDULER_IP>:8516`` is the address workers will use to connect to the scheduler.
*   The adapter can spawn up to 4 worker subprocesses in dynamic mode.

To use fixed-pool mode, set ``--mode fixed`` and specify the exact number of workers:

.. code-block:: toml

    # config.toml

    [native_worker_adapter]
    mode = "fixed"
    max_workers = 8

How it Works
------------

**Dynamic mode** (default): when the scheduler determines that more capacity is needed, it sends a request to the Native worker adapter. The adapter then spawns a new worker process using the same Python interpreter and environment that started the adapter. Each worker group managed by the Native adapter contains exactly one worker process.

**Fixed mode**: all workers are pre-spawned at startup. The adapter advertises zero capacity to the scheduler so it never receives dynamic scale commands. When all pre-spawned workers have exited, the adapter itself exits.

Supported Parameters
--------------------

.. note::
    For more details on how to configure Scaler, see the :doc:`../configuration` section.

The Native worker adapter supports the following specific configuration parameters in addition to the common worker adapter parameters.

Native Configuration
~~~~~~~~~~~~~~~~~~~~

*   ``--mode``: Operating mode. ``dynamic`` (default) enables auto-scaling driven by the scheduler.
    ``fixed`` pre-spawns ``--max-workers`` workers at startup and does not support dynamic scaling.
    In fixed mode ``--max-workers`` must be a positive integer.
*   ``--max-workers`` (``-mw``): In dynamic mode, the maximum number of worker subprocesses that can be started (``-1`` = unlimited, default: ``-1``). In fixed mode, the exact number of workers spawned at startup (must be ≥ 1).
*   ``--preload``: Python module or script to preload in each worker process before it starts accepting tasks.
*   ``--worker-io-threads`` (``-wit``): Number of IO threads for the IO backend per worker (default: ``1``).

Common Parameters
~~~~~~~~~~~~~~~~~

For a full list of common parameters including networking, worker configuration, and logging, see :doc:`common_parameters`.
