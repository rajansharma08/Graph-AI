"""
Graph layer for building and querying the entity relationship graph.
"""

from collections import deque
from typing import Any

import networkx as nx

from .schema_config import NODE_LABEL_HINTS, TABLE_CONFIG


def _make_key(parts: list[Any]) -> str:
    """Create a compound key from parts."""
    return "|".join([str(p) for p in parts])


def make_node_id(table: str, pk_values: list[Any]) -> str:
    """Create a unique node ID from table name and primary key values."""
    return f"{table}:{_make_key(pk_values)}"


class GraphLayer:
    def __init__(self):
        self.graph = nx.DiGraph()

    def build_from_tables(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        """Build the graph from loaded table data."""
        # First pass: create all nodes
        for table, cfg in TABLE_CONFIG.items():
            rows = tables.get(table, [])
            if not rows:
                continue

            pk = cfg["pk"]
            label_col = NODE_LABEL_HINTS.get(table)
            for row in rows:
                pk_values = [row.get(c) for c in pk]
                # Skip rows with missing PK values
                if any(v is None or v == "" for v in pk_values):
                    continue
                node_id = make_node_id(table, pk_values)
                # Use label column if available, otherwise use first PK value
                label = str(row.get(label_col)) if label_col and row.get(label_col) else str(pk_values[0])
                self.graph.add_node(
                    node_id,
                    table=table,
                    label=label,
                    pk={k: row.get(k) for k in pk},
                    metadata=row,
                )

        # Second pass: create edges via foreign keys
        for table, cfg in TABLE_CONFIG.items():
            rows = tables.get(table, [])
            if not rows:
                continue

            source_pk = cfg["pk"]
            for row in rows:
                source_vals = [row.get(c) for c in source_pk]
                if any(v is None or v == "" for v in source_vals):
                    continue
                source_id = make_node_id(table, source_vals)

                for fk in cfg["fks"]:
                    from_cols = fk["from"]
                    to_table = fk["to_table"]
                    to_cols = fk["to"]
                    rel = fk["rel"]

                    fk_vals = [row.get(c) for c in from_cols]
                    if any(v is None or v == "" for v in fk_vals):
                        continue

                    # Map FK values to target PK ordering
                    to_pk = TABLE_CONFIG[to_table]["pk"]
                    target_key_map = dict(zip(to_cols, fk_vals))
                    ordered_target_vals = [target_key_map.get(pk_col) for pk_col in to_pk]
                    if any(v is None or v == "" for v in ordered_target_vals):
                        continue

                    target_id = make_node_id(to_table, ordered_target_vals)
                    if self.graph.has_node(target_id):
                        self.graph.add_edge(source_id, target_id, relationship=rel, from_table=table, to_table=to_table)

    def subgraph_for_node(self, node_id: str, depth: int = 1, max_nodes: int = 120) -> dict[str, Any]:
        """Get a subgraph around a node (both successors and predecessors)."""
        if not self.graph.has_node(node_id):
            return {"nodes": [], "edges": []}

        visited = set([node_id])
        q = deque([(node_id, 0)])

        while q and len(visited) < max_nodes:
            cur, d = q.popleft()
            if d >= depth:
                continue
            # Include both outgoing and incoming edges
            neighbors = list(self.graph.successors(cur)) + list(self.graph.predecessors(cur))
            for n in neighbors:
                if n not in visited:
                    visited.add(n)
                    q.append((n, d + 1))
                if len(visited) >= max_nodes:
                    break

        sg = self.graph.subgraph(visited)
        return self._to_vis_payload(sg)

    def full_snapshot(self, max_nodes: int = 300, max_edges: int = 500) -> dict[str, Any]:
        """Get a snapshot of the full graph (limited by max_nodes and max_edges)."""
        node_ids = list(self.graph.nodes())[:max_nodes]
        sg = self.graph.subgraph(node_ids).copy()

        edges = list(sg.edges(data=True))[:max_edges]
        trimmed = nx.DiGraph()
        trimmed.add_nodes_from(sg.nodes(data=True))
        trimmed.add_edges_from(edges)
        return self._to_vis_payload(trimmed)

    def search_nodes(self, term: str, limit: int = 15) -> list[dict[str, Any]]:
        """Search for nodes by label or ID."""
        t = term.lower().strip()
        out = []
        for node_id, attrs in self.graph.nodes(data=True):
            text = f"{node_id} {attrs.get('label', '')}".lower()
            if t in text:
                out.append({"id": node_id, "label": attrs.get("label", node_id), "table": attrs.get("table")})
            if len(out) >= limit:
                break
        return out

    def _to_vis_payload(self, g: nx.DiGraph) -> dict[str, Any]:
        """Convert a NetworkX graph to vis-network JSON payload."""
        nodes = []
        edges = []
        for node_id, attrs in g.nodes(data=True):
            nodes.append(
                {
                    "id": node_id,
                    "label": attrs.get("label", node_id),
                    "table": attrs.get("table", "unknown"),
                    "metadata": attrs.get("metadata", {}),
                }
            )
        for src, dst, attrs in g.edges(data=True):
            edges.append(
                {
                    "from": src,
                    "to": dst,
                    "label": attrs.get("relationship", "rel"),
                    "fromTable": attrs.get("from_table", ""),
                    "toTable": attrs.get("to_table", ""),
                }
            )
        return {"nodes": nodes, "edges": edges}
