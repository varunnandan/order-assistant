import re
from typing import Dict, Any, List, Optional, Union
from app.data import dataset

def get_order(order_id: str) -> Dict[str, Any]:
    """Retrieve details for a single order by its ID (e.g., ORD-1025, ord 1025, 1025)."""
    normalized_id = dataset.normalize_order_id(order_id)
    for o in dataset.orders:
        if o["order_id"] == normalized_id:
            return {
                "ok": True,
                "order": o,
                "summary": f"Found order {normalized_id} for {o['customer_name']} ({o['product']}, total INR {o['total_inr']}, status: {o['status']})."
            }
    
    valid_ids = [o["order_id"] for o in dataset.orders]
    min_id = min(valid_ids) if valid_ids else "ORD-1001"
    max_id = max(valid_ids) if valid_ids else "ORD-1060"
    return {
        "ok": False,
        "error": f"No order found with ID {normalized_id}.",
        "hint": f"Valid order IDs range from {min_id} to {max_id}.",
        "summary": f"Order {normalized_id} not found."
    }

def search_orders(
    customer_name: Optional[str] = None,
    city: Optional[str] = None,
    product: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_total: Optional[float] = None,
    max_total: Optional[float] = None,
    sort_by: Optional[str] = "order_date",
    sort_order: Optional[str] = "desc",
    limit: Optional[int] = 20
) -> Dict[str, Any]:
    """Search and filter orders matching given criteria."""
    filtered = list(dataset.orders)

    # City alias
    if city:
        city = dataset.normalize_city(city)

    # Filtering logic
    if customer_name:
        c_low = customer_name.strip().lower()
        filtered = [o for o in filtered if c_low in o["customer_name"].lower()]

    if city:
        c_low = city.strip().lower()
        filtered = [o for o in filtered if c_low == o["city"].lower()]

    if product:
        p_low = product.strip().lower()
        filtered = [o for o in filtered if p_low in o["product"].lower()]

    if category:
        cat_low = category.strip().lower()
        filtered = [o for o in filtered if cat_low == o["category"].lower()]

    if status:
        st_low = status.strip().lower()
        filtered = [o for o in filtered if st_low == o["status"].lower()]

    if payment_method:
        pm_low = payment_method.strip().lower()
        filtered = [o for o in filtered if pm_low in o["payment_method"].lower()]

    if date_from:
        filtered = [o for o in filtered if o["order_date"] >= date_from]

    if date_to:
        filtered = [o for o in filtered if o["order_date"] <= date_to]

    if min_total is not None:
        filtered = [o for o in filtered if o["total_inr"] >= min_total]

    if max_total is not None:
        filtered = [o for o in filtered if o["total_inr"] <= max_total]

    matching_count = len(filtered)

    if matching_count == 0:
        info = dataset.get_dataset_info()
        suggestions = {}
        if customer_name:
            suggestions["valid_customers"] = info["customers"]
        if city:
            suggestions["valid_cities"] = info["cities"]
        if category:
            suggestions["valid_categories"] = info["categories"]
        if product:
            suggestions["valid_products"] = info["products"]
        if status:
            suggestions["valid_statuses"] = info["statuses"]

        return {
            "ok": True,
            "matching_count": 0,
            "returned_rows": 0,
            "rows": [],
            "message": "No orders matched the search criteria.",
            "suggestions": suggestions,
            "summary": "Found 0 matching orders."
        }

    # Sorting
    reverse = (sort_order or "desc").lower() == "desc"
    sort_key = sort_by if sort_by in ["order_date", "total_inr", "quantity"] else "order_date"
    filtered.sort(key=lambda x: x[sort_key], reverse=reverse)

    # Limit
    effective_limit = min(max(1, limit or 20), 50)
    rows = filtered[:effective_limit]

    return {
        "ok": True,
        "matching_count": matching_count,
        "returned_rows": len(rows),
        "rows": rows,
        "summary": f"Found {matching_count} matching orders (returned top {len(rows)})."
    }

def calculate_metrics(
    metric: str,
    group_by: Optional[str] = None,
    customer_name: Optional[str] = None,
    city: Optional[str] = None,
    product: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_total: Optional[float] = None,
    max_total: Optional[float] = None,
    include_statuses: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Calculate aggregate metrics (revenue, order_count, units_sold, average_order_value) over orders with optional grouping."""
    metric = metric.strip().lower()
    if metric not in ["revenue", "order_count", "units_sold", "average_order_value"]:
        return {
            "ok": False,
            "error": f"Invalid metric '{metric}'. Must be one of: revenue, order_count, units_sold, average_order_value.",
            "summary": f"Invalid metric {metric} requested."
        }

    # Status convention handling:
    # If metric is revenue or average_order_value, and include_statuses is not explicitly provided,
    # default to excluding cancelled and returned orders.
    # If status filter is passed explicitly, that takes precedence or works alongside include_statuses.
    all_statuses = ["delivered", "cancelled", "returned", "processing", "shipped"]
    
    if include_statuses is not None:
        valid_included = [s.strip().lower() for s in include_statuses]
    elif status:
        valid_included = [status.strip().lower()]
    elif metric in ["revenue", "average_order_value"]:
        valid_included = ["delivered", "processing", "shipped"]  # Excludes cancelled and returned sales
    else:
        valid_included = all_statuses

    filtered = list(dataset.orders)

    # Apply filters
    if customer_name:
        c_low = customer_name.strip().lower()
        filtered = [o for o in filtered if c_low in o["customer_name"].lower()]

    if city:
        c_norm = dataset.normalize_city(city).lower()
        filtered = [o for o in filtered if c_norm == o["city"].lower()]

    if product:
        p_low = product.strip().lower()
        filtered = [o for o in filtered if p_low in o["product"].lower()]

    if category:
        cat_low = category.strip().lower()
        filtered = [o for o in filtered if cat_low == o["category"].lower()]

    if payment_method:
        pm_low = payment_method.strip().lower()
        filtered = [o for o in filtered if pm_low in o["payment_method"].lower()]

    if date_from:
        filtered = [o for o in filtered if o["order_date"] >= date_from]

    if date_to:
        filtered = [o for o in filtered if o["order_date"] <= date_to]

    if min_total is not None:
        filtered = [o for o in filtered if o["total_inr"] >= min_total]

    if max_total is not None:
        filtered = [o for o in filtered if o["total_inr"] <= max_total]

    # Filter by included statuses
    filtered = [o for o in filtered if o["status"] in valid_included]

    def calc_value(items: List[Dict[str, Any]]) -> float:
        if not items:
            return 0.0
        if metric == "revenue":
            return float(sum(o["total_inr"] for o in items))
        elif metric == "order_count":
            return float(len(items))
        elif metric == "units_sold":
            return float(sum(o["quantity"] for o in items))
        elif metric == "average_order_value":
            tot = sum(o["total_inr"] for o in items)
            return float(round(tot / len(items), 2))
        return 0.0

    total_value = calc_value(filtered)
    total_orders = len(filtered)

    if not group_by:
        return {
            "ok": True,
            "metric": metric,
            "value": total_value,
            "matching_orders_count": total_orders,
            "included_statuses": valid_included,
            "summary": f"{metric.replace('_', ' ').title()}: {total_value} over {total_orders} orders (statuses included: {', '.join(valid_included)})."
        }

    # Grouped calculation
    group_key_name = group_by.strip().lower()
    valid_group_keys = ["customer_name", "product", "category", "city", "status", "payment_method", "month"]
    if group_key_name not in valid_group_keys:
        return {
            "ok": False,
            "error": f"Invalid group_by '{group_by}'. Must be one of: {', '.join(valid_group_keys)}.",
            "summary": f"Invalid group_by field {group_by}."
        }

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for o in filtered:
        if group_key_name == "month":
            g_val = o["order_date"][:7] # YYYY-MM
        else:
            g_val = o[group_key_name]
        groups.setdefault(g_val, []).append(o)

    grouped_rows = []
    for g_val, g_items in groups.items():
        v = calc_value(g_items)
        grouped_rows.append({
            group_key_name: g_val,
            "value": v,
            "order_count": len(g_items)
        })

    # Sort descending by value
    grouped_rows.sort(key=lambda x: x["value"], reverse=True)

    return {
        "ok": True,
        "metric": metric,
        "group_by": group_key_name,
        "total_value": total_value,
        "total_orders": total_orders,
        "included_statuses": valid_included,
        "groups": grouped_rows,
        "summary": f"Calculated {metric} grouped by {group_key_name} ({len(grouped_rows)} groups, total: {total_value}, statuses: {', '.join(valid_included)})."
    }

def get_dataset_info() -> Dict[str, Any]:
    """Get distinct values and summary metadata about the orders dataset."""
    res = dataset.get_dataset_info()
    res["summary"] = f"Dataset contains {res['total_orders']} orders from {res['date_range']['min']} to {res['date_range']['max']} across {len(res['cities'])} cities."
    return res

# Map tool names to functions
TOOL_REGISTRY = {
    "get_order": get_order,
    "search_orders": search_orders,
    "calculate_metrics": calculate_metrics,
    "get_dataset_info": get_dataset_info,
}
