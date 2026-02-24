import unittest
from db import process_inventory_batch


class InventoryTests(unittest.TestCase):

    def test_negative_inventory_blocked(self):
        items = [
            {"type": "key", "brand": "TestBrand", "number": "999", "quantity": -1000}
        ]

        result = process_inventory_batch(items, strict_mode=False)

        self.assertEqual(result["failed"], 1)


if __name__ == "__main__":
    unittest.main()
