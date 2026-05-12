"""Verify that the capnp C extension deserializes without copying the input
buffer.  Lazy structs returned by from_bytes must read live from the original
bytes object, so mutations to a bytearray source are visible on first field
access."""

import gc
import unittest

from scaler.protocol.capnp import Message, StateTask, TaskState


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

    def test_lazy_struct_keeps_buffer_alive(self):
        # The lazy struct stores a memoryview of the source buffer as
        # _capnp_source, keeping the underlying bytes alive even after the
        # caller's reference is dropped.  Field access must still succeed.
        buf = bytearray(StateTask(state=TaskState.success, taskId=b"t", functionName=b"f", worker=b"w").to_bytes())
        st = StateTask.from_bytes(buf)
        del buf
        gc.collect()
        self.assertEqual(st.state, TaskState.success)

    def test_lazy_union_to_bytes_round_trips(self):
        # to_bytes() on a lazily-deserialized union (capnp_union_to_bytes path)
        # must produce a valid, re-deserializable payload identical to the
        # original wire bytes.
        from scaler.io.utility import deserialize, serialize

        original = StateTask(state=TaskState.success, taskId=b"task", functionName=b"func", worker=b"w")
        wire = serialize(original)
        lazy_msg = Message.from_bytes(wire)
        result = deserialize(lazy_msg.to_bytes())
        assert isinstance(result, StateTask)
        self.assertEqual(result.state, original.state)
        self.assertEqual(result.taskId, original.taskId)
        self.assertEqual(result.functionName, original.functionName)
        self.assertEqual(result.worker, original.worker)


if __name__ == "__main__":
    unittest.main()
