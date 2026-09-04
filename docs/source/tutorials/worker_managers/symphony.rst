IBM Spectrum Symphony Worker Manager
=====================================

The Symphony worker manager integrates Scaler with `IBM Spectrum Symphony <https://www.ibm.com/products/analytics-workload-management>`_, allowing Scaler to offload task execution to a Symphony cluster via the SOAM (Service-Oriented Architecture Middleware) API.

Quick Start
-----------

Prerequisites
~~~~~~~~~~~~~

* An IBM Spectrum Symphony cluster with a registered application and deployed service, which
  ``scripts/symphony/setup_application.py`` creates (see Step 2)
* A Symphony installation on the machine running the worker manager, which is where the ``soamapi`` Python API comes from
* Python 3.10 or 3.12, the versions both Scaler and Symphony 7.3.2 support (see the note in Step 1)
* Python packages: ``pip install opengris-scaler``
* Network connectivity between the machine running the worker manager and both the Scaler scheduler and the Symphony cluster

Step 1: Install Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Scaler comes from PyPI:

.. code-block:: bash

   pip install opengris-scaler

``soamapi`` does not. It is not published on PyPI: it ships with the Symphony product as bytecode, under
``$SOAM_HOME/$SOAM_VERSION/$BINARY_TYPE/lib64/pythonapi_<python-version>``. Put it on the path by sourcing the
Symphony environment, which sets both ``PYTHONPATH`` and ``LD_LIBRARY_PATH``:

.. code-block:: bash

   . $SOAM_HOME/conf/profile.soam

``LD_LIBRARY_PATH`` matters as much as ``PYTHONPATH``. The API is backed by shared libraries in the same ``lib64``
directory, so importing ``soamapi`` with only ``PYTHONPATH`` set fails with
``ImportError: libcom_platform_log4cxx_097_4.so.9: cannot open shared object file``.

``lib64`` holds one bytecode directory per interpreter rather than ``soamapi`` itself, so sourcing the profile
does not by itself make ``import soamapi`` work. Symphony's ``soamapiversion`` module selects the directory
matching the running interpreter, and the worker manager imports it for you. Check the setup the same way:

.. code-block:: bash

   python -c "import soamapiversion, soamapi"

.. note::

   **Supported Python versions.** Symphony compiles ``soamapi`` for specific interpreters, one
   ``pythonapi_<python-version>`` directory per version, and selects one by the running interpreter's minor version.
   Symphony 7.3.2 build 603035 ships Python 2.7, 3.4, 3.6, 3.8, 3.9, 3.10 and 3.12; earlier builds ship fewer. Scaler
   requires Python 3.10 or later, so the Symphony worker manager runs on **Python 3.10 or 3.12**.

   On any other version, including 3.11, 3.13 and 3.14, Symphony falls back to its Python 3.4 bytecode and the import
   fails with ``ImportError: bad magic number in 'soamapi'``. List what your own installation supports with:

   .. code-block:: bash

      ls -d $SOAM_HOME/$SOAM_VERSION/$BINARY_TYPE/lib64/pythonapi_*

Step 2: Create the Symphony Application
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The worker manager submits tasks to a Symphony application whose service runs cloudpickled callables. Create
both with the setup utility, on a host with the Symphony installation, passing the interpreter that will run
the service:

.. code-block:: bash

   python3 scripts/symphony/setup_application.py --python /path/to/python3.12

It packages and deploys the service, generates an application profile with the paths resolved, registers it,
and prints the registered applications. Add ``--dry-run`` to see the profile without changing the cluster, and
``--application``/``--service`` to use names other than ``PickleRunner``/``PickleRunnerService``.

The interpreter you name needs ``cloudpickle`` and a matching ``soamapi``; the utility checks both by running
it, and refuses rather than leaving the failure to appear later as unexplained task failures.

Step 3: Start the Scheduler
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   scaler_object_storage_server tcp://127.0.0.1:8517
   scaler_scheduler tcp://0.0.0.0:8516 --object-storage-address tcp://127.0.0.1:8517 \
       --policy-content "allocate=even_load; scaling=vanilla"


Step 4: Start the Symphony Worker Manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   scaler_worker_manager symphony tcp://<SCHEDULER_IP>:8516 \
       --worker-manager-id wm-symphony \
       --service-name PickleRunner \
       --max-task-concurrency 8

``--service-name`` takes the Symphony **application** name, not the service name. The worker manager passes it
to ``soamapi.connect()``, which connects to an application. With the application created by
``scripts/symphony/setup_application.py`` this is ``PickleRunner``, whose service is ``PickleRunnerService``.

Or use a TOML configuration file:

.. code-block:: bash

   scaler config.toml

.. code-block:: toml
   :caption: config.toml

   [object_storage_server]
   bind_address = "tcp://127.0.0.1:8517"

   [scheduler]
   bind_address = "tcp://0.0.0.0:8516"
   object_storage_address = "tcp://127.0.0.1:8517"

   [[worker_manager]]
   type = "symphony"
   scheduler_address = "tcp://<SCHEDULER_IP>:8516"
   worker_manager_id = "wm-symphony"
   service_name = "MyScalerService"
   max_task_concurrency = 8
   logging_level = "INFO"

Step 5: Submit Tasks
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from scaler import Client

   def compute(x):
       return x ** 2

   with Client(address="tcp://<SCHEDULER_IP>:8516") as client:
       results = client.map(compute, range(50))
       print(results)

``Client.map`` returns the results themselves. ``Client.submit`` is the one that returns a future:

.. code-block:: python

   future = client.submit(compute, 7)
   print(future.result())

How It Works
------------

1. The Symphony worker manager connects to the Scaler scheduler as a worker.
2. It establishes a SOAM connection and session to the configured Symphony service.
3. When the worker manager receives a task from the scheduler, it serializes the function and arguments with ``cloudpickle`` and submits them as a Symphony task via the SOAM API.
4. Symphony schedules the task on its compute hosts. On completion, the SOAM callback delivers the result back to the worker manager.
5. The worker manager deserializes the result and returns it to the Scaler scheduler.

The worker manager uses a concurrency semaphore to limit the number of tasks in flight.

Configuration Reference
------------------------

Symphony-Specific Parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``scheduler_address`` (positional, required): Address of the Scaler scheduler.
* ``--service-name`` (``-sn``, required): The name of the Symphony **application** to connect to. Despite the
  option name, this value reaches ``soamapi.connect()``, which takes an application rather than a service.
* ``--max-task-concurrency`` (``-mtc``): Maximum number of concurrent Symphony workers (default: number of CPUs − 1).

Common Parameters
~~~~~~~~~~~~~~~~~

For networking, worker behavior, logging, and event loop options, see :doc:`common_parameters`.
