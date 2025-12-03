import time
import unittest

import numpy as np
from numpy import random

from scaler.compat import ray


class TestRayCompat(unittest.TestCase):
    def tearDown(self):
        ray.shutdown()

    def test_basic(self) -> None:
        ray.init()

        @ray.remote
        def remote_fn() -> int:
            return 7

        ref = remote_fn.remote()

        self.assertEqual(ray.get(ref), 7)

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

    # https://docs.ray.io/en/latest/ray-core/patterns/nested-tasks.html#code-example
    def test_ray_example_nested(self) -> None:
        def partition(collection):
            # Use the last element as the pivot
            pivot = collection.pop()
            greater, lesser = [], []
            for element in collection:
                if element > pivot:
                    greater.append(element)
                else:
                    lesser.append(element)
            return lesser, pivot, greater

        def quick_sort(collection):
            if len(collection) <= 200000:  # magic number
                return sorted(collection)
            else:
                lesser, pivot, greater = partition(collection)
                lesser = quick_sort(lesser)
                greater = quick_sort(greater)
            return lesser + [pivot] + greater

        @ray.remote
        def quick_sort_distributed(collection):
            # Tiny tasks are an antipattern.
            # Thus, in our example we have a "magic number" to
            # toggle when distributed recursion should be used vs
            # when the sorting should be done in place. The rule
            # of thumb is that the duration of an individual task
            # should be at least 1 second.
            if len(collection) <= 200000:  # magic number
                return sorted(collection)
            else:
                lesser, pivot, greater = partition(collection)
                lesser = quick_sort_distributed.remote(lesser)
                greater = quick_sort_distributed.remote(greater)
                return ray.get(lesser) + [pivot] + ray.get(greater)

        for size in [200000, 4000000, 8000000]:
            unsorted = random.randint(1000000, size=(size)).tolist()
            s = time.time()
            sequential_sorted = quick_sort(unsorted[:])
            print(f"Sequential execution: {(time.time() - s):.3f}")
            s = time.time()
            distributed_sorted = ray.get(quick_sort_distributed.remote(unsorted))
            print(f"Distributed execution: {(time.time() - s):.3f}")
            print("--" * 10)

            print(len(sequential_sorted), len(distributed_sorted))

            self.assertEqual(
                sequential_sorted,
                distributed_sorted,
                msg=f"Expected sequential and distributed sorts to match for {size} element case",
            )

    def test_ray_passing_refs(self) -> None:
        @ray.remote
        def my_function() -> int:
            return 1

        @ray.remote
        def function_with_an_argument(value: int) -> int:
            return value + 1

        obj_ref1 = my_function.remote()
        self.assertEqual(ray.get(obj_ref1), 1)

        # You can pass an object ref as an argument to another Ray task.
        obj_ref2 = function_with_an_argument.remote(obj_ref1)
        self.assertEqual(ray.get(obj_ref2), 2)

    def test_ray_wait_timeout(self) -> None:
        @ray.remote
        def sleep(secs: int) -> None:
            time.sleep(secs)

        refs = [sleep.remote(x) for x in (2, 10)]
        ready, remaining = ray.wait(refs, timeout=5)

        self.assertEqual(ready, refs[:1])
        self.assertEqual(remaining, refs[1:])

    def test_ray_wait_no_timeout(self) -> None:
        @ray.remote
        def sleep(secs: int) -> None:
            time.sleep(secs)

        refs = [sleep.remote(x) for x in (2, 10)]
        ready, remaining = ray.wait(refs, num_returns=2, timeout=None)

        self.assertEqual(ready, refs)
        self.assertEqual(remaining, [])

    def test_ray_wait_num_returns(self) -> None:
        @ray.remote
        def sleep(secs: int) -> None:
            time.sleep(secs)

        refs = [sleep.remote(x) for x in (2, 10)]
        ready, remaining = ray.wait(refs, num_returns=1, timeout=None)

        self.assertEqual(ready, refs[:1])
        self.assertEqual(remaining, refs[1:])
