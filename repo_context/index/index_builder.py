from dataclasses import dataclass
from pathlib import Path

from repo_context.ingest.file_scanner import scan_repo
from repo_context.parser.ast_parser import parse_python_file
from repo_context.store.models import CodeEdge, CodeFile, CodeNode
from repo_context.store.sqlite_store import SQLiteStore


@dataclass(frozen=True)
class IndexBuildResult:
    repo_id: str
    db_path: str
    file_count: int
    node_count: int
    edge_count: int


def build_index(repo_id: str, repo_path: str | Path, db_path: str | Path) -> IndexBuildResult:
    """串联扫描、AST 解析和 SQLite 写入，不生成任务或覆盖率。"""
    root = Path(repo_path).resolve()
    store = SQLiteStore(db_path)
    store.init_db()

    scanned_files = scan_repo(root)
    store.insert_code_files(
        CodeFile(
            repo_id=repo_id,
            file_path=item.file_path,
            file_type=item.file_type,
            language=item.language,
            line_count=item.line_count,
            is_test=item.is_test,
        )
        for item in scanned_files
    )

    node_count = 0
    edge_count = 0
    for code_file in scanned_files:
        parse_result = parse_python_file(root / code_file.file_path, root)
        # 语法错误由解析阶段记录；阶段 3 只写入成功解析出的节点。
        code_nodes = [
            CodeNode(
                repo_id=repo_id,
                node_id=node.node_id,
                type=node.type,
                name=node.name,
                qualified_name=node.qualified_name,
                file_path=node.file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                signature=node.signature,
                decorators=node.decorators,
            )
            for node in parse_result.nodes
        ]
        store.insert_code_nodes(code_nodes)

        contains_edges = _build_contains_edges(repo_id, code_nodes)
        store.insert_code_edges(contains_edges)

        node_count += len(code_nodes)
        edge_count += len(contains_edges)

    return IndexBuildResult(
        repo_id=repo_id,
        db_path=str(Path(db_path)),
        file_count=len(scanned_files),
        node_count=node_count,
        edge_count=edge_count,
    )


def _build_contains_edges(repo_id: str, nodes: list[CodeNode]) -> list[CodeEdge]:
    """构建 module/class 到下级节点的包含关系；调用边留到阶段 4。"""
    by_qualified_name = {node.qualified_name: node for node in nodes}
    edges: list[CodeEdge] = []

    for node in nodes:
        if node.type == "module":
            continue

        parent_name = node.qualified_name.rsplit(".", 1)[0]
        parent = by_qualified_name.get(parent_name)
        if parent is None:
            continue

        edges.append(
            CodeEdge(
                repo_id=repo_id,
                source_node_id=parent.node_id,
                target_node_id=node.node_id,
                edge_type="contains",
            )
        )

    return edges
