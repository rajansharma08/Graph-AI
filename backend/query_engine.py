"""
Query engine for translating natural language to structured queries.
Includes domain guardrails, rule-based SQL, LLM fallback, and result summarization.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from .data_layer import DataLayer


# Domain keywords for guardrails
DOMAIN_KEYWORDS = {
    "order", "sales", "delivery", "invoice", "billing", "payment", "journal",
    "customer", "product", "material", "plant", "company", "amount", "quantity",
    "flow", "document", "account", "receivable", "shipment", "shipped",
}


@dataclass
class QueryResult:
    """Result of a query execution."""
    answer: str
    sql: str | None
    rows: list[dict[str, Any]]
    highlighted_nodes: list[str]


class QueryEngine:
    def __init__(self, data_layer: DataLayer):
        self.data_layer = data_layer
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        self.model = None
        
        if GENAI_AVAILABLE and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
            except Exception:
                self.model = None

    def _domain_guardrail(self, text: str) -> bool:
        """Check if question is related to the O2C domain."""
        t = text.lower()
        return any(k in t for k in DOMAIN_KEYWORDS)

    def _rule_based_sql(self, question: str) -> str | None:
        """Generate SQL for known query patterns."""
        q = question.lower()

        # Generic product listing
        if ("product" in q or "material" in q) and ("show" in q or "list" in q or "what" in q or "display" in q or "have" in q):
            return """
                SELECT DISTINCT p.product,
                       pd.productDescription,
                       COUNT(DISTINCT pp.plant) AS plant_count,
                       COUNT(DISTINCT psl.storageLocation) AS storage_locations
                FROM products p
                LEFT JOIN product_descriptions pd ON p.product = pd.product AND pd.language = 'EN'
                LEFT JOIN product_plants pp ON p.product = pp.product
                LEFT JOIN product_storage_locations psl ON p.product = psl.product AND pp.plant = psl.plant
                GROUP BY p.product, pd.productDescription
                ORDER BY p.product
                LIMIT 100
            """

        # Generic customer listing
        if ("customer" in q or "partner" in q) and ("show" in q or "list" in q or "what" in q or "display" in q or "have" in q):
            return """
                SELECT bp.businessPartner,
                       bp.businessPartnerName,
                       COUNT(DISTINCT soh.salesOrder) AS total_orders,
                       COUNT(DISTINCT bdh.billingDocument) AS total_invoices
                FROM business_partners bp
                LEFT JOIN sales_order_headers soh ON bp.businessPartner = soh.soldToParty
                LEFT JOIN billing_document_headers bdh ON bp.businessPartner = bdh.soldToParty
                GROUP BY bp.businessPartner, bp.businessPartnerName
                ORDER BY total_orders DESC
                LIMIT 100
            """

        # Generic order-to-delivery-to-billing flow (entire O2C process)
        if ("flow" in q or "o2c" in q or "order" in q) and ("delivery" in q or "billing" in q or "end-to-end" in q or "process" in q):
            return """
                WITH orders AS (
                    SELECT DISTINCT salesOrder,
                           soldToParty,
                           creationDate
                    FROM sales_order_headers
                    LIMIT 50
                ),
                deliveries AS (
                    SELECT DISTINCT odi.referenceSdDocument AS salesOrder,
                           odh.deliveryDocument,
                           odh.documentDate
                    FROM outbound_delivery_items odi
                    JOIN outbound_delivery_headers odh ON odi.deliveryDocument = odh.deliveryDocument
                ),
                billings AS (
                    SELECT DISTINCT bdi.referenceSdDocument AS salesOrder,
                           bdh.billingDocument,
                           bdh.billingDocumentDate
                    FROM billing_document_items bdi
                    JOIN billing_document_headers bdh ON bdi.billingDocument = bdh.billingDocument
                )
                SELECT o.salesOrder,
                       bp.businessPartnerName AS customer,
                       d.deliveryDocument,
                       b.billingDocument,
                       o.creationDate,
                       d.documentDate,
                       b.billingDocumentDate
                FROM orders o
                LEFT JOIN business_partners bp ON o.soldToParty = bp.businessPartner
                LEFT JOIN deliveries d ON o.salesOrder = d.salesOrder
                LEFT JOIN billings b ON o.salesOrder = b.salesOrder
                ORDER BY o.salesOrder
                LIMIT 50
            """

        # Query a: Which products are associated with highest number of billing documents?
        if ("highest" in q or "most" in q) and "billing" in q and ("product" in q or "material" in q):
            return """
                SELECT bdi.material AS product,
                       COUNT(DISTINCT bdi.billingDocument) AS billing_document_count
                FROM billing_document_items bdi
                WHERE bdi.material IS NOT NULL
                GROUP BY bdi.material
                ORDER BY billing_document_count DESC
                LIMIT 20
            """

        # Query c: Identify broken/incomplete flows
        if ("incomplete" in q or "broken" in q or "not billed" in q or "without delivery" in q):
            return """
                WITH delivered AS (
                    SELECT DISTINCT referenceSdDocument AS salesOrder
                    FROM outbound_delivery_items
                    WHERE referenceSdDocument IS NOT NULL
                ),
                billed AS (
                    SELECT DISTINCT referenceSdDocument AS salesOrder
                    FROM billing_document_items
                    WHERE referenceSdDocument IS NOT NULL
                )
                SELECT soh.salesOrder,
                       CASE
                         WHEN d.salesOrder IS NOT NULL AND b.salesOrder IS NULL THEN 'DELIVERED_NOT_BILLED'
                         WHEN d.salesOrder IS NULL AND b.salesOrder IS NOT NULL THEN 'BILLED_WITHOUT_DELIVERY'
                         ELSE 'OK'
                       END AS flow_status,
                       (SELECT COUNT(*) FROM sales_order_items WHERE salesOrder = soh.salesOrder) AS item_count
                FROM sales_order_headers soh
                LEFT JOIN delivered d ON soh.salesOrder = d.salesOrder
                LEFT JOIN billed b ON soh.salesOrder = b.salesOrder
                WHERE (d.salesOrder IS NOT NULL AND b.salesOrder IS NULL)
                   OR (d.salesOrder IS NULL AND b.salesOrder IS NOT NULL)
                ORDER BY soh.salesOrder
                LIMIT 100
            """

        # Query b: Trace full flow of a specific billing document
        m = re.search(r"(?:billing\s*document|document)\s*(?:[:=])?\s*([A-Z0-9]+)", q)
        if ("trace" in q or "flow" in q or "linked" in q or "related" in q or "show all" in q) and m:
            billing_doc = m.group(1)
            return f"""
                SELECT bdh.billingDocument,
                       bdh.billingDocumentDate,
                       bdi.referenceSdDocument AS salesOrder,
                       bdi.referenceSdDocumentItem AS salesOrderItem,
                       odi.deliveryDocument,
                       odi.deliveryDocumentItem,
                       jeiar.accountingDocument,
                       jeiar.companyCode,
                       jeiar.fiscalYear,
                       par.accountingDocument AS paymentDocument
                FROM billing_document_headers bdh
                LEFT JOIN billing_document_items bdi ON bdh.billingDocument = bdi.billingDocument
                LEFT JOIN outbound_delivery_items odi
                       ON bdi.referenceSdDocument = odi.referenceSdDocument
                      AND bdi.referenceSdDocumentItem = odi.referenceSdDocumentItem
                LEFT JOIN journal_entry_items_accounts_receivable jeiar
                       ON jeiar.referenceDocument = bdh.billingDocument
                LEFT JOIN payments_accounts_receivable par
                       ON par.customer = bdh.soldToParty
                WHERE bdh.billingDocument = '{billing_doc}'
                LIMIT 50
            """

        # Fallback trace (pick first billing document)
        if "trace" in q and "billing" in q:
            return """
                WITH chosen_billing AS (
                    SELECT billingDocument, billingDocumentDate
                    FROM billing_document_headers
                    ORDER BY billingDocument
                    LIMIT 1
                )
                SELECT bdh.billingDocument,
                       bdh.billingDocumentDate,
                       bdi.referenceSdDocument AS salesOrder,
                       bdi.referenceSdDocumentItem AS salesOrderItem,
                       odi.deliveryDocument,
                       jeiar.accountingDocument,
                       jeiar.companyCode,
                       jeiar.fiscalYear
                FROM billing_document_headers bdh
                JOIN chosen_billing cb ON cb.billingDocument = bdh.billingDocument
                LEFT JOIN billing_document_items bdi ON bdh.billingDocument = bdi.billingDocument
                LEFT JOIN outbound_delivery_items odi
                       ON bdi.referenceSdDocument = odi.referenceSdDocument
                      AND bdi.referenceSdDocumentItem = odi.referenceSdDocumentItem
                LEFT JOIN journal_entry_items_accounts_receivable jeiar
                       ON jeiar.referenceDocument = bdh.billingDocument
                LIMIT 50
            """

        # Query about customers and their orders
        if ("customer" in q and ("order" in q or "delivered" in q or "billed" in q)):
            return """
                SELECT bp.businessPartner,
                       bp.businessPartnerName,
                       COUNT(DISTINCT soh.salesOrder) AS order_count,
                       COUNT(DISTINCT odi.deliveryDocument) AS delivery_count,
                       COUNT(DISTINCT bdh.billingDocument) AS billing_count
                FROM business_partners bp
                LEFT JOIN sales_order_headers soh ON soh.soldToParty = bp.businessPartner
                LEFT JOIN outbound_delivery_items odi ON odi.referenceSdDocument = soh.salesOrder
                LEFT JOIN billing_document_headers bdh ON bdh.soldToParty = bp.businessPartner
                GROUP BY bp.businessPartner, bp.businessPartnerName
                HAVING order_count > 0
                ORDER BY order_count DESC
                LIMIT 30
            """

        return None

    def _llm_generate_sql(self, question: str) -> str | None:
        """Use LLM to generate SQL from natural language."""
        if not self.model:
            return None

        schema_text = self.data_layer.get_schema_prompt_text()
        prompt = f"""You are generating DuckDB SQL for a SAP Order-to-Cash (O2C) dataset.
Return ONLY the SQL query, no markdown, no explanations.
Constraints:
- Only SELECT or WITH statements.
- Use only tables/columns from the provided schema.
- Include LIMIT 100 unless user specifically asks for more.
- No destructive operations.

Available Schema:
{schema_text}

Question: {question}

Generate the SQL:"""
        try:
            out = self.model.generate_content(prompt)
            text = out.text.strip()
            # Remove markdown code blocks if present
            text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            # Extract the actual SQL
            m = re.search(r"(?is)(with\s+.+|select\s+.+)", text)
            sql = m.group(1).strip() if m else text
            return sql
        except Exception:
            return None

    def _safe_sql(self, sql: str | None) -> str | None:
        """Validate SQL to prevent dangerous operations."""
        if not sql:
            return None
        s = sql.strip().lower()
        if not s.startswith("select") and not s.startswith("with"):
            return None
        # Block dangerous keywords
        banned = ["insert", "update", "delete", "drop", "alter", "truncate", "create", "attach", "copy", ";--", "pragma"]
        if any(tok in s for tok in banned):
            return None
        return sql

    def _summarize_with_llm(self, question: str, sql: str, df: pd.DataFrame) -> str:
        """Use LLM to summarize query results in natural language."""
        if df.empty:
            return "No matching records found in the dataset for this query."

        if not self.model:
            return self._fallback_nl_summary(question, df)

        prompt = f"""You are answering a business question about an SAP Order-to-Cash dataset.
Your goal is to provide a clear, concise, human-readable answer.

Question: {question}
Rows returned: {len(df)}
Data (first 20 rows):
{df.head(20).to_json(orient='records', date_format='iso')}

Provide a natural language business summary:
1. Start with a brief statement of what the data shows
2. Highlight key numbers, patterns, and insights
3. If there are multiple records, summarize trends rather than listing all records
4. Use business language, not technical jargon
5. Keep it under 200 words and easy to understand for a business user"""
        try:
            out = self.model.generate_content(prompt)
            return out.text.strip()
        except Exception:
            return self._fallback_nl_summary(question, df)

    def _fallback_nl_summary(self, question: str, df: pd.DataFrame) -> str:
        """Generate a natural language summary without LLM."""
        q = question.lower()
        cols = set(df.columns)

        # Generic product listing
        if {"product", "productDescription"}.issubset(cols):
            lines = [f"Found {len(df)} products in the system:\n"]
            for i, row in df.head(20).iterrows():
                product = row.get("product", "N/A")
                desc = row.get("productDescription", "No description")
                plants = row.get("plant_count", 0)
                storage = row.get("storage_locations", 0)
                lines.append(f"• {product} - {desc}")
                if plants and plants > 0:
                    lines.append(f"  Available in {plants} plant(s) with {storage} storage location(s)")
            if len(df) > 20:
                lines.append(f"\n... and {len(df) - 20} more products")
            return "\n".join(lines)

        # Generic customer listing
        if {"businessPartner", "businessPartnerName"}.issubset(cols) and "total_orders" in cols:
            lines = [f"Company has {len(df)} business partners:\n"]
            total_orders = df["total_orders"].sum() if "total_orders" in cols else 0
            total_invoices = df["total_invoices"].sum() if "total_invoices" in cols else 0
            lines.append(f"Overall Statistics:")
            lines.append(f"  • Total Customers: {len(df)}")
            lines.append(f"  • Total Orders: {int(total_orders)}")
            lines.append(f"  • Total Invoices: {int(total_invoices)}\n")
            lines.append(f"Top Customers by Order Volume:")
            for i, row in df.head(10).iterrows():
                partner = row.get("businessPartnerName", "Unknown")
                orders = int(row.get("total_orders", 0))
                invoices = int(row.get("total_invoices", 0))
                lines.append(f"  {i+1}. {partner}: {orders} orders, {invoices} invoices")
            if len(df) > 10:
                lines.append(f"\n... showing top 10 of {len(df)} customers")
            return "\n".join(lines)

        # O2C Flow (order to delivery to billing)
        if {"salesOrder", "deliveryDocument", "billingDocument"}.intersection(cols):
            lines = ["Order-to-Cash (O2C) Flow Summary:\n"]
            total = len(df)
            completed = df[df["billingDocument"].notna()].shape[0] if "billingDocument" in cols else 0
            delivered = df[df["deliveryDocument"].notna()].shape[0] if "deliveryDocument" in cols else 0
            
            lines.append(f"Process Status:")
            lines.append(f"  • Total Sales Orders: {total}")
            lines.append(f"  • Orders Delivered: {delivered} ({int(delivered/max(total,1)*100)}%)")
            lines.append(f"  • Orders Billed: {completed} ({int(completed/max(total,1)*100)}%)\n")
            
            lines.append(f"Sample Order Flows (showing first {min(5, total)}):")
            for i, row in df.head(5).iterrows():
                order = row.get("salesOrder", "N/A")
                customer = row.get("customer", "Unknown")
                delivery = row.get("deliveryDocument", "—")
                billing = row.get("billingDocument", "—")
                lines.append(f"  • Order {order} ({customer})")
                lines.append(f"    → Delivery: {delivery} → Billing: {billing}")
            
            if total > 5:
                lines.append(f"\n... showing 5 of {total} orders")
            return "\n".join(lines)

        # Top products by billing document count
        if {"product", "billing_document_count"}.issubset(cols):
            top = df.head(5).to_dict(orient="records")
            lines = [f"Top {len(top)} products by number of billing documents:"]
            for i, row in enumerate(top, start=1):
                lines.append(f"{i}. Product '{row['product']}': {row['billing_document_count']} billing documents")
            lines.append(f"\nTotal products returned: {len(df)}.")
            return "\n".join(lines)

        # Incomplete/broken flows
        if {"salesOrder", "flow_status"}.issubset(cols):
            status_counts = df["flow_status"].value_counts().to_dict()
            sample = df.head(10)[["salesOrder", "flow_status"]].to_dict(orient="records")
            lines = ["Incomplete or broken sales order flows detected:"]
            for status, count in status_counts.items():
                lines.append(f"- {status}: {count} orders")
            lines.append("\nSample orders:")
            for row in sample:
                lines.append(f"  • Order {row['salesOrder']}: {row['flow_status']}")
            lines.append(f"\nTotal affected orders: {len(df)}.")
            return "\n".join(lines)

        # Generic summary for any other query
        return f"""Query completed successfully! 

Results: {len(df)} records found

Summary: Your query returned {len(df)} results. Here are the first few records:

{self._format_table_summary(df.head(10))}

Use the "Show SQL" button to see the exact query used, and explore the results in the data table below."""

    def _format_table_summary(self, df: pd.DataFrame) -> str:
        """Format a DataFrame as a readable text summary."""
        if df.empty:
            return "No data to display"
        
        lines = []
        cols_to_show = df.columns.tolist()[:4]  # Show first 4 columns
        
        for i, row in df.iterrows():
            formatted_row = ", ".join([
                f"{col}: {row[col]}"
                for col in cols_to_show
                if col in df.columns
            ])
            lines.append(f"• {formatted_row}")
        
        if len(df.columns) > 4:
            lines.append(f"  ... and {len(df.columns) - 4} more columns")
        
        return "\n".join(lines)

    def _extract_ids(self, text: str) -> list[str]:
        """Extract document IDs from response text for highlighting."""
        # Look for numeric IDs (6-12 digits typically document numbers)
        ids = re.findall(r"\b(\d{6,12})\b", text)
        return list(set(ids))[:20]  # Limit to 20 to avoid overwhelming the UI

    def ask(self, question: str) -> QueryResult:
        """Process a natural language question and return results."""
        # Step 1: Domain guardrail
        if not self._domain_guardrail(question):
            return QueryResult(
                answer="This system is designed to answer questions related to the provided dataset only. Please ask about orders, deliveries, billing, payments, customers, or products.",
                sql=None,
                rows=[],
                highlighted_nodes=[],
            )

        # Step 2: Try rule-based SQL first
        sql = self._rule_based_sql(question)
        
        # Step 3: Fall back to LLM if no rule matched
        if not sql:
            sql = self._llm_generate_sql(question)

        # Step 4: Validate SQL
        sql = self._safe_sql(sql)
        if not sql:
            return QueryResult(
                answer="I could not generate a valid query for that question. Please rephrase with specific entity references (e.g., order ID, billing document, customer name).",
                sql=None,
                rows=[],
                highlighted_nodes=[],
            )

        # Step 5: Execute SQL
        try:
            df = self.data_layer.execute_sql(sql)
            answer = self._summarize_with_llm(question, sql, df)
            highlighted = self._extract_ids(answer)
            return QueryResult(
                answer=answer,
                sql=sql,
                rows=df.head(100).to_dict(orient="records"),
                highlighted_nodes=highlighted,
            )
        except Exception as e:
            return QueryResult(
                answer=f"Query execution failed: {str(e)}. Please rephrase your question.",
                sql=sql,
                rows=[],
                highlighted_nodes=[],
            )
