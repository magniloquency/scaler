"""Tests for the capnp C extension: lazy deserialization, zero-copy buffer
semantics, union variant resolution, and error paths."""

import gc
import unittest

from scaler.protocol.capnp import Message, StateTask, TaskState


class TestCapnp(unittest.TestCase):
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

    def test_union_which_is_lazy(self):
        # _variant_name must not be pre-set on the shell at from_bytes time.
        # which() resolves from the live buffer on first call, consistent with
        # how field values work.
        from scaler.io.utility import serialize

        original = StateTask(state=TaskState.success, taskId=b"t", functionName=b"f", worker=b"w")
        msg = Message.from_bytes(serialize(original))
        self.assertFalse(hasattr(msg, "_variant_name"))
        self.assertEqual(msg.which(), "stateTask")
        self.assertTrue(hasattr(msg, "_variant_name"))

    def test_inactive_union_field_raises_attribute_error(self):
        # Accessing a union field that is not the active variant must raise
        # AttributeError.  This exercises the load_struct_field inner check
        # that replaced the redundant outer check in capnp_union_get_attr.
        from scaler.io.utility import serialize

        original = StateTask(state=TaskState.success, taskId=b"t", functionName=b"f", worker=b"w")
        msg = Message.from_bytes(serialize(original))
        self.assertEqual(msg.which(), "stateTask")
        with self.assertRaises(AttributeError):
            _ = msg.task


if __name__ == "__main__":
    unittest.main()
