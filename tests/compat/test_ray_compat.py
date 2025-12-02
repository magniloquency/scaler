import unittest

import numpy as np

from scaler.compat import ray


class TestRayCompat(unittest.TestCase):
    def test_basic(self) -> None:
        ray.init()

        @ray.remote
        def remote_fn() -> int:
            return 7

        ref = remote_fn.remote()

        self.assertEqual(ray.get(ref), 7)
        ray.shutdown()

    # https://docs.ray.io/en/latest/ray-core/walkthrough.html#running-a-task
    def test_ray_example_square(self) -> None:
        # Define the square task.
        @ray.remote
        def square(x):
            return x * x

        # Launch four parallel square tasks.
        futures = [square.remote(i) for i in range(4)]

        # Retrieve results.
        self.assertEqual(ray.get(futures), [0, 1, 4, 9])

        ray.shutdown()

    # https://docs.ray.io/en/latest/ray-core/walkthrough.html#passing-objects
    def test_ray_example_numpy(self) -> None:
        # Define a task that sums the values in a matrix.
        @ray.remote
        def sum_matrix(matrix):
            return np.sum(matrix)

        # Call the task with a literal argument value.
        print(ray.get(sum_matrix.remote(np.ones((100, 100)))))
        # -> 10000.0

        # Put a large array into the object store.
        matrix_ref = ray.put(np.ones((1000, 1000)))

        # Call the task with the object reference as an argument.
        self.assertEqual(ray.get(sum_matrix.remote(matrix_ref)), 1000000.0)

        ray.shutdown()
