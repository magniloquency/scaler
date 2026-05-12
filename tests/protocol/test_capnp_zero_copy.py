"""Verify that the capnp C extension deserializes without copying the input
buffer.  Lazy structs returned by from_bytes must read live from the original
bytes object, so mutations to a bytearray source are visible on first field
access."""

import unittest

from scaler.protocol.capnp import StateTask, TaskState


class TestZeroCopyDeserialization(unittest.TestCase):
    def test_struct_from_bytes_reads_from_original_buffer(self):
        # Prove zero-copy: deserialize from a bytearray, mutate the buffer
        # before accessing any field, then verify the field reflects the
        # mutation.  A copying implementation would snapshot the data at
        # from_bytes time and ignore the later write.
        inactive_bytes = StateTask(state=TaskState.inactive, taskId=b"t", functionName=b"f", worker=b"w").to_bytes()
        success_bytes = StateTask(state=TaskState.success, taskId=b"t", functionName=b"f", worker=b"w").to_bytes()
        diff_indices = [
            i for i in range(min(len(inactive_bytes), len(success_bytes))) if inactive_bytes[i] != success_bytes[i]
        ]
        if len(diff_indices) != 1:
            self.skipTest("could not locate state ordinal byte")
        state_offset = diff_indices[0]
        success_ordinal = success_bytes[state_offset]

        buf = bytearray(inactive_bytes)
        st = StateTask.from_bytes(buf)

        buf[state_offset] = success_ordinal
        self.assertEqual(st.state, TaskState.success)


if __name__ == "__main__":
    unittest.main()
