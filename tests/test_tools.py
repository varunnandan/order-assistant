import pytest
from app.data import dataset
from app.tools import get_order, search_orders, calculate_metrics, get_dataset_info

def test_get_order_exact_and_normalization():
    # Exact match ORD-1025
    res = get_order("ORD-1025")
    assert res["ok"] is True
    order = res["order"]
    assert order["order_id"] == "ORD-1025"
    assert order["customer_name"] == "Karthik Rao"
    assert order["city"] == "Kochi"
    assert order["product"] == "Wireless Mouse"
    assert order["quantity"] == 3
    assert order["total_inr"] == 2397
    assert order["status"] == "delivered"

    # Normalization tests
    res_1025 = get_order("1025")
    assert res_1025["ok"] is True
    assert res_1025["order"]["order_id"] == "ORD-1025"

    res_ord1025 = get_order("ord 1025")
    assert res_ord1025["ok"] is True
    assert res_ord1025["order"]["order_id"] == "ORD-1025"

def test_get_order_nonexistent():
    res = get_order("ORD-9999")
    assert res["ok"] is False
    assert "No order found" in res["error"]
    assert "ORD-1001" in res["hint"]
    assert "ORD-1060" in res["hint"]

def test_status_counts():
    cancelled_res = search_orders(status="cancelled")
    assert cancelled_res["ok"] is True
    assert cancelled_res["matching_count"] == 7

    returned_res = search_orders(status="returned")
    assert returned_res["ok"] is True
    assert returned_res["matching_count"] == 3

def test_electronics_august_revenue():
    # Aug 2026 dates: 2026-08-01 to 2026-08-31
    # Excluding cancelled & returned (default)
    res_default = calculate_metrics(
        metric="revenue",
        category="Electronics",
        date_from="2026-08-01",
        date_to="2026-08-31"
    )
    assert res_default["ok"] is True
    assert res_default["value"] == 16692

    # Including cancelled & returned
    res_all = calculate_metrics(
        metric="revenue",
        category="Electronics",
        date_from="2026-08-01",
        date_to="2026-08-31",
        include_statuses=["delivered", "cancelled", "returned", "processing", "shipped"]
    )
    assert res_all["ok"] is True
    assert res_all["value"] == 27189

def test_top_customer_by_revenue():
    res = calculate_metrics(
        metric="revenue",
        group_by="customer_name"
    )
    assert res["ok"] is True
    top_customer = res["groups"][0]
    assert top_customer["customer_name"] == "Rohan Das"
    assert top_customer["value"] == 91887

def test_city_alias_and_search_no_matches():
    # City alias Trivandrum -> Thiruvananthapuram
    res_alias = search_orders(city="Trivandrum")
    assert res_alias["ok"] is True
    assert res_alias["matching_count"] > 0
    for row in res_alias["rows"]:
        assert row["city"] == "Thiruvananthapuram"

    # Search with no matches
    res_empty = search_orders(customer_name="NonExistentCustomerName123")
    assert res_empty["ok"] is True
    assert res_empty["matching_count"] == 0
    assert "No orders matched" in res_empty["message"]
    assert "valid_customers" in res_empty["suggestions"]

def test_invalid_metric_and_group_by():
    res_metric = calculate_metrics(metric="invalid_metric_name")
    assert res_metric["ok"] is False
    assert "Invalid metric" in res_metric["error"]

    res_group = calculate_metrics(metric="revenue", group_by="invalid_field")
    assert res_group["ok"] is False
    assert "Invalid group_by" in res_group["error"]

def test_get_dataset_info():
    info = get_dataset_info()
    assert info["ok"] is True
    assert info["total_orders"] == 60
    assert info["date_range"]["min"] == "2026-06-01"
    assert info["date_range"]["max"] == "2026-09-28"
    assert "Electronics" in info["categories"]
    assert "Kochi" in info["cities"]
