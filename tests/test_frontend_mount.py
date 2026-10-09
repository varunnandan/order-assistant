import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_serve_index_and_static_files():
    # GET /
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Order Assistant" in res_index.text
    assert "<form id=\"chat-form\"" in res_index.text

    # GET /static/styles.css
    res_css = client.get("/static/styles.css")
    assert res_css.status_code == 200
    assert "--primary-color" in res_css.text

    # GET /static/app.js
    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "DOMContentLoaded" in res_js.text
