from collections import deque
from pathlib import Path
from typing import Any

from repo_context.store.models import CodeEdge, CodeNode
from repo_context.store.sqlite_store import SQLiteStore


CALL_EDGE = "calls"


class ContextService:
    def __init__(self, repo_id: str, repo_root: str | Path, db_path: str | Path) -> None:
        self.repo_id = repo_id
        self.repo_root = Path(repo_root).resolve()
        self.store = SQLiteStore(db_path)

    def search_symbol(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """按关键字搜索符号和路由，返回稳定的 JSON 结构。"""
        normalized = keyword.lower()
        matches = [
            node
            for node in self.store.list_code_nodes(self.repo_id)
            if normalized in node.name.lower()
            or normalized in node.qualified_name.lower()
            or normalized in node.type.lower()
        ]
        return [self._node_summary(node) for node in matches[:limit]]

    def get_node_detail(
        self,
        node_id: str,
        include_source: bool = False,
    ) -> dict[str, Any] | None:
        node = self.store.get_code_node(self.repo_id, node_id)
        if node is None:
            return None

        detail = self._node_detail(node)
        if include_source:
            detail["source"] = self.get_file_snippet(
                node.file_path,
                node.start_line,
                node.end_line,
            )["source"]
        return detail

    def get_file_snippet(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        """读取仓库内源码片段，明确阻止仓库外路径。"""
        if start_line < 1 or end_line < start_line:
            raise ValueError("Invalid line range")

        source_path = (self.repo_root / file_path).resolve()
        if not source_path.is_relative_to(self.repo_root):
            raise ValueError(f"File path escapes repository: {file_path}")
        if not source_path.is_file():
            raise FileNotFoundError(f"File not found in repository: {file_path}")

        lines = source_path.read_text(encoding="utf-8").splitlines()
        selected = lines[start_line - 1 : end_line]
        return {
            "file_path": Path(file_path).as_posix(),
            "start_line": start_line,
            "end_line": min(end_line, len(lines)),
            "source": "\n".join(selected),
        }

    def get_callees(
        self,
        node_id: str,
        depth: int = 1,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self._walk_calls(node_id, direction="out", depth=depth, limit=limit)

    def get_callers(
        self,
        node_id: str,
        depth: int = 1,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self._walk_calls(node_id, direction="in", depth=depth, limit=limit)

    def trace_call_chain(
        self,
        source_node_id: str,
        target_node_id: str,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """查找两个节点之间的 calls 路径，找不到时返回空路径。"""
        edges = [edge for edge in self.store.list_code_edges(self.repo_id) if edge.edge_type == CALL_EDGE]
        outgoing = self._edge_map(edges, direction="out")
        node_by_id = self._nodes_by_id()

        queue: deque[tuple[str, list[str]]] = deque([(source_node_id, [source_node_id])])
        visited = {source_node_id}

        while queue:
            current_id, path = queue.popleft()
            if len(path) - 1 >= max_depth:
                continue

            for next_id in outgoing.get(current_id, []):
                if next_id in visited:
                    continue
                next_path = [*path, next_id]
                if next_id == target_node_id:
                    return {
                        "found": True,
                        "path": [
                            self._node_summary(node_by_id[node_id])
                            for node_id in next_path
                            if node_id in node_by_id
                        ],
                    }
                visited.add(next_id)
                queue.append((next_id, next_path))

        return {"found": False, "path": []}

    def explore_related_symbols(
        self,
        node_id: str,
        include_source: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """返回某节点的一跳相关节点和边。"""
        node_by_id = self._nodes_by_id()
        center = node_by_id.get(node_id)
        if center is None:
            return {"center": None, "nodes": [], "edges": []}

        related_edges = [
            edge
            for edge in self.store.list_code_edges(self.repo_id)
            if edge.source_node_id == node_id or edge.target_node_id == node_id
        ][:limit]
        related_ids = {
            edge.source_node_id for edge in related_edges if edge.source_node_id in node_by_id
        } | {
            edge.target_node_id for edge in related_edges if edge.target_node_id in node_by_id
        }

        return {
            "center": self._node_detail(center, include_source=include_source),
            "nodes": [
                self._node_detail(node_by_id[item], include_source=include_source)
                for item in sorted(related_ids)
            ],
            "edges": [self._edge_to_dict(edge) for edge in related_edges],
        }

    def get_related_context(
        self,
        node_id: str,
        include_source: bool = False,
    ) -> dict[str, Any]:
        """基础版相关上下文，阶段 6 再接入 task_id。"""
        return self.explore_related_symbols(node_id, include_source=include_source)

    def _walk_calls(
        self,
        node_id: str,
        direction: str,
        depth: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        if depth < 1 or limit < 1:
            return []

        call_edges = [
            edge for edge in self.store.list_code_edges(self.repo_id) if edge.edge_type == CALL_EDGE
        ]
        edge_map = self._edge_map(call_edges, direction=direction)
        node_by_id = self._nodes_by_id()
        results: list[dict[str, Any]] = []
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        visited = {node_id}

        while queue and len(results) < limit:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue

            for next_id in edge_map.get(current_id, []):
                if next_id in visited:
                    continue
                visited.add(next_id)
                if next_id in node_by_id:
                    results.append(self._node_summary(node_by_id[next_id]))
                if len(results) >= limit:
                    break
                queue.append((next_id, current_depth + 1))

        return results

    @staticmethod
    def _edge_map(edges: list[CodeEdge], direction: str) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        for edge in edges:
            source = edge.source_node_id if direction == "out" else edge.target_node_id
            target = edge.target_node_id if direction == "out" else edge.source_node_id
            mapping.setdefault(source, []).append(target)
        return mapping

    def _nodes_by_id(self) -> dict[str, CodeNode]:
        return {node.node_id: node for node in self.store.list_code_nodes(self.repo_id)}

    def _node_detail(
        self,
        node: CodeNode,
        include_source: bool = False,
    ) -> dict[str, Any]:
        detail = {
            **self._node_summary(node),
            "signature": node.signature,
            "decorators": list(node.decorators),
        }
        if include_source:
            detail["source"] = self.get_file_snippet(
                node.file_path,
                node.start_line,
                node.end_line,
            )["source"]
        return detail

    @staticmethod
    def _node_summary(node: CodeNode) -> dict[str, Any]:
        return {
            "node_id": node.node_id,
            "type": node.type,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "file_path": node.file_path,
            "start_line": node.start_line,
            "end_line": node.end_line,
        }

    @staticmethod
    def _edge_to_dict(edge: CodeEdge) -> dict[str, str]:
        return {
            "repo_id": edge.repo_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "edge_type": edge.edge_type,
        }
