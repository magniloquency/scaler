Unified Worker Manager Entry Point
===================================

``scaler_worker_manager`` is a single command that replaces the individual per-adapter entry points
(``scaler_worker_manager_baremetal_native``, ``scaler_worker_manager_symphony``, etc.).

.. note::
    ``scaler_cluster`` is no longer available. Users should migrate to
    ``scaler_worker_manager native --mode fixed``.

Usage
-----

.. code-block:: bash

    scaler_worker_manager <subcommand> [options]

Available sub-commands: ``native``, ``symphony``, ``ecs``, ``hpc``, ``orb``.

The ``--config`` flag may appear before or after the sub-command name:

.. code-block:: bash

    scaler_worker_manager native --config cluster.toml tcp://127.0.0.1:8516
    scaler_worker_manager --config cluster.toml native tcp://127.0.0.1:8516

Sub-commands
------------

native
~~~~~~

Provisions workers as local subprocesses. Supports dynamic (default) and fixed-pool mode.

.. code-block:: bash

    # Dynamic mode (auto-scaling)
    scaler_worker_manager native tcp://127.0.0.1:8516 --max-task-concurrency 4

    # Fixed mode (pre-spawned workers)
    scaler_worker_manager native --mode fixed --max-task-concurrency 4 tcp://127.0.0.1:8516

    # Using a TOML config file
    scaler_worker_manager native tcp://127.0.0.1:8516 --config config.toml

See :doc:`native` for full parameter details.

symphony
~~~~~~~~

Integrates with IBM Spectrum Symphony.

.. code-block:: bash

    scaler_worker_manager symphony tcp://127.0.0.1:8516 \
        --service-name ScalerService \
        --base-concurrency 4

ecs
~~~

Provisions workers as AWS ECS Fargate tasks.

.. code-block:: bash

    scaler_worker_manager ecs tcp://127.0.0.1:8516 \
        --ecs-cluster my-cluster \
        --ecs-task-image my-image:latest \
        --aws-region us-east-1

hpc
~~~

Provisions workers via AWS Batch.

.. code-block:: bash

    scaler_worker_manager hpc tcp://127.0.0.1:8516 \
        --job-queue my-queue \
        --job-definition my-job-def \
        --s3-bucket my-bucket

See :doc:`aws_hpc/index` for full setup details.

orb
~~~

Provisions workers as AWS EC2 instances via ORB.

.. code-block:: bash

    scaler_worker_manager orb tcp://127.0.0.1:8516 \
        --image-id ami-0528819f94f4f5fa5 \
        --instance-type t3.medium

See :doc:`orb` for full parameter details.
