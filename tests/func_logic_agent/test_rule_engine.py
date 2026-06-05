from __future__ import annotations

from func_logic_agent.config import AgentConfig
from func_logic_agent.rules.rule_engine import RuleEngine


def _make_config(**overrides) -> AgentConfig:
    return AgentConfig(repo_id="test", **overrides)


class TestR1GraphComplexity:
    def test_trivial_graph_flagged(self, sample_task_package, sample_graph_slice):
        engine = RuleEngine(_make_config())
        # Reduce to 2 nodes
        sample_graph_slice["nodes"] = sample_graph_slice["nodes"][:2]
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "trivial_graph" in result.rule_flags

    def test_complex_graph_flagged(self, sample_task_package, sample_graph_slice):
        engine = RuleEngine(_make_config(graph_node_count_high=2))
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "complex_graph" in result.rule_flags
        assert any("nodes" in f.lower() for f in result.focus_areas)

    def test_normal_graph_no_flag(self, sample_task_package, sample_graph_slice):
        engine = RuleEngine(_make_config(graph_node_count_high=100))
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "trivial_graph" not in result.rule_flags
        assert "complex_graph" not in result.rule_flags


class TestR2HighRiskNodes:
    def test_detects_high_risk(self, sample_task_package, sample_graph_slice):
        engine = RuleEngine(_make_config(risk_score_threshold=30))
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "high_risk_nodes_present" in result.rule_flags
        assert result.priority_boost > 0
        assert any("login" in f for f in result.focus_areas)

    def test_no_risk_when_below_threshold(self, sample_task_package, sample_graph_slice):
        engine = RuleEngine(_make_config(risk_score_threshold=100))
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "high_risk_nodes_present" not in result.rule_flags


class TestR3DeepCallChain:
    def test_deep_chain_flagged(self, sample_task_package, sample_graph_slice):
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "deep_call_chain" in result.rule_flags

    def test_no_deep_chain(self, sample_task_package, sample_graph_slice):
        # Remove indirect node
        sample_graph_slice["nodes"] = [
            n for n in sample_graph_slice["nodes"]
            if n.get("relation_to_target") != "indirect"
        ]
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "deep_call_chain" not in result.rule_flags


class TestR4BoundaryRisk:
    def test_boundary_risk_detected(self, sample_task_package, sample_graph_slice):
        sample_graph_slice["boundary_nodes"] = [
            {"name": "external_api", "risk_score": 60, "node_id": "ext.1"}
        ]
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "risk_at_boundary" in result.rule_flags
        assert result.priority_boost > 0

    def test_no_boundary_risk(self, sample_task_package, sample_graph_slice):
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "risk_at_boundary" not in result.rule_flags


class TestR5ErrorPath:
    def test_io_without_error_handling(self, sample_task_package, sample_graph_slice):
        sample_graph_slice["nodes"] = [
            {
                "node_id": "db.query",
                "name": "execute_query",
                "type": "function",
                "relation_to_target": "direct_callee",
                "priority": 70,
                "risk_score": 0,
                "reason": "database query",
            }
        ]
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "potential_missing_error_handling" in result.rule_flags


class TestR6TaskTypeFocus:
    def test_entrypoint_focus(self, sample_task_package, sample_graph_slice):
        sample_graph_slice["nodes"] = sample_graph_slice["nodes"][:1]
        sample_graph_slice["boundary_nodes"] = []
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "Input validation flow" in result.focus_areas

    def test_module_focus(self, sample_task_package, sample_graph_slice):
        sample_task_package["task_type"] = "module_review"
        sample_graph_slice["nodes"] = sample_graph_slice["nodes"][:1]
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "Return value contracts" in result.focus_areas


class TestR7SkipTrivial:
    def test_skip_low_priority_trivial(self, sample_task_package, sample_graph_slice):
        sample_task_package["task_type"] = "file_review"
        sample_task_package["priority"] = "low"
        sample_graph_slice["nodes"] = sample_graph_slice["nodes"][:2]
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert result.should_skip is True
        assert result.skip_reason is not None

    def test_no_skip_high_priority(self, sample_task_package, sample_graph_slice):
        sample_task_package["task_type"] = "file_review"
        sample_task_package["priority"] = "high"
        sample_graph_slice["nodes"] = sample_graph_slice["nodes"][:2]
        engine = RuleEngine(_make_config())
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert result.should_skip is False


class TestRulesAreAdditive:
    def test_multiple_flags_accumulate(self, sample_task_package, sample_graph_slice):
        sample_graph_slice["boundary_nodes"] = [
            {"name": "risky_ext", "risk_score": 50, "node_id": "ext.1"}
        ]
        engine = RuleEngine(_make_config(risk_score_threshold=30))
        result = engine.screen(sample_task_package, sample_graph_slice)
        assert "high_risk_nodes_present" in result.rule_flags
        assert "deep_call_chain" in result.rule_flags
        assert "risk_at_boundary" in result.rule_flags
        assert result.priority_boost > 10
