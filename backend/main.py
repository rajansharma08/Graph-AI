"""
FastAPI backend for O2C Graph system.
"""

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .data_layer import DataLayer
from .graph_layer import GraphLayer
from .query_engine import QueryEngine
from .schema_config import TABLE_CONFIG


# Setup paths and environment
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "Data"

load_dotenv(BASE_DIR / ".env")

# Initialize FastAPI app
app = FastAPI(title="O2C Context Graph + Query API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files from frontend directory
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


class QueryRequest(BaseModel):
    """Request body for query endpoint."""
    question: str


# Initialize data layer and load tables
data_layer = DataLayer(DATA_DIR)
load_stats = data_layer.load_tables()

# Build graph from loaded tables
row_tables: dict[str, list[dict[str, Any]]] = {}
for table in TABLE_CONFIG.keys():
    if table in load_stats:
        row_tables[table] = data_layer.execute_sql(f"SELECT * FROM {table}").to_dict(orient="records")

graph_layer = GraphLayer()
graph_layer.build_from_tables(row_tables)

# Initialize query engine
query_engine = QueryEngine(data_layer)


@app.get("/")
def root() -> FileResponse:
    """Serve the frontend HTML."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    """Health check endpoint with system stats."""
    return {
        "status": "ok",
        "tables_loaded": load_stats,
        "graph_nodes": len(graph_layer.graph.nodes),
        "graph_edges": len(graph_layer.graph.edges),
        "llm_enabled": bool(os.getenv("GOOGLE_API_KEY", "")),
    }


@app.get("/api/graph/snapshot")
def graph_snapshot(
    max_nodes: int = Query(default=300, ge=50, le=1500),
    max_edges: int = Query(default=500, ge=50, le=3000)
) -> dict[str, Any]:
    """Get a snapshot of the full graph (limited size)."""
    return graph_layer.full_snapshot(max_nodes=max_nodes, max_edges=max_edges)


@app.get("/api/graph/neighbors")
def graph_neighbors(
    node_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    max_nodes: int = Query(default=120, ge=20, le=500)
) -> dict[str, Any]:
    """Get neighbors of a node (expanding neighborhood)."""
    return graph_layer.subgraph_for_node(node_id=node_id, depth=depth, max_nodes=max_nodes)


@app.get("/api/graph/search")
def graph_search(q: str) -> dict[str, Any]:
    """Search for nodes by label or ID."""
    return {"results": graph_layer.search_nodes(q)}


@app.post("/api/query")
def ask_query(payload: QueryRequest) -> dict[str, Any]:
    """Process a natural language query."""
    res = query_engine.ask(payload.question)
    return {
        "answer": res.answer,
        "sql": res.sql,
        "rows": res.rows,
        "highlighted_nodes": res.highlighted_nodes,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
