import csv
import os
import re
from typing import List, Dict, Any, Optional

CITY_ALIASES = {
    "trivandrum": "Thiruvananthapuram",
    "thiruvananthapuram": "Thiruvananthapuram",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "cochin": "Kochi",
    "kochi": "Kochi",
    "chennai": "Chennai",
    "madras": "Chennai",
    "pune": "Pune",
    "hyderabad": "Hyderabad"
}

class OrderDataset:
    def __init__(self, csv_path: Optional[str] = None):
        if csv_path is None:
            # Check data/orders.csv first, then orders.csv
            if os.path.exists("data/orders.csv"):
                csv_path = "data/orders.csv"
            elif os.path.exists("orders.csv"):
                csv_path = "orders.csv"
            else:
                csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "orders.csv")

        self.csv_path = csv_path
        self.orders: List[Dict[str, Any]] = []
        self.load_data()

    def load_data(self):
        self.orders = []
        if not os.path.exists(self.csv_path):
            return
        with open(self.csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                order = {
                    "order_id": row["order_id"].strip().upper(),
                    "order_date": row["order_date"].strip(),
                    "customer_name": row["customer_name"].strip(),
                    "city": row["city"].strip(),
                    "product": row["product"].strip(),
                    "category": row["category"].strip(),
                    "quantity": int(row["quantity"]),
                    "unit_price_inr": int(row["unit_price_inr"]),
                    "total_inr": int(row["total_inr"]),
                    "payment_method": row["payment_method"].strip(),
                    "status": row["status"].strip().lower()
                }
                self.orders.append(order)

    def normalize_city(self, city_input: str) -> str:
        if not city_input:
            return city_input
        lowered = city_input.strip().lower()
        return CITY_ALIASES.get(lowered, city_input.strip())

    def normalize_order_id(self, order_id_input: str) -> str:
        if not order_id_input:
            return order_id_input
        cleaned = order_id_input.strip().upper()
        # "1025" -> "ORD-1025", "ORD 1025" -> "ORD-1025"
        match = re.search(r"(\d{4})", cleaned)
        if match:
            return f"ORD-{match.group(1)}"
        return cleaned

    def get_dataset_info(self) -> Dict[str, Any]:
        if not self.orders:
            return {
                "ok": True,
                "total_orders": 0,
                "date_range": {"min": None, "max": None},
                "customers": [],
                "cities": [],
                "products": [],
                "categories": [],
                "statuses": [],
                "payment_methods": []
            }
        dates = [o["order_date"] for o in self.orders]
        customers = sorted(list(set(o["customer_name"] for o in self.orders)))
        cities = sorted(list(set(o["city"] for o in self.orders)))
        products = sorted(list(set(o["product"] for o in self.orders)))
        categories = sorted(list(set(o["category"] for o in self.orders)))
        statuses = sorted(list(set(o["status"] for o in self.orders)))
        payment_methods = sorted(list(set(o["payment_method"] for o in self.orders)))

        return {
            "ok": True,
            "total_orders": len(self.orders),
            "date_range": {"min": min(dates), "max": max(dates)},
            "customers": customers,
            "cities": cities,
            "products": products,
            "categories": categories,
            "statuses": statuses,
            "payment_methods": payment_methods
        }

dataset = OrderDataset()
