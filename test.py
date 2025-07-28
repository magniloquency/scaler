import sys, os

port = int(sys.argv[1])

import math
from scaler import Client

with Client(address=f"tcp://127.0.0.1:{port}") as client:
    # Submits 100 tasks
    futures = [
        (client.submit(math.sqrt, i), print(i))[0]
        for i in range(0, os.cpu_count() - 1)
    ]

    # Collects the results and sums them
    result = sum(future.result() for future in futures)

    print("!!!! THIS IS THE RESULT !!!!;;", result)  # 661.46

    # print(client.submit(math.sqrt, 2).result())
