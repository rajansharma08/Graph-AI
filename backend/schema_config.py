"""
Schema configuration for SAP O2C dataset tables, primary keys, and foreign keys.
"""

TABLE_CONFIG = {
    "sales_order_headers": {
        "pk": ["salesOrder"],
        "fks": [{"from": ["soldToParty"], "to_table": "business_partners", "to": ["businessPartner"], "rel": "sold_to_party"}],
    },
    "sales_order_items": {
        "pk": ["salesOrder", "salesOrderItem"],
        "fks": [
            {"from": ["salesOrder"], "to_table": "sales_order_headers", "to": ["salesOrder"], "rel": "belongs_to_order"},
            {"from": ["material"], "to_table": "products", "to": ["product"], "rel": "material_product"},
            {"from": ["productionPlant"], "to_table": "plants", "to": ["plant"], "rel": "produced_at_plant"},
        ],
    },
    "sales_order_schedule_lines": {
        "pk": ["salesOrder", "salesOrderItem", "scheduleLine"],
        "fks": [
            {"from": ["salesOrder", "salesOrderItem"], "to_table": "sales_order_items", "to": ["salesOrder", "salesOrderItem"], "rel": "schedule_for_item"},
        ],
    },
    "outbound_delivery_headers": {"pk": ["deliveryDocument"], "fks": []},
    "outbound_delivery_items": {
        "pk": ["deliveryDocument", "deliveryDocumentItem"],
        "fks": [
            {"from": ["deliveryDocument"], "to_table": "outbound_delivery_headers", "to": ["deliveryDocument"], "rel": "belongs_to_delivery"},
            {"from": ["plant"], "to_table": "plants", "to": ["plant"], "rel": "delivered_from_plant"},
            {"from": ["referenceSdDocument", "referenceSdDocumentItem"], "to_table": "sales_order_items", "to": ["salesOrder", "salesOrderItem"], "rel": "delivers_order_item"},
        ],
    },
    "billing_document_headers": {
        "pk": ["billingDocument"],
        "fks": [{"from": ["soldToParty"], "to_table": "business_partners", "to": ["businessPartner"], "rel": "billed_to_party"}],
    },
    "billing_document_items": {
        "pk": ["billingDocument", "billingDocumentItem"],
        "fks": [
            {"from": ["billingDocument"], "to_table": "billing_document_headers", "to": ["billingDocument"], "rel": "belongs_to_billing"},
            {"from": ["material"], "to_table": "products", "to": ["product"], "rel": "billed_product"},
            {"from": ["referenceSdDocument", "referenceSdDocumentItem"], "to_table": "sales_order_items", "to": ["salesOrder", "salesOrderItem"], "rel": "bills_order_item"},
        ],
    },
    "billing_document_cancellations": {
        "pk": ["billingDocument"],
        "fks": [{"from": ["soldToParty"], "to_table": "business_partners", "to": ["businessPartner"], "rel": "cancelled_for_party"}],
    },
    "journal_entry_items_accounts_receivable": {
        "pk": ["companyCode", "fiscalYear", "accountingDocument", "accountingDocumentItem"],
        "fks": [
            {"from": ["referenceDocument"], "to_table": "billing_document_headers", "to": ["billingDocument"], "rel": "journal_for_billing"},
            {"from": ["customer"], "to_table": "business_partners", "to": ["businessPartner"], "rel": "journal_customer"},
        ],
    },
    "payments_accounts_receivable": {
        "pk": ["companyCode", "fiscalYear", "accountingDocument", "accountingDocumentItem"],
        "fks": [
            {"from": ["customer"], "to_table": "business_partners", "to": ["businessPartner"], "rel": "payment_customer"},
            {"from": ["salesDocument"], "to_table": "sales_order_headers", "to": ["salesOrder"], "rel": "payment_for_order"},
        ],
    },
    "business_partners": {"pk": ["businessPartner"], "fks": []},
    "business_partner_addresses": {
        "pk": ["businessPartner", "addressId"],
        "fks": [{"from": ["businessPartner"], "to_table": "business_partners", "to": ["businessPartner"], "rel": "has_address"}],
    },
    "products": {"pk": ["product"], "fks": []},
    "product_descriptions": {
        "pk": ["product", "language"],
        "fks": [{"from": ["product"], "to_table": "products", "to": ["product"], "rel": "description_of_product"}],
    },
    "product_plants": {
        "pk": ["product", "plant"],
        "fks": [
            {"from": ["product"], "to_table": "products", "to": ["product"], "rel": "product_at_plant"},
            {"from": ["plant"], "to_table": "plants", "to": ["plant"], "rel": "plant_stores_product"},
        ],
    },
    "product_storage_locations": {
        "pk": ["product", "plant", "storageLocation"],
        "fks": [
            {"from": ["product", "plant"], "to_table": "product_plants", "to": ["product", "plant"], "rel": "storage_for_product_plant"},
        ],
    },
    "plants": {"pk": ["plant"], "fks": []},
    "customer_company_assignments": {
        "pk": ["customer", "companyCode"],
        "fks": [{"from": ["customer"], "to_table": "business_partners", "to": ["customer"], "rel": "customer_company_assignment"}],
    },
    "customer_sales_area_assignments": {
        "pk": ["customer", "salesOrganization", "distributionChannel", "division"],
        "fks": [{"from": ["customer"], "to_table": "business_partners", "to": ["customer"], "rel": "customer_sales_area_assignment"}],
    },
}

NODE_LABEL_HINTS = {
    "sales_order_headers": "salesOrder",
    "sales_order_items": "salesOrderItem",
    "outbound_delivery_headers": "deliveryDocument",
    "outbound_delivery_items": "deliveryDocumentItem",
    "billing_document_headers": "billingDocument",
    "billing_document_items": "billingDocumentItem",
    "business_partners": "businessPartnerName",
    "products": "product",
    "plants": "plant",
}
