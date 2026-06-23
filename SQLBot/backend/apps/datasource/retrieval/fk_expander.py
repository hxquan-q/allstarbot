"""Foreign-key-aware schema expansion over an abstract relation graph.

Given the set of tables that vector retrieval "hit" for a question, decide
which *additional* tables must be included so joins are possible:

* **Sphere expansion** — 1-hop FK neighbours of hits (a hit table's direct
  relations are very likely needed).
* **Bridge discovery** — for every pair of hit tables, the intermediate tables
  on the shortest FK path between them (the join bridges), up to ``max_hops``.
  Mirrors QueryWeaver's ``_find_connecting_tables`` idea, but runs over a plain
  in-memory graph so it needs no FalkorDB/Postgres graph backend.

The graph is abstract (table-name adjacency) so it works for any vendor and is
trivially unit-testable. Build it from ``CoreDatasource.table_relation`` (or
live FK introspection) at the call site.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class RelationGraph:
    """Undirected adjacency graph of table-to-table relationships."""

    _adj: dict = field(default_factory=dict)

    @classmethod
    def from_pairs(cls, pairs: Iterable) -> "RelationGraph":
        graph = cls()
        for left, right in pairs:
            graph._adj.setdefault(left, set()).add(right)
            graph._adj.setdefault(right, set()).add(left)
        return graph

    def neighbors(self, table) -> set:
        return set(self._adj.get(table, set()))

    def expand_sphere(self, hits: set, radius: int = 1) -> set:
        """Return tables within ``radius`` hops of any hit, excluding the hits
        themselves. ``radius=0`` returns the empty set."""
        if radius <= 0:
            return set()
        seen = set(hits)
        frontier = set(hits)
        for _ in range(radius):
            next_frontier = set()
            for table in frontier:
                for neighbor in self._adj.get(table, set()):
                    if neighbor not in seen:
                        seen.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return seen - set(hits)

    def bridge_tables(self, hits: set, max_hops: int = 6) -> set:
        """Intermediate tables on shortest FK paths between hit tables.

        For each hit, BFS outwards up to ``max_hops``; any *other* hit reached
        contributes the interior tables of that shortest path as bridges. A
        direct hit-to-hit neighbour contributes no bridge (its path is empty).
        """
        hits = set(hits)
        if len(hits) < 2:
            return set()

        bridges: set = set()
        for start in hits:
            # BFS recording each node's predecessor on its shortest path from start
            predecessors: dict = {start: None}
            queue = deque([start])
            hops = {start: 0}
            while queue:
                node = queue.popleft()
                if hops[node] >= max_hops:
                    continue
                for neighbor in self._adj.get(node, set()):
                    if neighbor in hops:
                        continue
                    hops[neighbor] = hops[node] + 1
                    predecessors[neighbor] = node
                    queue.append(neighbor)

            for target in hits:
                if target == start or target not in predecessors:
                    continue
                # walk the path start -> ... -> target, collecting interior nodes
                node = predecessors[target]
                while node is not None and node != start:
                    bridges.add(node)
                    node = predecessors[node]
        return bridges

    def required_tables(
        self,
        hits: set,
        sphere_radius: int = 1,
        max_bridge_hops: int = 6,
    ) -> set:
        """Union of hits, their sphere neighbours, and inter-hit bridges."""
        hits = set(hits)
        return hits | self.expand_sphere(hits, radius=sphere_radius) | self.bridge_tables(
            hits, max_hops=max_bridge_hops
        )
