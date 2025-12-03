.. _ray_compatibility:

Ray Compatibility Layer
=======================

Scaler is a lightweight distributed computation engine similar to Ray. Scaler supports many of the same concepts as Ray including
remote functions (known as tasks in Scaler), futures, cluster object storage, labels (known as capabilities in Scaler), and it comes with comparable monitoring tools.

Unlike Ray, Scaler supports both local clusters and also easily integrates with multiple cloud providers out of the box, including AWS EC2 and IBM Symphony,
with more providers planned for the future. You can view our `roadmap on GitHub <https://github.com/finos/opengris-scaler/discussions/333>`_
for details on upcoming cloud integrations.

Scaler provides a compatibility layer that allows developers familiar with the `Ray <https://www.ray.io/>`_ API to adopt Scaler with minimal code changes.

Quickstart
----------

To start using Scaler's Ray compatibility layer, ensure you have `opengris-scaler <https://pypi.org/project/opengris-scaler/>`_ installed in your Python environment.

Then import ``scaler.compat.ray`` in your application after importing ``ray`` and before using any Ray APIs.

This import patches the ``ray`` module, allowing you to use Ray's API as you normally would.

.. code-block:: python
   
    import ray
    import scaler.compat.ray

    # existing Ray app

This will start a new local scheduler and cluster combo. To use an existing cluster, pass the address of the scheduler to ``scaler_init()``:

.. code-block:: python

    import ray
    from scaler.compat.ray import scaler_init

    # connects to an existing cluster
    # when an address is provided, a local cluster is not started
    scaler_init(address="tcp://<scheduler-ip>:<scheduler-port>")

    # existing Ray app

You can also provide scheduler and cluster configuration options to ``scaler_init()`` to configure the locally created cluster:

.. code-block:: python

    import ray
    from scaler.compat.ray import scaler_init

    # overrides the number of workers in the implicitly-created local cluster (defaults to number of CPU cores)
    scaler_init(n_workers=5)

    # existing Ray app

A Note about the Actor Model
----------------------------

Ray supports a powerful actor model that allows for stateful computation. This is currently not supported by the Scaler, but is planned for a future release.

This documentation will be updated when actor support is added. For now please view our `roadmap on GitHub <https://github.com/finos/opengris-scaler/discussions/333>`_ for more details.

Decorating a class with ``@ray.remote`` will raise a ``NotImplementedError``.

Full Examples
-------------

See `the examples directory <https://github.com/finos/opengris-scaler/tree/main/examples>`_ for complete Scaler Ray compatibility layer examples including:
*   `ray_compat_local_cluster.py`: Demonstrates using the Scaler Ray compatibility layer with the implicitly-created local cluster.
*   `ray_compat_remote_cluster.py`: Demonstrates using the Scaler Ray compatibility layer with an existing remote cluster.

Supported APIs
--------------

The compatibility layer supports a subset of Ray Core's API.

Below is a comprehensive list of the supported APIs. Functions and classes not in this list 

Core API
~~~~~~~~

*   ``@ray.remote``: Only supports remote functions. Decorating a class with ``@ray.remote`` will raise a ``NotImplementedError``.
*   ``ray.shutdown()``
*   ``ray.is_initialized()``
*   ``ray.get()``
*   ``ray.put()``
*   ``ray.wait()``
*   ``ray.cancel()``

Ray Utilities (`ray.util`)
~~~~~~~~~~~~~~~~~~~~~~~~~~

*   ``ray.util.as_completed()``
*   ``ray.util.map_unordered()``

Unsupported APIs
~~~~~~~~~~~~~~~~

The following APIs are not supported by the Scaler Ray compatibility layer.

Some functions will be no-ops, while others will raise a ``NotImplementedError`` exception.
 
*   ``ray.init()``: No-op. Use ``scaler_init()`` from ``scaler.compat.ray`` instead.
*   ``ray.method()``: Raises ``NotImplementedError``.
*   ``ray.actor``: Raises ``NotImplementedError``.
*   ``ray.runtime_context``: Raises ``NotImplementedError``.
*   ``ray.cross_language``: Raises ``NotImplementedError``.
*   ``ray.get_actor()``: Raises ``NotImplementedError``.
*   ``ray.get_gpu_ids()``: Raises ``NotImplementedError``.
*   ``ray.get_runtime_context()``: Raises ``NotImplementedError``.
*   ``ray.kill()``: Raises ``NotImplementedError``.
