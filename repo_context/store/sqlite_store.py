import json
import sqlite3
from pathlib import Path
from typing import Iterable

from repo_context.store.models import CodeEdge, CodeFile, CodeNode


class SQLiteStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        """初始化 SQLite schema；预留表只建结构，不实现业务逻辑。"""
        schema_path = Path(__file__).with_name("schema.sql")
        with self._connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))

    def insert_code_file(self, code_file: CodeFile) -> None:
        self.insert_code_files([code_file])

    def insert_code_files(self, code_files: Iterable[CodeFile]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO code_files (
                    repo_id, file_path, file_type, language, line_count, is_test
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.repo_id,
                        item.file_path,
                        item.file_type,
                        item.language,
                        item.line_count,
                        int(item.is_test),
                    )
                    for item in code_files
                ],
            )

    def insert_code_node(self, code_node: CodeNode) -> None:
        self.insert_code_nodes([code_node])

    def insert_code_nodes(self, code_nodes: Iterable[CodeNode]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO code_nodes (
                    repo_id, node_id, type, name, qualified_name, file_path,
                    start_line, end_line, signature, decorators
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.repo_id,
                        item.node_id,
                        item.type,
                        item.name,
                        item.qualified_name,
                        item.file_path,
                        item.start_line,
                        item.end_line,
                        item.signature,
                        json.dumps(item.decorators, ensure_ascii=False),
                    )
                    for item in code_nodes
                ],
            )

    def insert_code_edge(self, code_edge: CodeEdge) -> None:
        self.insert_code_edges([code_edge])

    def insert_code_edges(self, code_edges: Iterable[CodeEdge]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO code_edges (
                    repo_id, source_node_id, target_node_id, edge_type
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        item.repo_id,
                        item.source_node_id,
                        item.target_node_id,
                        item.edge_type,
                    )
                    for item in code_edges
                ],
            )

    def list_code_edges(self, repo_id: str) -> list[CodeEdge]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT repo_id, source_node_id, target_node_id, edge_type
                FROM code_edges
                WHERE repo_id = ?
                ORDER BY source_node_id, target_node_id, edge_type
                """,
                (repo_id,),
            ).fetchall()
        return [self._row_to_code_edge(row) for row in rows]

    def list_code_files(self, repo_id: str) -> list[CodeFile]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT repo_id, file_path, file_type, language, line_count, is_test
                FROM code_files
                WHERE repo_id = ?
                ORDER BY file_path
                """,
                (repo_id,),
            ).fetchall()
        return [self._row_to_code_file(row) for row in rows]

    def get_code_file(self, repo_id: str, file_path: str) -> CodeFile | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT repo_id, file_path, file_type, language, line_count, is_test
                FROM code_files
                WHERE repo_id = ? AND file_path = ?
                """,
                (repo_id, file_path),
            ).fetchone()
        return self._row_to_code_file(row) if row else None

    def list_code_nodes(self, repo_id: str) -> list[CodeNode]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT repo_id, node_id, type, name, qualified_name, file_path,
                       start_line, end_line, signature, decorators
                FROM code_nodes
                WHERE repo_id = ?
                ORDER BY file_path, start_line, qualified_name
                """,
                (repo_id,),
            ).fetchall()
        return [self._row_to_code_node(row) for row in rows]

    def get_code_node(self, repo_id: str, node_id: str) -> CodeNode | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT repo_id, node_id, type, name, qualified_name, file_path,
                       start_line, end_line, signature, decorators
                FROM code_nodes
                WHERE repo_id = ? AND node_id = ?
                """,
                (repo_id, node_id),
            ).fetchone()
        return self._row_to_code_node(row) if row else None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_code_file(row: sqlite3.Row) -> CodeFile:
        return CodeFile(
            repo_id=row["repo_id"],
            file_path=row["file_path"],
            file_type=row["file_type"],
            language=row["language"],
            line_count=row["line_count"],
            is_test=bool(row["is_test"]),
        )

    @staticmethod
    def _row_to_code_node(row: sqlite3.Row) -> CodeNode:
        return CodeNode(
            repo_id=row["repo_id"],
            node_id=row["node_id"],
            type=row["type"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            file_path=row["file_path"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            signature=row["signature"],
            decorators=json.loads(row["decorators"]),
        )

    @staticmethod
    def _row_to_code_edge(row: sqlite3.Row) -> CodeEdge:
        return CodeEdge(
            repo_id=row["repo_id"],
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            edge_type=row["edge_type"],
        )
