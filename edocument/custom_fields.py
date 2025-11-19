def get_custom_fields():
    return {
        "Company": [
            {
                "fieldname": "edocument_tab",
                "label": "EDocument",
                "fieldtype": "Tab Break",
                "insert_after": "dashboard_tab",
            },
            {
                "fieldname": "edocument_profile",
                "label": "EDocument Profile",
                "fieldtype": "Link",
                "options": "EDocument Profile",
                "insert_after": "edocument_tab",
            },
            {
                "fieldname": "edocument_electronic_address_scheme",
                "label": "Electronic Address Scheme",
                "fieldtype": "Link",
                "options": "Common Code",
                "insert_after": "edocument_profile",
            },
            {
                "fieldname": "edocument_electronic_address",
                "label": "Electronic Address",
                "fieldtype": "Data",
                "insert_after": "edocument_electronic_address_scheme",
                "depends_on": "edocument_electronic_address_scheme",
            },
        ],
        "Customer": [
            {
                "fieldname": "edocument_tab",
                "label": "EDocument",
                "fieldtype": "Tab Break",
                "insert_after": "portal_users",
            },
            {
                "fieldname": "edocument_profile",
                "label": "EDocument Profile",
                "fieldtype": "Link",
                "options": "EDocument Profile",
                "insert_after": "edocument_tab",
            },
            {
                "fieldname": "edocument_electronic_address_scheme",
                "label": "Electronic Address Scheme",
                "fieldtype": "Link",
                "options": "Common Code",
                "insert_after": "edocument_profile",
            },
            {
                "fieldname": "edocument_electronic_address",
                "label": "Electronic Address",
                "fieldtype": "Data",
                "insert_after": "edocument_electronic_address_scheme",
                "depends_on": "edocument_electronic_address_scheme",
            },
        ],
        "Supplier": [
            {
                "fieldname": "edocument_tab",
                "label": "EDocument",
                "fieldtype": "Tab Break",
                "insert_after": "portal_users",
            },
            {
                "fieldname": "edocument_profile",
                "label": "EDocument Profile",
                "fieldtype": "Link",
                "options": "EDocument Profile",
                "insert_after": "edocument_tab",
            },
            {
                "fieldname": "edocument_electronic_address_scheme",
                "label": "Electronic Address Scheme",
                "fieldtype": "Link",
                "options": "Common Code",
                "insert_after": "edocument_profile",
            },
            {
                "fieldname": "edocument_electronic_address",
                "label": "Electronic Address",
                "fieldtype": "Data",
                "insert_after": "edocument_electronic_address_scheme",
                "depends_on": "edocument_electronic_address_scheme",
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "edocument_tab",
                "label": "EDocument",
                "fieldtype": "Tab Break",
                "insert_after": "terms",
            },
            {
                "fieldname": "edocument_profile",
                "label": "EDocument Profile",
                "fieldtype": "Link",
                "options": "EDocument Profile",
                "insert_after": "edocument_tab",
                "fetch_from": "customer.edocument_profile",
                "fetch_if_empty": 1,
            },
        ],
    }
