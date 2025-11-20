from pathlib import Path

HTML = Path("frontend/index.html").read_text(encoding="utf-8")


def test_crud_sections_present():
    for section_id in [
        "clients-section",
        "users-section",
        "roles-section",
        "devices-section",
        "plans-section",
    ]:
        assert section_id in HTML, f"Expected {section_id} in CRUD layout"


def test_feature_blocks_present():
    expected_labels = [
        "Dashboards de estado",
        "Geocercas y plantillas de alertas",
        "Eventos y posiciones",
        "Exportar CSV",
        "Exportar PDF",
    ]
    for label in expected_labels:
        assert label in HTML, f"Missing feature label: {label}"


def test_sample_data_present():
    assert "Acme Corp" in HTML
    assert "Premium 10GB" in HTML
    assert "Vehículo 1" in HTML


def test_dashboard_widgets():
    for widget_id in ["onlineCount", "offlineCount", "recentAlerts", "dataUsage", "map"]:
        assert widget_id in HTML, f"Dashboard widget {widget_id} should exist"
