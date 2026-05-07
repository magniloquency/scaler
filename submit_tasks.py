import time
from scaler import Client


def slow_square(x: int) -> int:
    import time
    time.sleep(2)
    return x * x


def main() -> None:
    print("Connecting to scheduler at tcp://127.0.0.1:8516 ...")
    with Client(address="tcp://3.90.108.47:6788") as client:
        print("Connected. Submitting 8 tasks ...")
        futures = [client.submit(slow_square, i) for i in range(8)]
        print(f"Submitted {len(futures)} tasks. Waiting for results ...")

        results = [f.result() for f in futures]
        print(f"Results: {results}")
        assert results == [i * i for i in range(8)], "Unexpected results!"
        print("All results correct.")


if __name__ == "__main__":
    main()
