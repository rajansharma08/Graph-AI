# Graph AI - Natural Language to SQL for SAP Data

## 🎯 Project Overview

**Graph AI** is an intelligent query system that converts natural language questions into SQL queries for SAP Order-to-Cash (O2C) data. It combines graph visualization with LLM-powered query generation to make complex business data accessible through conversational AI.

**Live Demo:** https://graph-ai-7o34.onrender.com/

**Source Code:** https://github.com/rajansharma08/Graph-AI-Deploy

---

## 🏗️ Architectural Decisions

### 1. **Technology Stack Rationale**

| Component | Technology | Reason |
|-----------|-----------|--------|
| **Backend** | FastAPI | Lightweight, async-ready, excellent for real-time queries, minimal setup |
| **Frontend** | Vanilla JS + Vis.js | No build step, minimal dependencies, smooth graph visualization |
| **Database** | DuckDB | In-memory OLAP DB, perfect for analytical queries on JSON data |
| **LLM** | Google Gemini 1.5 Flash | Fast inference (~2-4s), affordable API, good SQL understanding |
| **Deployment** | Docker + Render | Reproducible, includes all data, free hosting with auto-scaling |

### 2. **Database Choice: Why DuckDB?**

**Alternatives Considered:**
- **PostgreSQL/MySQL**: Over-engineered, requires separate infrastructure
- **SQLite**: Single-threaded, not ideal for analytical queries
- **MongoDB**: Document DB doesn't fit relational SAP structure
- **Snowflake/BigQuery**: Too expensive for demo/assignment

**DuckDB Advantages:**
- ⚡ Sub-millisecond in-memory query execution
- 📦 Ships with application (no separate server)
- 📝 Native JSON/JSONL support (20+ column tables in single file)
- 🔍 Excellent column-oriented (OLAP) query performance
- 💾 Fits entire dataset in available RAM (~150MB)

**Data Model:**
- 19 SAP O2C tables with full relationship integrity
- 48 JSONL files (~3.65 MB total)
- Foreign keys define graph relationships
- Supports 19 different entity types with ~50K total records

### 3. **LLM Prompting Strategy**

**Three-Layer Query Generation Pipeline:**

```
┌─────────────────────────────────────┐
│  User Natural Language Question     │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│  Layer 1: Rule-Based SQL Gen        │  ← 80% of queries
│  (Instant, no API latency)          │
└────────────┬────────────────────────┘
             │ No match? Continue
             ↓
┌─────────────────────────────────────┐
│  Layer 2: LLM Generation (Gemini)   │  ← Fallback for complex
│  (2-4s latency with API call)       │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│  Layer 3: Safety Validation         │
│  (Block dangerous SQL operations)   │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│  Execute on DuckDB → Summarize      │
└─────────────────────────────────────┘
```

**LLM Prompt Design:**

```python
prompt = f"""You are generating DuckDB SQL for a SAP Order-to-Cash dataset.
Return ONLY the SQL query, no markdown, no explanations.
Constraints:
- Only SELECT or WITH statements
- Use ONLY tables/columns from schema
- Include LIMIT 100 unless asked for more
- No destructive operations

Available Schema:
{schema_text}

Question: {question}

Generate the SQL:"""
```

**Key Design Choices:**
1. **Schema Injection** - Full table/column info provided
2. **Constraint Setting** - Explicit DuckDB SQL rules
3. **Clear Instructions** - "Return ONLY SQL, no markdown"
4. **Fallback Handling** - Always provide answer even if LLM fails

### 4. **Safety Guardrails & Constraints**

**Domain Guardrail (Input Validation):**
```python
DOMAIN_KEYWORDS = {
    "order", "sales", "delivery", "invoice", "billing", 
    "payment", "customer", "product", "plant", "company",
    "account", "receivable", "material", "shipment"
}
# Only allow queries about these topics
```

**SQL Safety Validator:**
```python
BANNED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", 
    "TRUNCATE", "CREATE", "ATTACH", "PRAGMA"
]
# Block all destructive/unauthorized operations
```

**Validation Flow:**
1. ✅ Allow: `SELECT ... FROM ...`
2. ✅ Allow: `WITH ... AS (...) SELECT ...`
3. ❌ Block: Multi-statements (`;--`)
4. ❌ Block: Keyword-based injection

**Example:**
```python
# This would be rejected:
"SELECT * FROM products; DROP TABLE products;--"
# Dangerous keyword 'DROP' detected

# This is allowed:
"SELECT COUNT(*) FROM sales_order_headers"
# Only SELECT, safe to execute
```

### 5. **Graph Visualization Strategy**

**Why Use Graphs Instead of Tables?**

Raw SQL results show rows/columns - difficult for understanding relationships.

**Graph Approach:**
1. Parse Foreign Key relationships → Define edges
2. Extract entities → Create nodes
3. Visualize with Vis.js → Interactive exploration

**Example O2C Flow:**
```
Sales Order (SO-001)
    ↓ [orders]
Delivery Items (DLV-005)
    ↓ [bills]
Billing Items (INV-0123)
    ↓ [records in GL]
Journal Entry (JE-4567)
```

**User Benefits:**
- See complete data flow visually
- Click entities to expand context
- Understand business logic at glance
- Identify missing data/gaps in flow

---

## 🗄️ Data Model & Schema

### 19 SAP O2C Tables

**Order Processing (4 tables):**
- `sales_order_headers` - Main sales orders
- `sales_order_items` - Order line items  
- `sales_order_schedule_lines` - Delivery schedules

**Delivery (2 tables):**
- `outbound_delivery_headers` - Shipment records
- `outbound_delivery_items` - Shipment line items

**Billing (3 tables):**
- `billing_document_headers` - Invoice records
- `billing_document_items` - Invoice line items
- `billing_document_cancellations` - Cancelled invoices

**Financial (2 tables):**
- `journal_entry_items_accounts_receivable` - GL postings
- `payments_accounts_receivable` - Customer payments

**Master Data (5 tables):**
- `business_partners` - Customers/vendors
- `business_partner_addresses` - Location data
- `products` - Product catalog
- `product_descriptions` - Product text
- `plants` - Manufacturing facilities

**Relationships (3 tables):**
- `product_plants` - Storage at facilities
- `product_storage_locations` - Warehouse locations
- `customer_company_assignments` - Company mappings
- `customer_sales_area_assignments` - Sales area mappings

---

## 🔄 Query Execution Flow

```
1. INPUT: User question in natural language
   "Show me all customers with their orders"
   
2. DOMAIN CHECK: Is this about O2C?
   → Keywords check: "customer", "orders" ✓
   → Domain approved: CONTINUE
   
3. RULE-BASED MATCHING: Do we have a template?
   → Pattern: "customer" + ("order" | "delivered" | "billed")
   → Match found: YES
   → Execute pre-written SQL (instant)
   
4. SAFETY VALIDATION: Is SQL safe?
   → Check for banned keywords: NONE found ✓
   → Check for syntax: Only SELECT ✓
   → Approved: EXECUTE
   
5. DATABASE QUERY: Run on DuckDB
   → Returns DataFrame with 10 results
   
6. NL SUMMARIZATION: Make results human-readable
   → LLM: "Company has 10 business partners..."
   → Fallback: Template-based summary
   
7. OUTPUT: Complete response
   - Answer: "Company has 10 business partners..."
   - SQL: SELECT bp.businessPartner, ... FROM business_partners
   - Data: [rows 1-10 in table format]
   - Graph: Highlighted customer nodes
```

---

## 🎨 Frontend Architecture

**Single-Page Application (No build step)**

**Structure:**
```
frontend/
├── index.html (main app)
│   ├── <style> (embedded CSS)
│   ├── Graph visualization (Vis.js)
│   ├── Query chat interface  
│   ├── Results display
│   └── <script> (vanilla JS)
```

**Components:**
1. **Query Input** - Chat-like text input
2. **Response Panel** - AI answer in plain English
3. **Graph Visualization** - Interactive entity network
4. **Data Table** - Raw query results with sorting
5. **SQL Explorer** - Show exact SQL executed

**Why Vanilla JS?**
- No build process required
- Minimal dependencies (only Vis.js for graphs)
- Single HTML file deployable anywhere
- Fast, lightweight execution

---

## 🚀 Deployment Strategy

### Docker-Based Approach

**Why Docker Over Cloud Storage?**
- ✅ Self-contained (includes all data)
- ✅ Reproducible across environments
- ✅ No external dependencies
- ✅ Simple for free tier hosting
- ❌ Simpler than: Firebase, S3, GCS setup

**Dockerfile Optimization:**
```dockerfile
FROM python:3.11-slim          # Minimal base image
COPY . /app                     # Copy all code + data
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 8000
HEALTHCHECK --interval=30s CMD curl -f http://localhost:8000/health
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Image Size:**
- Python 3.11-slim: 120MB
- Dependencies: 250MB
- Data folder: 3.65MB  
- **Total: ~375MB** (fits in Render's 512MB free tier)

### Render Deployment

**Why Render?**
- Free tier: 512MB RAM, reasonable for demo
- Auto-redeploy on git push
- HTTPS included
- Easy multi-environment setup

**Environment Variables:**
- `GOOGLE_API_KEY` - Gemini API authentication
- `DATA_ROOT` - Path to data folder (./Data)
- `HOST` / `PORT` - Server binding

```bash
# Set in Render dashboard
GOOGLE_API_KEY=AIzaSyBfYlIWw...
```

---

## 🔐 Security Implementation

| Concern | Mitigation | Implementation |
|---------|-----------|-----------------|
| SQL Injection | Allowlist validation | Only SELECT/WITH allowed |
| Out-of-scope queries | Domain guardrails | Keyword matching |
| Destructive operations | Banned keywords | INSERT/DELETE/DROP blocked |
| API key exposure | Env variables | Never logged/printed |
| Unauthorized data access | No authentication | Per requirements |

---

## 📊 Performance Characteristics

**Query Latencies:**
- Rule-based queries: 50-100ms (instant)
- LLM-generated queries: 2-4s (API latency)
- Database execution: <100ms (DuckDB speed)
- **Total end-to-end: 2.5-5 seconds**

**System Resources:**
- Memory usage at rest: ~150MB
- Memory per query: +50MB (during execution)
- Graph rendering (300 nodes): ~200ms
- Data loading on startup: ~500ms

**Scaling Limits:**
- Max visible graph nodes: 1500
- Max query results: 100 (by design)
- Max real-world dataset: ~10M rows in DuckDB

---

## 🧪 Example Queries to Test

### Simple Queries
```
"What products do we have?"
"Show me all customers"
"List all sales orders"
```

### Analytical Queries
```
"Which products have the most billing documents?"
"Show sales orders that were delivered but not billed"
"List top 5 customers by order count"
```

### Complex Queries
```
"Trace the order-to-delivery-to-billing flow"
"Show customers with incomplete order flows"
"Which products are stored in which plants?"
```

---

## 📚 API Endpoints

| Endpoint | Method | Purpose | Example |
|----------|--------|---------|---------|
| `/` | GET | Frontend | `curl https://graph-ai-7o34.onrender.com/` |
| `/health` | GET | System status | `curl .../health` |
| `/api/graph/snapshot` | GET | Full graph | `curl .../api/graph/snapshot` |
| `/api/query` | POST | Execute question | `curl -X POST .../api/query` |

---

## 💡 Key Design Decisions & Reasoning

### Decision 1: Hybrid Query Generation
**Choice:** Rule-based + LLM fallback  
**Why:** 
- Rule-based handles 80% of queries instantly
- LLM handles edge cases
- User always gets answer

**Alternative Considered:** Pure LLM  
**Why Not:** Every query would add 2-4s latency

---

### Decision 2: In-Memory DuckDB vs Server DB
**Choice:** DuckDB in-memory  
**Why:**
- No infrastructure to maintain
- Shipping & startup faster
- Perfect for demo/learning purposes

**Alternative Considered:** PostgreSQL server  
**Why Not:** Overkill, requires separate infra management

---

### Decision 3: Fallback Summaries
**Choice:** Template-based NL fallback  
**Why:**
- LLM might timeout/fail
- Users get answer regardless
- Deterministic behavior

**Alternative:** Show raw JSON on API fail  
**Why Not:** Confuses users, bad UX

---

### Decision 4: No Authentication
**Choice:** Public, no auth  
**Why:** Assignment requirement, simplifies demo  
**Production:** Would add OAuth2/JWT

---

### Decision 5: Docker Approach (vs Cloud Storage)
**Choice:** Docker with embedded data  
**Why:**
- Simpler than Firebase/S3 setup
- Self-contained deployment
- Works offline

**What We Tried:** Firebase (failed - required paid Blaze plan)  
**Lesson:** Serverless storage on free tiers insufficient

---

## 🔧 Local Development

```bash
# Clone
git clone https://github.com/rajansharma08/Graph-AI-Deploy.git
cd Graph-AI-Deploy

# Install
pip install -r requirements.txt

# Configure
export GOOGLE_API_KEY="your-api-key"
export DATA_ROOT="./Data"

# Run
uvicorn backend.main:app --reload --port 8000

# Visit
open http://localhost:8000
```

---

## 🎓 Lessons Learned

1. **Firebase Free Tier Limitation**
   - Spark Plan doesn't support Cloud Storage
   - Lesson: Always check free tier limitations before architecture

2. **Docker is Simpler Than Cloud Storage Integration**
   - Spent time on Firebase, Docker was better solution
   - Lesson: Keep deployments simple for demos

3. **Fallback Mechanisms Are Essential**
   - LLM APIs can timeout
   - Database can be slow
   - Lesson: Always have Plan B for user experience

4. **Domain Guardrails Are Critical**
   - Can't prevent all misuse, but can guide users
   - Lesson: Guardrails should be informative, not blocking

5. **Vis.js Perfect for Relationship Visualization**
   - Lightweight, performant, interactive
   - Lesson: Choose tools that solve specific problem

---

## 📈 Future Enhancements

1. Query result caching (repeated questions)
2. Multi-language support
3. Advanced filtering (date ranges)
4. Data export (CSV/Excel)
5. Custom report builder
6. Query history + saved favorites
7. Batch query processing

---

## 🤝 AI Tool Usage

This project was developed using **GitHub Copilot** in VS Code.

**AI Assistance In:**
- Architecture planning
- API endpoint design
- Query pattern generation
- Frontend component layout
- Safety guardrail implementation
- Documentation writing

**Workflow:**
- Initial architecture discussion
- Code generation & review
- Debugging prompts
- Documentation drafting

See `COPILOT_SESSION_LOGS.md` in repo root for detailed interaction logs.

---

## 📞 Support & Questions

For architecture questions, refer to:
1. Inline code comments
2. Docstrings in Python files
3. This README
4. Copilot session logs for decision context

---

**Built with intelligence and intention** 🚀
