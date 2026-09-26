from __future__ import annotations

from decimal import Decimal

import pytest

from part2.cart import (
    LINE_PRODUCT_ID_INDEX,
    LINE_QUANTITY_INDEX,
    CartLine,
    add_to_cart,
    remove_from_cart,
)
from part2.crud import (
    create_product,
    delete_product,
    generate_product_id,
    read_product,
    update_product,
)
from part2.storage import (
    NAME_INDEX,
    PRICE_INDEX,
    PRODUCT_ID_INDEX,
    PRODUCT_ID_MIN,
    QUANTITY_INDEX,
    Product,
)
from part2.utils import PRICE_PRECISION, PRICE_STEP, normalize_price


def product(
    product_id: int,
    name: str,
    price: str = "10.00",
    quantity: int = 10,
) -> Product:
    return (
        product_id,
        name,
        normalize_price(Decimal(price)),
        quantity,
    )


# ============================================================
# storage — константы
# ============================================================


class TestStorageConstants:
    def test_indexes(self) -> None:
        assert PRODUCT_ID_INDEX == 0
        assert NAME_INDEX == 1
        assert PRICE_INDEX == 2
        assert QUANTITY_INDEX == 3

    def test_first_product_id(self) -> None:
        assert PRODUCT_ID_MIN == 1


# ============================================================
# utils — точность цены
# ============================================================


class TestPriceConstants:
    def test_precision(self) -> None:
        assert PRICE_PRECISION == 2

    def test_step_is_derived(self) -> None:
        assert PRICE_STEP == Decimal(1).scaleb(-PRICE_PRECISION)
        assert PRICE_STEP == Decimal("0.01")


class TestNormalizePrice:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("12.999", "13.00"),
            ("2.3451", "2.35"),
            ("2.3449", "2.34"),
            ("5", "5.00"),
            ("0.005", "0.01"),
            ("-2.345", "-2.35"),
        ],
    )
    def test_rounding(self, raw: str, expected: str) -> None:
        result = normalize_price(Decimal(raw))
        assert result == Decimal(expected)
        assert result.as_tuple().exponent == -PRICE_PRECISION

    def test_always_has_fixed_precision(self) -> None:
        result = normalize_price(Decimal(1))
        assert result == Decimal("1.00")
        assert result.as_tuple().exponent == -PRICE_PRECISION


# ============================================================
# crud — generate_product_id
# ============================================================


class TestGenerateProductId:
    def test_empty_storage(self) -> None:
        assert generate_product_id([]) == PRODUCT_ID_MIN

    def test_max_plus_one(self) -> None:
        storage = [
            product(1, "a", quantity=1),
            product(5, "b", quantity=1),
            product(3, "c", quantity=1),
        ]
        assert generate_product_id(storage) == 6


# ============================================================
# crud — create_product
# ============================================================


class TestCreateProduct:
    def test_success(self) -> None:
        storage: list[Product] = []
        product_id = create_product(
            storage,
            ("apple", Decimal("10.999"), 7),
        )

        assert product_id == PRODUCT_ID_MIN
        assert storage == [
            (PRODUCT_ID_MIN, "apple", Decimal("11.00"), 7),
        ]
        assert read_product(storage, product_id) == storage[0]

    def test_duplicate_name(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage = [product(1, "apple", quantity=1)]
        before = list(storage)

        result = create_product(
            storage,
            ("apple", Decimal(5), 1),
        )

        assert result is None
        assert storage == before

        out = capsys.readouterr().out
        assert "apple" in out
        assert "already taken" in out


# ============================================================
# crud — read_product
# ============================================================


class TestReadProduct:
    def test_existing(self) -> None:
        record = product(1, "apple", quantity=3)
        storage = [record]

        assert read_product(storage, 1) == record

    def test_missing(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage: list[Product] = []

        assert read_product(storage, 42) is None

        out = capsys.readouterr().out
        assert "42" in out
        assert "no product" in out


# ============================================================
# crud — update_product
# ============================================================


class TestUpdateProduct:
    def test_success(self) -> None:
        storage = [product(1, "apple", "10", 5)]

        updated = update_product(
            storage,
            1,
            ("pear", Decimal("12.345"), 9),
        )

        assert updated == (1, "pear", Decimal("12.35"), 9)
        assert storage == [updated]

    def test_missing(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage = [product(1, "apple", "10", 5)]
        before = list(storage)

        result = update_product(
            storage,
            99,
            ("pear", Decimal(1), 2),
        )

        assert result is None
        assert storage == before

        out = capsys.readouterr().out
        assert "99" in out
        assert "no product" in out


# ============================================================
# crud — delete_product
# ============================================================


class TestDeleteProduct:
    def test_success(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage = [product(1, "apple", "10", 5)]

        assert delete_product(storage, 1) == 1
        assert storage == []
        assert read_product(storage, 1) is None

        out = capsys.readouterr().out
        assert "1" in out
        assert "no product" in out

    def test_missing(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage = [product(1, "apple", "10", 5)]
        before = list(storage)

        assert delete_product(storage, 42) is None
        assert storage == before

        out = capsys.readouterr().out
        assert "42" in out
        assert "no product" in out


# ============================================================
# cart — add_to_cart
# ============================================================


class TestAddToCart:
    def test_new_line(self) -> None:
        storage = [product(1, "apple", "10", 5)]
        cart: list[CartLine] = []

        line = add_to_cart(storage, cart, 1, 3)

        assert line == (1, 3)
        assert cart == [(1, 3)]
        assert cart[0][LINE_PRODUCT_ID_INDEX] == 1
        assert cart[0][LINE_QUANTITY_INDEX] == 3
        assert storage[0][QUANTITY_INDEX] == 2
        assert storage[0][PRICE_INDEX] == Decimal("10.00")
        assert storage[0][NAME_INDEX] == "apple"

    def test_existing_line(self) -> None:
        storage = [product(1, "apple", "10", 5)]
        cart: list[CartLine] = [(1, 1)]

        line = add_to_cart(storage, cart, 1, 2)

        assert line == (1, 3)
        assert cart == [(1, 3)]
        assert storage[0][QUANTITY_INDEX] == 3

    def test_all_stock_is_allowed(self) -> None:
        storage = [product(1, "apple", "10", 3)]
        cart: list[CartLine] = []

        line = add_to_cart(storage, cart, 1, 3)

        assert line == (1, 3)
        assert storage[0][QUANTITY_INDEX] == 0

    def test_missing_product(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage: list[Product] = []
        cart: list[CartLine] = []

        assert add_to_cart(storage, cart, 42, 1) is None
        assert storage == []
        assert cart == []

        out = capsys.readouterr().out
        assert "42" in out
        assert "no product" in out

    def test_not_enough_stock(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage = [product(1, "apple", "10", 2)]
        cart: list[CartLine] = []
        before = list(storage)

        assert add_to_cart(storage, cart, 1, 3) is None
        assert storage == before
        assert cart == []

        out = capsys.readouterr().out
        assert "not enough stock" in out
        assert "2 available" in out
        assert "3 requested" in out


# ============================================================
# cart — remove_from_cart
# ============================================================


class TestRemoveFromCart:
    def test_partial_remove(self) -> None:
        storage = [product(1, "apple", "10", 2)]
        cart: list[CartLine] = [(1, 5)]

        line = remove_from_cart(storage, cart, 1, 3)

        assert line == (1, 2)
        assert cart == [(1, 2)]
        assert storage[0][QUANTITY_INDEX] == 5

    def test_full_remove_deletes_line(self) -> None:
        storage = [product(1, "apple", "10", 2)]
        cart: list[CartLine] = [(1, 4)]

        line = remove_from_cart(storage, cart, 1, 4)

        assert line == (1, 0)
        assert cart == []
        assert storage[0][QUANTITY_INDEX] == 6

    def test_not_in_cart(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage = [product(1, "apple", "10", 2)]
        cart: list[CartLine] = []
        before = list(storage)

        assert remove_from_cart(storage, cart, 1, 1) is None
        assert storage == before
        assert cart == []

        out = capsys.readouterr().out
        assert "1" in out
        assert "not in the cart" in out

    def test_not_enough_in_cart(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage = [product(1, "apple", "10", 2)]
        cart: list[CartLine] = [(1, 1)]
        before = list(storage)

        assert remove_from_cart(storage, cart, 1, 2) is None
        assert storage == before
        assert cart == [(1, 1)]

        out = capsys.readouterr().out
        assert "cart holds only 1" in out
        assert "cannot remove 2" in out

    def test_product_missing_in_storage(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        storage: list[Product] = []
        cart: list[CartLine] = [(42, 3)]
        before = list(cart)

        assert remove_from_cart(storage, cart, 42, 1) is None
        assert storage == []
        assert cart == before

        out = capsys.readouterr().out
        assert "42" in out
        assert "no product" in out


# ============================================================
# Инварианты
# ============================================================


class TestInvariants:
    def test_create_then_read(self) -> None:
        storage: list[Product] = []
        product_id = create_product(
            storage,
            ("apple", Decimal("10.999"), 5),
        )

        assert product_id is not None
        assert read_product(storage, product_id) == (
            product_id,
            "apple",
            normalize_price(Decimal("10.999")),
            5,
        )

    def test_delete_then_read_is_none(self) -> None:
        storage = [product(1, "apple", "10", 5)]

        assert delete_product(storage, 1) == 1
        assert read_product(storage, 1) is None

    def test_add_then_remove_restores_state(self) -> None:
        storage = [product(1, "apple", "10", 5)]
        cart: list[CartLine] = []
        initial_storage = list(storage)
        initial_cart = list(cart)

        assert add_to_cart(storage, cart, 1, 3) == (1, 3)
        assert remove_from_cart(storage, cart, 1, 3) == (1, 0)

        assert storage == initial_storage
        assert cart == initial_cart

    def test_quantity_conserved_on_add(self) -> None:
        storage = [product(1, "apple", "10", 5)]
        cart: list[CartLine] = []
        total_before = storage[0][QUANTITY_INDEX]

        add_to_cart(storage, cart, 1, 3)

        total_after = storage[0][QUANTITY_INDEX] + cart[0][LINE_QUANTITY_INDEX]
        assert total_after == total_before

    def test_quantity_conserved_on_remove(self) -> None:
        storage = [product(1, "apple", "10", 2)]
        cart: list[CartLine] = [(1, 5)]
        total_before = storage[0][QUANTITY_INDEX] + cart[0][LINE_QUANTITY_INDEX]

        remove_from_cart(storage, cart, 1, 3)

        total_after = storage[0][QUANTITY_INDEX] + cart[0][LINE_QUANTITY_INDEX]
        assert total_after == total_before
