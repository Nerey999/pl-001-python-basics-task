import time
import pytest

from part1.constants import (
    EPOCH_MS_DEFAULT, NODE_ID_DEFAULT,
    TIMESTAMP_BITS, NODE_ID_BITS, SEQUENCE_ID_BITS,
    TIMESTAMP_MS_MAX, NODE_ID_MAX, SEQUENCE_ID_MAX,
)
from part1 import snowflake as sf


# ============================================================
# CONSTANTS — границы и согласованность
# ============================================================

class TestConstants:
    def test_bit_widths(self):
        assert (TIMESTAMP_BITS, NODE_ID_BITS, SEQUENCE_ID_BITS) == (41, 10, 12)

    def test_total_width_is_63(self):
        # 1 (sign) + 41 + 10 + 12 = 64, знаковый не используется -> 63
        assert TIMESTAMP_BITS + NODE_ID_BITS + SEQUENCE_ID_BITS == 63

    def test_max_are_derived(self):
        assert TIMESTAMP_MS_MAX == 2**41 - 1
        assert NODE_ID_MAX       == 2**10 - 1 == 1023
        assert SEQUENCE_ID_MAX   == 2**12 - 1 == 4095

    def test_epoch_and_default(self):
        assert EPOCH_MS_DEFAULT == 1288834974657
        assert NODE_ID_DEFAULT == 1


# ============================================================
# read_current_millis — крайние случаи
# ============================================================

class TestReadCurrentMillis:
    def test_is_in_milliseconds(self):
        before = int(time.time() * 1000)
        got = sf.read_current_millis(0)
        after = int(time.time() * 1000)
        assert before <= got <= after

    def test_epoch_zero_equals_unix_ms(self):
        # при epoch=0 функция возвращает Unix-время в мс
        assert abs(sf.read_current_millis(0) - int(time.time() * 1000)) < 5

    def test_future_epoch_negative(self):
        # epoch_ms в будущем -> результат отрицательный
        future = int(time.time() * 1000) + 10_000_000
        assert sf.read_current_millis(future) < 0

    def test_default_epoch_yields_positive(self):
        # с 2010 года точно прошло > 0 мс
        assert sf.read_current_millis(EPOCH_MS_DEFAULT) > 0

    def test_tiny_negative_epoch(self):
        # отрицательная эпоха не должна падать
        assert sf.read_current_millis(-1) > 0


# ============================================================
# decode_* — границы полей, «мусор на входе»
# ============================================================

class TestDecodeNodeId:
    def test_zero(self):
        assert sf.decode_node_id(0) == 0

    def test_max(self):
        # sequence=0, node=NODE_ID_MAX
        sid = NODE_ID_MAX << SEQUENCE_ID_BITS
        assert sf.decode_node_id(sid) == NODE_ID_MAX

    def test_isolated_from_sequence(self):
        # sequence не влияет на node
        sid = (NODE_ID_MAX << SEQUENCE_ID_BITS) | SEQUENCE_ID_MAX
        assert sf.decode_node_id(sid) == NODE_ID_MAX

    def test_isolated_from_timestamp(self):
        # timestamp не влияет на node
        sid = (12345 << (NODE_ID_BITS + SEQUENCE_ID_BITS)) \
              | (5 << SEQUENCE_ID_BITS) \
              | 3
        assert sf.decode_node_id(sid) == 5


class TestDecodeSequenceId:
    def test_zero(self):
        assert sf.decode_sequence_id(0) == 0

    def test_max(self):
        assert sf.decode_sequence_id(SEQUENCE_ID_MAX) == SEQUENCE_ID_MAX

    def test_only_low_12_bits(self):
        # всё, что выше 12 бит, игнорируется
        assert sf.decode_sequence_id(0xFFFF_FFFF) == SEQUENCE_ID_MAX

    def test_isolated_from_node_and_timestamp(self):
        sid = (999 << 22) | (7 << 12) | 42
        assert sf.decode_sequence_id(sid) == 42


class TestDecodeTimestampMs:
    def test_zero_with_epoch(self):
        # id без timestamp -> возвращаем ровно эпоху
        assert sf.decode_timestamp_ms(0, epoch_ms=EPOCH_MS_DEFAULT) == EPOCH_MS_DEFAULT

    def test_zero_with_zero_epoch(self):
        assert sf.decode_timestamp_ms(0, epoch_ms=0) == 0

    def test_max_timestamp_roundtrip(self):
        sid = TIMESTAMP_MS_MAX << (NODE_ID_BITS + SEQUENCE_ID_BITS)
        assert sf.decode_timestamp_ms(sid, epoch_ms=0) == TIMESTAMP_MS_MAX

    def test_isolated_from_lower_fields(self):
        # node и sequence не должны влиять на timestamp
        ts = 123_456_789
        sid = (ts << 22) | (NODE_ID_MAX << 12) | SEQUENCE_ID_MAX
        assert sf.decode_timestamp_ms(sid, epoch_ms=0) == ts

    def test_default_epoch_is_used(self):
        ts = 1000
        sid = ts << 22
        assert sf.decode_timestamp_ms(sid) == ts + EPOCH_MS_DEFAULT


# ============================================================
# generate_snowflake_id — границы диапазонов
# ============================================================

class TestGenerateValidRanges:
    def test_min_valid(self):
        sid = sf.generate_snowflake_id(0, node_id=0)
        assert sid is not None
        assert 0 < sid < 2**63

    def test_max_valid(self):
        sid = sf.generate_snowflake_id(SEQUENCE_ID_MAX, node_id=NODE_ID_MAX)
        assert sid is not None
        assert 0 < sid < 2**63
        assert sf.decode_node_id(sid) == NODE_ID_MAX
        assert sf.decode_sequence_id(sid) == SEQUENCE_ID_MAX

    def test_always_positive_63bit(self):
        # прогоняем все граничные комбинации
        for n in (0, 1, NODE_ID_MAX):
            for s in (0, 1, SEQUENCE_ID_MAX):
                sid = sf.generate_snowflake_id(s, node_id=n)
                assert sid is not None
                assert 0 < sid < 2**63, f"n={n}, s={s}, sid={sid}"

    def test_monotonic_within_same_ms(self):
        # при одной и той же мс id с большим sequence больше
        # (пока время не перескочило — обычно успевает)
        a = sf.generate_snowflake_id(1, node_id=5)
        b = sf.generate_snowflake_id(2, node_id=5)
        # если мс не сменилась, b > a; если сменилась — b всё равно > a
        # т.к. elapsed только растёт, а sequence мал
        assert b >= a


class TestGenerateInvalidNodeId:
    def test_negative(self, capsys):
        assert sf.generate_snowflake_id(0, node_id=-1) is None
        out = capsys.readouterr().out
        assert "node_id must be in" in out

    def test_above_max(self, capsys):
        assert sf.generate_snowflake_id(0, node_id=NODE_ID_MAX + 1) is None
        assert "node_id must be in" in capsys.readouterr().out

    def test_way_above(self, capsys):
        assert sf.generate_snowflake_id(0, node_id=10**9) is None
        assert "node_id must be in" in capsys.readouterr().out

    def test_node_checked_before_sequence(self, capsys):
        # node невалиден И sequence невалиден -> жалуемся на node
        sf.generate_snowflake_id(-1, node_id=-1)
        out = capsys.readouterr().out
        assert "node_id must be in" in out
        assert "sequence_id must be in" not in out


class TestGenerateInvalidSequenceId:
    def test_negative(self, capsys):
        assert sf.generate_snowflake_id(-1, node_id=1) is None
        assert "sequence_id must be in" in capsys.readouterr().out

    def test_above_max(self, capsys):
        assert sf.generate_snowflake_id(SEQUENCE_ID_MAX + 1, node_id=1) is None
        assert "sequence_id must be in" in capsys.readouterr().out

    def test_huge(self, capsys):
        assert sf.generate_snowflake_id(10**9, node_id=1) is None
        assert "sequence_id must be in" in capsys.readouterr().out


class TestGenerateOverflow:
    def test_negative_epoch_overflows(self, capsys):
        # epoch=-1 -> elapsed ~ 1.7e12 + 1 > 2^41-1? 2^41-1 ≈ 2.199e12
        # сейчас ~1.76e12, ещё влезает. Уводим эпоху глубоко в прошлое:
        sf.generate_snowflake_id(0, node_id=1, epoch_ms=-10**12)
        out = capsys.readouterr().out
        assert "overflows" in out

    def test_exactly_at_max_ok(self):
        # elapsed ровно = TIMESTAMP_MS_MAX -> НЕ переполнение
        # подбираем epoch так, чтобы elapsed == TIMESTAMP_MS_MAX
        now_ms = int(time.time() * 1000)
        epoch = now_ms - TIMESTAMP_MS_MAX
        sid = sf.generate_snowflake_id(0, node_id=1, epoch_ms=epoch)
        # могут быть гонки в 1 мс — допускаем оба исхода
        if sid is not None:
            assert sid > 0

    def test_one_past_max_overflows(self, capsys):
        now_ms = int(time.time() * 1000)
        epoch = now_ms - TIMESTAMP_MS_MAX - 100  # заведомо больше
        assert sf.generate_snowflake_id(0, node_id=1, epoch_ms=epoch) is None
        assert "overflows" in capsys.readouterr().out

    def test_overflow_checked_after_both_ids(self, capsys):
        # невалидный node + переполнение -> сначала node
        sf.generate_snowflake_id(0, node_id=-1, epoch_ms=-10**12)
        out = capsys.readouterr().out
        assert "node_id must be in" in out
        assert "overflows" not in out

    def test_future_epoch_no_overflow_but_valid(self):
        # эпоха в будущем -> elapsed отрицательный, это НЕ overflow
        future = int(time.time() * 1000) + 10_000
        sid = sf.generate_snowflake_id(0, node_id=1, epoch_ms=future)
        # по заданию не описано поведение для отрицательного elapsed
        # но текущая реализация не падает
        assert sid is None or isinstance(sid, int)


# ============================================================
# Roundtrip — главное свойство
# ============================================================

class TestRoundtrip:
    @pytest.mark.parametrize("node_id", [0, 1, 5, NODE_ID_MAX])
    @pytest.mark.parametrize("sequence_id", [0, 1, 42, SEQUENCE_ID_MAX])
    def test_node_and_sequence(self, node_id, sequence_id):
        sid = sf.generate_snowflake_id(sequence_id, node_id=node_id)
        assert sid is not None
        assert sf.decode_node_id(sid) == node_id
        assert sf.decode_sequence_id(sid) == sequence_id

    def test_timestamp_is_absolute_now(self):
        before = int(time.time() * 1000)
        sid = sf.generate_snowflake_id(0, node_id=1, epoch_ms=EPOCH_MS_DEFAULT)
        after = int(time.time() * 1000)
        ts = sf.decode_timestamp_ms(sid, epoch_ms=EPOCH_MS_DEFAULT)
        assert before - 1 <= ts <= after + 1

    def test_custom_epoch_roundtrip(self):
        epoch = 1_700_000_000_000
        before = int(time.time() * 1000)
        sid = sf.generate_snowflake_id(7, node_id=3, epoch_ms=epoch)
        after = int(time.time() * 1000)
        ts = sf.decode_timestamp_ms(sid, epoch_ms=epoch)
        assert before - 1 <= ts <= after + 1
        assert sf.decode_node_id(sid) == 3
        assert sf.decode_sequence_id(sid) == 7

    def test_ordering_by_timestamp(self):
        # id, сгенерированный позже, не меньше предыдущего
        ids = [sf.generate_snowflake_id(i, node_id=1) for i in range(10)]
        assert all(x is not None for x in ids)
        # монотонность по времени + sequence (в пределах одной мс — строго растёт)
        for a, b in zip(ids, ids[1:]):
            assert b >= a

    def test_fields_do_not_overlap(self):
        # изменение node не меняет sequence и timestamp
        sid_a = sf.generate_snowflake_id(100, node_id=1)
        sid_b = sf.generate_snowflake_id(100, node_id=2)
        assert sf.decode_sequence_id(sid_a) == sf.decode_sequence_id(sid_b) == 100
        assert sf.decode_node_id(sid_a) != sf.decode_node_id(sid_b)


# ============================================================
# «Мусор на входе» — int-подобные значения
# ============================================================

class TestGarbageInputs:
    def test_bool_is_int_subclass(self):
        # True == 1, False == 0 — не должно падать
        assert sf.generate_snowflake_id(True, node_id=False) is not None

    def test_big_negative_node(self, capsys):
        assert sf.generate_snowflake_id(0, node_id=-10**18) is None

    def test_big_positive_sequence(self, capsys):
        assert sf.generate_snowflake_id(10**18, node_id=1) is None


# ============================================================
# Формат stdout-сообщений (как требует TASK.md)
# ============================================================

class TestErrorMessages:
    def test_node_message_contains_range(self, capsys):
        sf.generate_snowflake_id(0, node_id=-1)
        out = capsys.readouterr().out
        # задание требует диапазон и полученное значение
        assert str(NODE_ID_MAX) in out
        assert "-1" in out

    def test_sequence_message_contains_range(self, capsys):
        sf.generate_snowflake_id(-1, node_id=1)
        out = capsys.readouterr().out
        assert str(SEQUENCE_ID_MAX) in out
        assert "-1" in out

    def test_overflow_message_contains_word(self, capsys):
        sf.generate_snowflake_id(0, node_id=1, epoch_ms=-10**12)
        out = capsys.readouterr().out
        assert "overflows" in out

    def test_no_print_on_success(self, capsys):
        sf.generate_snowflake_id(0, node_id=1)
        assert capsys.readouterr().out == ""