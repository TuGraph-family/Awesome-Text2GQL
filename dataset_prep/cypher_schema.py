from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable

from app.impl.oracle_sqlpgq.utils.sqlpgq import OracleNameSanitizer

IGNORED_PROPERTY_REFERENCE_NAMESPACES = {
    "apoc",
    "date",
    "datetime",
    "duration",
    "localdatetime",
    "localtime",
    "time",
}


@dataclass(frozen=True)
class CypherSchemaIssue:
    signature: str
    message: str


class CypherSchema:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.schema = list(config.get("schema") or [])
        self.vertices = [item for item in self.schema if item.get("type") == "VERTEX"]
        self.edges = [item for item in self.schema if item.get("type") == "EDGE"]
        self.node_props = {
            item.get("label"): {
                prop.get("name") for prop in item.get("properties", []) if prop.get("name")
            }
            for item in self.vertices
        }
        self.edge_props = {
            item.get("label"): {
                prop.get("name") for prop in item.get("properties", []) if prop.get("name")
            }
            for item in self.edges
        }
        self.property_types_by_label = {
            item.get("label"): {
                prop.get("name"): prop.get("type", "STRING")
                for prop in item.get("properties", [])
                if prop.get("name")
            }
            for item in self.schema
        }
        self.edge_constraints = {
            item.get("label"): {
                (constraint[0], constraint[1])
                for constraint in item.get("constraints", [])
                if isinstance(constraint, list) and len(constraint) == 2
            }
            for item in self.edges
        }
        self.node_primary = {
            item.get("label"): item.get("primary", "_id") for item in self.vertices
        }
        self.node_label_aliases = self._schema_name_aliases(self.node_props)
        self.edge_label_aliases = self._schema_name_aliases(self.edge_props)
        self.property_aliases_by_label = {
            label: self._schema_name_aliases(properties)
            for label, properties in self.property_types_by_label.items()
        }
        self.global_property_aliases = self._global_property_aliases()

    @classmethod
    def from_path(cls, path: Path) -> CypherSchema:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def validation_issues(self, query: str) -> list[CypherSchemaIssue]:
        query = str(query or "")
        issues: list[CypherSchemaIssue] = []
        node_variables, edge_variables = cypher_variable_labels(query)
        for variable, label in node_variables.items():
            if self.canonical_node_label(label) not in self.node_props:
                issues.append(
                    CypherSchemaIssue(
                        "invalid_schema_label",
                        f'Node label "{label}" for variable "{variable}" is not in schema.',
                    )
                )
        for variable, label in edge_variables.items():
            if self.canonical_edge_label(label) not in self.edge_props:
                issues.append(
                    CypherSchemaIssue(
                        "invalid_schema_label",
                        f'Edge label "{label}" for variable "{variable}" is not in schema.',
                    )
                )
        for left_label, direction, edge_labels, right_label in cypher_edge_triples(query):
            if direction == "undirected":
                continue
            left = self.canonical_node_label(left_label)
            right = self.canonical_node_label(right_label)
            for edge_label in edge_labels:
                edge = self.canonical_edge_label(edge_label)
                constraints = self.edge_constraints.get(edge)
                if not constraints or not left or not right:
                    continue
                expected = (left, right) if direction == "right" else (right, left)
                if expected not in constraints:
                    issues.append(
                        CypherSchemaIssue(
                            "invalid_schema_direction",
                            (
                                f'Edge "{edge_label}" does not allow {left_label} '
                                f"{direction} {right_label}."
                            ),
                        )
                    )
                    break
        for variable, property_name in cypher_property_references(query):
            if variable.lower() in IGNORED_PROPERTY_REFERENCE_NAMESPACES:
                continue
            if variable in node_variables:
                label = self.canonical_node_label(node_variables[variable])
                if not self._valid_node_property(query, variable, label, property_name):
                    issues.append(
                        CypherSchemaIssue(
                            "invalid_schema_property",
                            f'Property "{property_name}" is not valid for node "{variable}".',
                        )
                    )
            elif variable in edge_variables:
                label = self.canonical_edge_label(edge_variables[variable])
                if not self._valid_edge_property(label, property_name):
                    issues.append(
                        CypherSchemaIssue(
                            "invalid_schema_property",
                            f'Property "{property_name}" is not valid for edge "{variable}".',
                        )
                    )
            elif property_name.lower() in {"identity", "id"}:
                issues.append(
                    CypherSchemaIssue(
                        "invalid_schema_property",
                        f'Cannot resolve pseudo-property "{property_name}" for "{variable}".',
                    )
                )
            elif not self._property_known_anywhere(property_name):
                issues.append(
                    CypherSchemaIssue(
                        "invalid_schema_property",
                        f'Cannot resolve property "{property_name}" for "{variable}".',
                    )
                )
        issues.extend(self.unsafe_numeric_issues(query))
        return _dedupe_issues(issues)

    def unsafe_numeric_issues(self, query: str) -> list[CypherSchemaIssue]:
        issues: list[CypherSchemaIssue] = []
        node_variables, edge_variables = cypher_variable_labels(query)
        variables = {**node_variables, **edge_variables}
        for match in re.finditer(
            r"\bto(?:Integer|Float)\s*\(\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<prop>[A-Za-z_][A-Za-z0-9_$#-]*)\s*\)",
            mask_string_literals(query),
            flags=re.IGNORECASE,
        ):
            variable = match.group("var")
            property_name = self.canonical_property_name(variable, match.group("prop"), variables)
            property_type = self.property_type(variable, property_name, variables)
            if self._is_string_type(property_type) and self._looks_unsafe_numeric_text_property(
                property_name
            ):
                issues.append(
                    CypherSchemaIssue(
                        "unsafe_numeric_conversion",
                        f'Unsafe numeric conversion for "{variable}.{property_name}".',
                    )
                )
        property_ref = (
            r"(?P<{prefix}_var>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<{prefix}_prop>[A-Za-z_][A-Za-z0-9_$#-]*)"
        )
        comparison = re.compile(
            property_ref.format(prefix="left")
            + r"\s*(?P<operator><=|>=|<|>)\s*"
            + property_ref.format(prefix="right"),
            flags=re.IGNORECASE,
        )
        for match in comparison.finditer(mask_string_literals(query)):
            left_type = self.property_type(
                match.group("left_var"),
                self.canonical_property_name(
                    match.group("left_var"), match.group("left_prop"), variables
                ),
                variables,
            )
            right_type = self.property_type(
                match.group("right_var"),
                self.canonical_property_name(
                    match.group("right_var"), match.group("right_prop"), variables
                ),
                variables,
            )
            if (
                self._is_temporal_type(left_type)
                and self._is_numeric_type(right_type)
                or self._is_numeric_type(left_type)
                and self._is_temporal_type(right_type)
            ):
                issues.append(
                    CypherSchemaIssue(
                        "unsafe_temporal_numeric_comparison",
                        "Temporal and numeric properties are compared directly.",
                    )
                )
        aggregate_ref = re.compile(
            r"\b(?P<function>AVG|SUM|MIN|MAX)\s*\(\s*"
            + property_ref.format(prefix="arg")
            + r"\s*\)",
            flags=re.IGNORECASE,
        )
        aggregate_matches = list(aggregate_ref.finditer(mask_string_literals(query)))
        for match in aggregate_matches:
            variable = match.group("arg_var")
            if variable not in variables:
                continue
            property_name = self.canonical_property_name(
                variable,
                match.group("arg_prop"),
                variables,
            )
            property_type = self.property_type(variable, property_name, variables)
            if self._is_unsafe_numeric_text_property(property_name, property_type):
                issues.append(
                    CypherSchemaIssue(
                        "unsafe_numeric_conversion",
                        f'Unsafe numeric aggregate over "{variable}.{property_name}".',
                    )
                )
        if self._has_arithmetic_between_temporal_aggregates(query, aggregate_matches, variables):
            issues.append(
                CypherSchemaIssue(
                    "unsafe_temporal_arithmetic",
                    "Temporal aggregate arithmetic requires explicit numeric conversion.",
                )
            )
        for variable, property_name in cypher_property_references(query):
            if variable not in variables:
                continue
            canonical_property = self.canonical_property_name(variable, property_name, variables)
            property_type = self.property_type(variable, canonical_property, variables)
            if not self._is_unsafe_numeric_text_property(canonical_property, property_type):
                continue
            if self._property_reference_has_numeric_operator(query, variable, property_name):
                issues.append(
                    CypherSchemaIssue(
                        "unsafe_numeric_conversion",
                        f'Unsafe numeric arithmetic over "{variable}.{canonical_property}".',
                    )
                )
        return issues

    def canonical_node_label(self, label: str) -> str:
        return self._canonical_schema_name(label, self.node_label_aliases)

    def canonical_edge_label(self, label: str) -> str:
        return self._canonical_schema_name(label, self.edge_label_aliases)

    def canonical_property_name(
        self,
        variable: str,
        property_name: str,
        variables: dict[str, str],
    ) -> str:
        label = variables.get(variable, "")
        if not label:
            return self._canonical_schema_name(property_name, self.global_property_aliases)
        canonical_label = (
            self.canonical_node_label(label)
            if label in self.node_label_aliases or label in self.node_props
            else self.canonical_edge_label(label)
        )
        primary = self.node_primary.get(canonical_label, "")
        if property_name.lower() in {"identity", "id"} and primary:
            return primary
        aliases = self.property_aliases_by_label.get(canonical_label, {})
        canonical = self._canonical_schema_name(property_name, aliases)
        if canonical != property_name:
            return canonical
        return self._canonical_schema_name(property_name, self.global_property_aliases)

    def property_type(
        self,
        variable: str,
        property_name: str,
        variables: dict[str, str],
    ) -> str:
        label = variables.get(variable, "")
        if not label:
            return ""
        labels = [self.canonical_node_label(label), self.canonical_edge_label(label)]
        for candidate in labels:
            properties = self.property_types_by_label.get(candidate, {})
            if property_name in properties:
                return properties[property_name]
            canonical = self._canonical_schema_name(
                property_name,
                self.property_aliases_by_label.get(candidate, {}),
            )
            if canonical in properties:
                return properties[canonical]
        return ""

    def redirected_property_target(
        self,
        query: str,
        variable: str,
        property_name: str,
    ) -> tuple[str, str]:
        node_variables, edge_variables = cypher_variable_labels(query)
        if variable not in node_variables:
            return "", ""
        candidates: set[tuple[str, str]] = set()
        for left_var, edge_var, right_var in cypher_variable_edge_adjacencies(query):
            if variable not in {left_var, right_var} or edge_var not in edge_variables:
                continue
            edge_label = self.canonical_edge_label(edge_variables[edge_var])
            canonical_property = self._canonical_schema_name(
                property_name,
                self.property_aliases_by_label.get(edge_label, {}),
            )
            if canonical_property in self.edge_props.get(edge_label, set()):
                candidates.add((edge_var, canonical_property))
        if len(candidates) == 1:
            return next(iter(candidates))
        return "", ""

    def _valid_node_property(
        self,
        query: str,
        variable: str,
        label: str,
        property_name: str,
    ) -> bool:
        if property_name.lower() in {"identity", "id"}:
            return bool(self.node_primary.get(label))
        canonical = self._canonical_schema_name(
            property_name,
            self.property_aliases_by_label.get(label, {}),
        )
        if canonical in self.node_props.get(label, set()):
            return True
        redirect_variable, _redirect_property = self.redirected_property_target(
            query,
            variable,
            property_name,
        )
        return bool(redirect_variable)

    def _valid_edge_property(self, label: str, property_name: str) -> bool:
        if property_name.lower() in {"identity", "id"}:
            return True
        canonical = self._canonical_schema_name(
            property_name,
            self.property_aliases_by_label.get(label, {}),
        )
        return canonical in self.edge_props.get(label, set())

    def _property_known_anywhere(self, property_name: str) -> bool:
        aliases = {
            property_name,
            OracleNameSanitizer.clean(property_name, fallback=property_name),
            re.sub(r"(?<!^)(?=[A-Z])", "_", str(property_name or "")).lower(),
            str(property_name or "").lower(),
        }
        for properties in self.property_types_by_label.values():
            property_aliases = self._schema_name_aliases(properties)
            if any(alias in property_aliases for alias in aliases):
                return True
        return False

    def _schema_name_aliases(self, names: Iterable[str]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for name in names:
            cleaned = OracleNameSanitizer.clean(name, fallback=name)
            for alias in {name, cleaned, name.lower(), cleaned.lower()}:
                aliases.setdefault(alias, name)
        return aliases

    def _global_property_aliases(self) -> dict[str, str]:
        candidates: dict[str, set[str]] = {}
        for properties in self.property_types_by_label.values():
            for property_name in properties:
                cleaned = OracleNameSanitizer.clean(property_name, fallback=property_name)
                snake = re.sub(r"(?<!^)(?=[A-Z])", "_", property_name).lower()
                for alias in {
                    property_name,
                    cleaned,
                    snake,
                    property_name.lower(),
                    cleaned.lower(),
                }:
                    candidates.setdefault(alias, set()).add(property_name)
        return {alias: next(iter(names)) for alias, names in candidates.items() if len(names) == 1}

    def _canonical_schema_name(self, name: str, aliases: dict[str, str]) -> str:
        if not name:
            return ""
        cleaned = OracleNameSanitizer.clean(name, fallback=name)
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(name or "")).lower()
        return (
            aliases.get(name)
            or aliases.get(cleaned)
            or aliases.get(snake)
            or aliases.get(str(name).lower())
            or aliases.get(cleaned.lower())
            or name
        )

    def _looks_unsafe_numeric_text_property(self, property_name: str) -> bool:
        lower = property_name.lower()
        return any(
            token in lower
            for token in [
                "percent",
                "percentage",
                "sla",
                "requirement",
                "embedding",
                "vector",
                "list",
                "array",
            ]
        )

    def _is_unsafe_numeric_text_property(self, property_name: str, property_type: str) -> bool:
        return self._is_string_type(property_type) and self._looks_unsafe_numeric_text_property(
            property_name
        )

    def _property_reference_has_numeric_operator(
        self,
        query: str,
        variable: str,
        property_name: str,
    ) -> bool:
        protected = mask_string_literals(query)
        reference = (
            rf"\b{re.escape(variable)}\."
            rf"(?:`{re.escape(property_name)}`|{re.escape(property_name)})\b"
        )
        return bool(
            re.search(reference + r"\s*[-+*/%]", protected)
            or re.search(r"[-+*/%]\s*" + reference, protected)
        )

    def _has_arithmetic_between_temporal_aggregates(
        self,
        query: str,
        aggregate_matches: list[re.Match],
        variables: dict[str, str],
    ) -> bool:
        protected = mask_string_literals(query)
        temporal_spans = []
        for match in aggregate_matches:
            variable = match.group("arg_var")
            property_name = self.canonical_property_name(
                variable,
                match.group("arg_prop"),
                variables,
            )
            if self._is_temporal_type(self.property_type(variable, property_name, variables)):
                temporal_spans.append(match.span())
        for _left_start, left_end in temporal_spans:
            for right_start, _right_end in temporal_spans:
                if left_end > right_start:
                    continue
                between = protected[left_end:right_start]
                if re.fullmatch(r"\s*[-+]\s*", between):
                    return True
        return False

    def _is_string_type(self, type_name: str) -> bool:
        return (
            "CHAR" in type_name.upper()
            or "STRING" in type_name.upper()
            or "TEXT" in type_name.upper()
        )

    def _is_temporal_type(self, type_name: str) -> bool:
        upper = type_name.upper()
        return "DATE" in upper or "TIME" in upper

    def _is_numeric_type(self, type_name: str) -> bool:
        upper = type_name.upper()
        return any(token in upper for token in ["INT", "NUMBER", "FLOAT", "DOUBLE", "DECIMAL"])


def cypher_variable_labels(query: str) -> tuple[dict[str, str], dict[str, str]]:
    node_labels: dict[str, str] = {}
    edge_labels: dict[str, str] = {}
    for match in re.finditer(
        r"\(\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*"
        r"(?:`(?P<quoted>[^`]+)`|(?P<label>[A-Za-z_][A-Za-z0-9_$#-]*))",
        query,
    ):
        variable = match.group("var")
        if variable:
            node_labels[variable] = _clean_schema_name(
                match.group("quoted") or match.group("label")
            )
    for match in re.finditer(
        r"\[\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*"
        r"(?:`(?P<quoted>[^`]+)`|(?P<label>[A-Za-z_][A-Za-z0-9_$#|.-]*))",
        query,
    ):
        variable = match.group("var")
        if variable:
            edge_labels[variable] = _clean_schema_name(
                match.group("quoted") or match.group("label")
            )
    return node_labels, edge_labels


def cypher_property_references(query: str) -> list[tuple[str, str]]:
    protected = mask_string_literals(query)
    references = []
    for match in re.finditer(
        r"\b(?P<var>[A-Za-z_][A-Za-z0-9_]*)\."
        r"(?:`(?P<quoted>[^`]+)`|(?P<bare>[A-Za-z_][A-Za-z0-9_$#-]*))",
        protected,
    ):
        references.append(
            (match.group("var"), _clean_schema_name(match.group("quoted") or match.group("bare")))
        )
    return references


def cypher_edge_triples(query: str) -> list[tuple[str, str, list[str], str]]:
    node = (
        r"\(\s*(?:[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*"
        r"(?:`(?P<NAME_Q>[^`]+)`|(?P<NAME>[A-Za-z_][A-Za-z0-9_$#.-]*))"
        r"(?:\s*\{[^}]*\})?\s*\)"
    )
    edge = (
        r"\[\s*(?:[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*"
        r"(?P<edge>`[^`]+`|[A-Za-z_][A-Za-z0-9_$#.-]*"
        r"(?:\s*\|\s*(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$#.-]*))*)"
        r"(?:\s*\{[^}]*\})?\s*(?:\*\s*(?:\d+\s*)?(?:\.\.\s*\d*)?)?\s*\]"
    )
    triples = []
    patterns = [
        (
            "right",
            node.replace("NAME", "left")
            + r"\s*-\s*"
            + edge
            + r"\s*->\s*"
            + node.replace("NAME", "right"),
        ),
        (
            "left",
            node.replace("NAME", "left")
            + r"\s*<-\s*"
            + edge
            + r"\s*-\s*"
            + node.replace("NAME", "right"),
        ),
        (
            "undirected",
            node.replace("NAME", "left")
            + r"\s*-\s*"
            + edge
            + r"\s*-\s*"
            + node.replace("NAME", "right"),
        ),
    ]
    for direction, pattern in patterns:
        for match in re.finditer(pattern, query):
            left = match.group("left_Q") or match.group("left")
            right = match.group("right_Q") or match.group("right")
            edge_labels = [
                _clean_schema_name(item)
                for item in re.split(r"\s*\|\s*", match.group("edge"))
                if item.strip()
            ]
            triples.append(
                (_clean_schema_name(left), direction, edge_labels, _clean_schema_name(right))
            )
    return triples


def cypher_variable_edge_adjacencies(query: str) -> list[tuple[str, str, str]]:
    node = r"\(\s*(?P<NODE>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^)]*)?\)"
    edge = r"\[\s*(?P<EDGE>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^\]]*)?\]"
    adjacencies = []
    for pattern in (
        node.replace("NODE", "left")
        + r"\s*-\s*"
        + edge
        + r"\s*->?\s*"
        + node.replace("NODE", "right"),
        node.replace("NODE", "left")
        + r"\s*<-\s*"
        + edge
        + r"\s*-\s*"
        + node.replace("NODE", "right"),
    ):
        for match in re.finditer(pattern, query):
            adjacencies.append((match.group("left"), match.group("EDGE"), match.group("right")))
    return adjacencies


def mask_string_literals(query: str) -> str:
    return re.sub(r"'(?:''|\\'|[^'])*'|\"(?:\\\"|[^\"])*\"", "''", query or "")


def _clean_schema_name(value: str) -> str:
    return str(value or "").strip().strip("`").strip('"')


def _dedupe_issues(issues: list[CypherSchemaIssue]) -> list[CypherSchemaIssue]:
    seen = set()
    deduped = []
    for issue in issues:
        key = (issue.signature, issue.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped
