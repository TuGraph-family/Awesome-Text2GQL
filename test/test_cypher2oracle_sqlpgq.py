from app.core.clauses.match_clause import MatchClause
from app.impl.tugraph_cypher.ast_visitor.tugraph_cypher_ast_visitor import (
    TugraphCypherAstVisitor,
)
from examples.cypher2oracle_sqlpgq import cypher2oracle_sqlpgq


def _translate(cypher: str) -> str:
    query, category = cypher2oracle_sqlpgq(cypher, graph_name="MOVIE_GRAPH")

    assert category == "Graph-IL Translatable"
    assert query.startswith("SELECT")
    assert "FROM GRAPH_TABLE" in query
    assert '"MOVIE_GRAPH"' in query
    return query


def _translate_with_types(
    cypher: str,
    property_type_map: dict[str, dict[str, str]],
) -> str:
    query, category = cypher2oracle_sqlpgq(
        cypher,
        graph_name="MOVIE_GRAPH",
        property_type_map=property_type_map,
    )

    assert category == "Graph-IL Translatable"
    return query


def _translate_sql(cypher: str) -> str:
    query, category = cypher2oracle_sqlpgq(cypher, graph_name="MOVIE_GRAPH")

    assert category == "Graph-IL Translatable"
    assert "FROM GRAPH_TABLE" in query
    assert '"MOVIE_GRAPH"' in query
    return query


def test_cypher2oracle_sqlpgq_translates_simple_node_return_property():
    query = _translate("MATCH (p:PERSON) RETURN p.name AS person_name")

    assert 'MATCH (p IS "PERSON")' in query
    assert 'COLUMNS (p."name" AS person_name)' in query


def test_cypher_ast_marks_optional_match_clause():
    visitor = TugraphCypherAstVisitor()

    success, optional_pattern = visitor.get_query_pattern("OPTIONAL MATCH (a)-->(b) RETURN b")
    assert success
    optional_match = next(clause for clause in optional_pattern if isinstance(clause, MatchClause))
    assert optional_match.optional

    success, regular_pattern = visitor.get_query_pattern("MATCH (a)-->(b) RETURN b")
    assert success
    regular_match = next(clause for clause in regular_pattern if isinstance(clause, MatchClause))
    assert not regular_match.optional


def test_cypher2oracle_sqlpgq_translates_directed_edge_and_where():
    query = _translate(
        "MATCH (p:PERSON)-[a:ACTED_IN]->(m:MOVIE) "
        "WHERE p.name = 'Tom Hanks' "
        "RETURN m.title AS movie_title"
    )

    assert 'MATCH (p IS "PERSON")-[a IS "ACTED_IN"]->(m IS "MOVIE")' in query
    assert "WHERE p.\"name\" = 'Tom Hanks'" in query
    assert 'COLUMNS (m."title" AS movie_title)' in query


def test_cypher2oracle_sqlpgq_translates_order_skip_limit():
    query = _translate(
        "MATCH (p:PERSON) RETURN p.name AS person_name ORDER BY p.name ASC SKIP 5 LIMIT 10"
    )

    assert "ORDER BY person_name ASC" in query
    assert "OFFSET 5 ROWS" in query
    assert "FETCH FIRST 10 ROWS ONLY" in query


def test_cypher2oracle_sqlpgq_wraps_distinct_hidden_sort_columns():
    query = _translate_sql(
        "MATCH (r:RULE)<-[mr:MATCHED_RULE]-(t:TRANSACTION) "
        "RETURN DISTINCT r ORDER BY r.created_at ASC"
    )

    assert "SELECT DISTINCT r_VALUE, created_at" in query
    assert "SELECT r_VALUE\nFROM (" in query
    assert "ORDER BY created_at ASC" in query


def test_cypher2oracle_sqlpgq_translates_variable_length_relationship():
    query = _translate(
        "MATCH (person:PERSON)-[:KNOWS*..3]->(friend:PERSON) RETURN friend.name AS friend_name"
    )

    assert '[e1 IS "KNOWS"]->{1,3}' in query
    assert 'COLUMNS (friend."name" AS friend_name)' in query


def test_cypher2oracle_sqlpgq_translates_whole_node_return_to_vertex_id():
    query = _translate("MATCH (p:PERSON) RETURN p")

    assert "COLUMNS (VERTEX_ID(p) AS p_VALUE)" in query


def test_cypher2oracle_sqlpgq_expands_named_path_return_to_element_ids():
    query = _translate(
        "MATCH p = (n1:ACCOUNT)-[e1]-(x)-[e2]-(n2:ACCOUNT) "
        "WHERE n1.account_id = 'A000000' AND n2.account_id <> 'A000000' "
        "RETURN p LIMIT 1"
    )

    assert 'MATCH (n1 IS "ACCOUNT")-[e1]-(x)-[e2]-(n2 IS "ACCOUNT")' in query
    assert "VERTEX_ID(n1) AS p_n1_ID" in query
    assert "EDGE_ID(e1) AS p_e1_ID" in query
    assert "VERTEX_ID(x) AS p_x_ID" in query
    assert "EDGE_ID(e2) AS p_e2_ID" in query
    assert "VERTEX_ID(n2) AS p_n2_ID" in query
    assert "FETCH FIRST 1 ROWS ONLY" in query


def test_cypher2oracle_sqlpgq_expands_variable_length_named_path_return():
    query = _translate("MATCH p = (a:ACCOUNT)-[e*1..3]->(b:ACCOUNT) RETURN p LIMIT 5")

    assert 'MATCH (a IS "ACCOUNT")-[e]->{1,3}(b IS "ACCOUNT")' in query
    assert "VERTEX_ID(a) AS p_a_ID" in query
    assert "JSON_ARRAYAGG(EDGE_ID(e)) AS p_e_IDS" in query
    assert "VERTEX_ID(b) AS p_b_ID" in query
    assert "FETCH FIRST 5 ROWS ONLY" in query


def test_cypher2oracle_sqlpgq_rejects_open_ended_variable_length_path():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (person:PERSON)-[:KNOWS*1..]->(friend:PERSON) RETURN friend",
        graph_name="MOVIE_GRAPH",
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_rejects_quantified_relationship_property_map():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (a)-[:CONNECTS_TO*1..2 {connectionType:'WiFi'}]->(b) RETURN count(b)"
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_translates_union_all_path_branches():
    query = _translate(
        "MATCH p = (n1:ACCOUNT)-[e1:BelongsTo]-(x:FINANCIAL_PERIOD) "
        'WHERE n1.account_id = "A000000" RETURN p LIMIT 5 '
        "UNION ALL "
        "MATCH p = (n1:ACCOUNT)-[e1:BelongsTo]-(x:FINANCIAL_PERIOD)-[e2]-(y) "
        'WHERE n1.account_id = "A000000" RETURN p LIMIT 5'
    )

    assert "\nUNION ALL\n" in query
    assert query.count("FROM GRAPH_TABLE") == 2
    assert "NULL AS p_e2_ID" in query
    assert "NULL AS p_y_ID" in query
    assert query.count("FETCH FIRST 5 ROWS ONLY") == 2


def test_cypher2oracle_sqlpgq_rejects_invalid_cypher():
    translated_query, category = cypher2oracle_sqlpgq("MATCH (p:PERSON RETURN p")

    assert translated_query == "Unable to Translate to Oracle SQL/PGQ"
    assert category != "Graph-IL Translatable"


def test_cypher2oracle_sqlpgq_translates_multi_condition_where():
    query = _translate(
        "MATCH (m:Movie) "
        "WHERE m.released >= 1990 AND m.released <= 2000 AND m.votes > 5000 "
        "RETURN m.title, m.released, m.votes"
    )

    assert 'm."released" >= 1990 AND m."released" <= 2000' in query
    assert 'm."votes" > 5000' in query


def test_cypher2oracle_sqlpgq_translates_null_predicate():
    query = _translate(
        "MATCH (c:Character) WHERE c.song IS NOT NULL RETURN c.name AS character_name"
    )

    assert 'WHERE c."song" IS NOT NULL' in query


def test_cypher2oracle_sqlpgq_translates_count_star():
    query = _translate("MATCH (m:Movie) RETURN count(*)")

    assert query.startswith("SELECT COUNT(*) AS COUNT_VALUE")
    assert "COLUMNS (1 AS dummy_value)" in query


def test_cypher2oracle_sqlpgq_coalesces_sum_but_not_other_aggregates():
    query = _translate(
        "MATCH (m:Movie) "
        "RETURN sum(m.budget) AS total_budget, count(m) AS movie_count, "
        "avg(m.budget) AS average_budget, min(m.budget) AS min_budget, "
        "max(m.budget) AS max_budget"
    )

    assert "COALESCE(SUM(budget), 0) AS total_budget" in query
    assert "COUNT(m_VALUE) AS movie_count" in query
    assert "AVG(budget) AS average_budget" in query
    assert "MIN(budget) AS min_budget" in query
    assert "MAX(budget) AS max_budget" in query


def test_cypher2oracle_sqlpgq_translates_backtick_identifiers_and_column_compare():
    query = _translate(
        "MATCH (a:`voice-actors`)-[:MOVIE]->(c:characters) "
        "WHERE a.movie = c.movie_title "
        "RETURN a.`voice-actor` AS actor"
    )

    assert 'a."movie" = c."movie_title"' in query
    assert 'a."voice_actor" AS actor' in query


def test_cypher2oracle_sqlpgq_translates_double_quoted_property_map_strings():
    query = _translate('MATCH (u1:User {label: "inchristbl.bsky.social"}) RETURN u1.label')

    assert "u1.\"label\" = 'inchristbl.bsky.social'" in query
    assert '"inchristbl.bsky.social"' not in query


def test_cypher2oracle_sqlpgq_translates_escaped_single_quote_literals():
    query = _translate_sql(
        "MATCH (p:Product {productName: 'Chef Anton\\'s Cajun Seasoning'})"
        "-[:PART_OF]->(c:Category) "
        "MATCH (c)<-[:PART_OF]-(otherProducts:Product) "
        "MATCH (otherProducts)<-[:SUPPLIES]-(suppliers:Supplier) "
        "RETURN DISTINCT suppliers.companyName"
    )

    assert "Chef Anton''s Cajun Seasoning" in query
    assert "Anton\\'s" not in query


def test_cypher2oracle_sqlpgq_uses_out_of_line_where_for_property_maps():
    query = _translate(
        "MATCH (target:User {label: 'dwither.bsky.social'})"
        "<-[:INTERACTED]-(user:User) "
        "RETURN user.x, user.y LIMIT 3"
    )

    assert 'MATCH (user_var IS "User")-[e1 IS "INTERACTED"]->(target IS "User")' in query
    assert 'COLUMNS (user_var."x" AS x, user_var."y" AS y)' in query
    assert "WHERE target.\"label\" = 'dwither.bsky.social'" in query


def test_cypher2oracle_sqlpgq_projects_hidden_order_by_property():
    query = _translate("MATCH (u:User) WHERE u.size < 2.0 RETURN u ORDER BY u.size DESC LIMIT 5")

    assert query.startswith("SELECT u_VALUE")
    assert 'COLUMNS (VERTEX_ID(u) AS u_VALUE, u."size" AS size_VALUE)' in query
    assert "ORDER BY size_VALUE DESC" in query


def test_cypher2oracle_sqlpgq_projects_hidden_order_by_scalar_function():
    query = _translate("MATCH (u:User) WHERE u.x IS NOT NULL RETURN u ORDER BY abs(u.x) LIMIT 3")

    assert query.startswith("SELECT u_VALUE")
    assert 'abs(u."x") AS abs_x' in query
    assert "ORDER BY abs_x" in query


def test_cypher2oracle_sqlpgq_translates_cypher_date_function_to_oracle_literal():
    query = _translate(
        "MATCH (a:ACCOUNT) WHERE a.opening_date < date('2020-01-01') RETURN a.status"
    )

    assert "a.\"opening_date\" < DATE '2020-01-01'" in query


def test_cypher2oracle_sqlpgq_translates_cypher_current_date_function():
    query = _translate(
        "MATCH (cr:COMPLIANCE_RULE) WHERE cr.expiry_date >= date() RETURN cr.rule_id"
    )

    assert 'cr."expiry_date" >= TRUNC(CURRENT_DATE)' in query
    assert "date()" not in query


def test_cypher2oracle_sqlpgq_translates_cypher_date_weekday_extractors():
    weekday = _translate("MATCH (m:Movie) WHERE date(m.released).weekday = 5 RETURN m.title")
    day_of_week = _translate("MATCH (m:Movie) WHERE date(m.released).dayOfWeek = 5 RETURN m.title")

    assert '(TRUNC(m."released") - TRUNC(m."released", \'IW\')) = 5' in weekday
    assert '(TRUNC(m."released") - TRUNC(m."released", \'IW\') + 1) = 5' in day_of_week
    assert ".weekday" not in weekday
    assert ".dayOfWeek" not in day_of_week


def test_cypher2oracle_sqlpgq_coerces_string_backed_date_literals():
    query = _translate_with_types(
        "MATCH (m:Movie) WHERE m.release_date >= date('1990-01-01') RETURN m.title",
        {"Movie": {"release_date": "VARCHAR2(4000)"}},
    )

    assert "m.\"release_date\" >= '1990-01-01'" in query


def test_cypher2oracle_sqlpgq_coerces_string_property_numeric_literals():
    query = _translate_with_types(
        "MATCH (u:User {id: 1}) RETURN u",
        {"User": {"id": "VARCHAR2(4000)"}},
    )

    assert "u.\"id\" = '1'" in query


def test_cypher2oracle_sqlpgq_coerces_string_property_boolean_literals():
    query = _translate_with_types(
        "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product) WHERE p.discontinued = true RETURN s",
        {"Product": {"discontinued": "VARCHAR2(4000)"}},
    )

    assert "p.\"discontinued\" = 'true'" in query
    assert 'p."discontinued" = 1' not in query


def test_cypher2oracle_sqlpgq_coerces_string_property_map_boolean_literals():
    query = _translate_with_types(
        "MATCH (p:Product {discontinued: false}) RETURN p",
        {"Product": {"discontinued": "VARCHAR2(4000)"}},
    )

    assert "p.\"discontinued\" = 'false'" in query
    assert "p.\"discontinued\" = '0'" not in query


def test_cypher2oracle_sqlpgq_translates_date_property_extractors():
    query = _translate_with_types(
        "MATCH (m:Movie) WHERE date(m.release_date).year = 1995 RETURN m.title",
        {"Movie": {"release_date": "VARCHAR2(4000)"}},
    )

    assert (
        'EXTRACT(YEAR FROM TO_DATE(m."release_date" DEFAULT NULL ON CONVERSION ERROR, '
        "'YYYY-MM-DD')) = 1995"
    ) in query


def test_cypher2oracle_sqlpgq_coerces_string_property_date_function_calls():
    query = _translate_with_types(
        "MATCH (a:Actor)-[:ACTED_IN]->(m:Movie) "
        "WHERE date(m.released) < a.born RETURN DISTINCT a.name",
        {
            "Actor": {"name": "VARCHAR2(4000)", "born": "VARCHAR2(4000)"},
            "Movie": {"released": "VARCHAR2(4000)"},
        },
    )

    assert (
        "TO_DATE(m.\"released\" DEFAULT NULL ON CONVERSION ERROR, 'YYYY-MM-DD') "
        "< TO_DATE(a.\"born\" DEFAULT NULL ON CONVERSION ERROR, 'YYYY-MM-DD')"
    ) in query
    assert 'CAST(m."released" AS DATE)' not in query


def test_cypher2oracle_sqlpgq_translates_property_date_extractors_and_modulo():
    query = _translate_with_types(
        "MATCH (m:Movie) WHERE m.release_date.year % 4 = 0 RETURN m.title",
        {"Movie": {"release_date": "VARCHAR2(4000)"}},
    )

    assert (
        'MOD(EXTRACT(YEAR FROM TO_DATE(m."release_date" DEFAULT NULL ON CONVERSION ERROR, '
        "'YYYY-MM-DD')), 4) = 0"
    ) in query


def test_cypher2oracle_sqlpgq_disambiguates_duplicate_projection_aliases():
    query = _translate(
        "MATCH (dc:DataConsumer)-[:Consumes]->(da:DataAsset) RETURN dc.name, da.name"
    )

    assert 'dc."name" AS dc' in query
    assert 'da."name" AS da' in query
    assert " AS name" not in query


def test_cypher2oracle_sqlpgq_orders_by_aggregate_alias_without_inner_projection():
    query = _translate(
        "MATCH (u:USER)-[:Initiates]->(t:TRANSACTION) "
        "RETURN u.user_id, SUM(t.amount) AS total_amount "
        "ORDER BY total_amount DESC"
    )

    assert "SELECT user_id, COALESCE(SUM(amount), 0) AS total_amount" in query
    assert "total_amount AS total_amount" not in query
    assert "ORDER BY total_amount DESC" in query


def test_cypher2oracle_sqlpgq_translates_scalar_function_return_expressions():
    query = _translate(
        "MATCH (m:Movie) "
        "RETURN abs(m.revenue - m.budget) AS difference "
        "ORDER BY difference DESC LIMIT 3"
    )

    assert 'abs(m."revenue" - m."budget") AS difference' in query


def test_cypher2oracle_sqlpgq_translates_tofloat_to_oracle_number_cast():
    query = _translate("MATCH (m:Movie) RETURN avg(toFloat(m.budget)) AS average_budget")

    assert 'COLUMNS (TO_NUMBER(m."budget") AS budget)' in query
    assert "SELECT AVG(budget) AS average_budget" in query


def test_cypher2oracle_sqlpgq_translates_tointeger_to_oracle_cast():
    query = _translate(
        "MATCH (se:SystemEnvironment)<-[:RunsIn]-(pj:ProcessingJob)"
        "-[:Transforms]->(da:DataAsset) "
        "WHERE da.sensitivity_level = 'PII' "
        "RETURN se.name AS environment_name, COUNT(pj) AS pii_processing_job_count, "
        "AVG(toInteger(pj.sla_requirements)) AS avg_sla_hours"
    )

    assert 'CAST(pj."sla_requirements" AS INTEGER) AS sla_requirements' in query
    assert (
        "SELECT environment_name, COUNT(pj_VALUE) AS pii_processing_job_count, "
        "AVG(sla_requirements) AS avg_sla_hours" in query
    )
    assert "toInteger" not in query


def test_cypher2oracle_sqlpgq_translates_substring_to_oracle_substr():
    query = _translate(
        "MATCH (o:Order) WHERE substring(o.orderDate, 0, 4) = '1997' RETURN count(o)"
    )

    assert "SUBSTR(o.\"orderDate\", 1, 4) = '1997'" in query
    assert "substring" not in query.lower()


def test_cypher2oracle_sqlpgq_translates_modulo_after_to_integer():
    query = _translate(
        "MATCH (p:Product) WHERE toInteger(p.unitPrice) % 10 = 0 RETURN p.productName"
    )

    assert 'MOD(CAST(p."unitPrice" AS INTEGER), 10) = 0' in query
    assert "%" not in query


def test_cypher2oracle_sqlpgq_redirects_unambiguous_node_property_to_adjacent_edge():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (c:Category {categoryName: 'Condiments'})"
        "<-[:PART_OF]-(p:Product)<-[:ORDERS]-(o:Order) "
        "RETURN p.productName, SUM(o.quantity) AS totalQuantity",
        graph_name="G",
        node_label_map={
            "Category": ["Category"],
            "Product": ["Product"],
            "Order": ["Order"],
        },
        edge_label_map={
            "PART_OF": ["Product_PART_OF_Category"],
            "ORDERS": ["Order_ORDERS_Product"],
        },
        property_type_map={
            "Category": {"categoryName": "VARCHAR2(4000)"},
            "Product": {"productName": "VARCHAR2(4000)"},
            "Order": {"orderID": "VARCHAR2(4000)"},
            "Order_ORDERS_Product": {"quantity": "NUMBER"},
            "Product_PART_OF_Category": {},
        },
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 'e1."quantity" AS quantity' in query
    assert 'o."quantity"' not in query


def test_cypher2oracle_sqlpgq_rejects_unmapped_edge_property_on_node():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (c:Customer)-[:PURCHASED]->(o:Order) "
        "WITH o.discount AS discounts RETURN avg(toFloat(discounts))",
        graph_name="G",
        node_label_map={"Customer": ["Customer"], "Order": ["Order"]},
        edge_label_map={
            "PURCHASED": ["Customer_PURCHASED_Order"],
            "ORDERS": ["Order_ORDERS_Product"],
        },
        property_type_map={
            "Customer": {},
            "Order": {"orderID": "VARCHAR2(4000)"},
            "Customer_PURCHASED_Order": {},
            "Order_ORDERS_Product": {"discount": "VARCHAR2(4000)"},
        },
        strict_property_validation=True,
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_rejects_raw_edge_property_leaking_to_node():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (c:Customer {country: 'Argentina'})-[:PURCHASED]->(o:Order) "
        "WITH o.discount AS discounts RETURN avg(toFloat(discounts)) AS average_discount",
        graph_name="G",
        node_label_map={"Customer": ["Customer"], "Order": ["Order"]},
        edge_label_map={
            "PURCHASED": ["Customer_PURCHASED_Order"],
            "ORDERS": ["Order_ORDERS_Product"],
        },
        property_type_map={
            "Customer": {"country": "VARCHAR2(4000)"},
            "Order": {"orderID": "VARCHAR2(4000)"},
            "PURCHASED": {},
            "Customer_PURCHASED_Order": {},
            "ORDERS": {"discount": "VARCHAR2(4000)"},
            "Order_ORDERS_Product": {"discount": "VARCHAR2(4000)"},
        },
        strict_property_validation=True,
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_infers_endpoint_label_for_strict_node_property():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (c:Customer {country: 'Argentina'})-[:PURCHASED]->(o:Order) RETURN o.orderID",
        graph_name="G",
        node_label_map={"Customer": ["Customer"], "Order": ["Order"]},
        edge_label_map={"PURCHASED": ["Customer_PURCHASED_Order"]},
        property_type_map={
            "Customer": {"country": "VARCHAR2(4000)"},
            "Order": {"orderID": "VARCHAR2(4000)"},
            "PURCHASED": {},
            "Customer_PURCHASED_Order": {},
        },
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 'o."orderID" AS orderID' in query


def test_cypher2oracle_sqlpgq_translates_size_split_word_count():
    query = _translate('MATCH (m:Movie) RETURN size(split(m.overview, " ")) AS word_count')

    assert "REGEXP_COUNT(m.\"overview\", '\\S+') AS word_count" in query


def test_cypher2oracle_sqlpgq_translates_with_size_split_word_count_aggregate():
    query = _translate_sql(
        'MATCH (q:Question)-[:TAGGED]->(t:Tag {name: "graphql"}) '
        'WITH size(split(q.text, " ")) AS wordsInQuestion '
        "RETURN avg(wordsInQuestion) AS averageWordCount"
    )

    assert "WITH stage_1 AS" in query
    assert "REGEXP_COUNT(q.\"text\", '\\S+') AS wordsInQuestion" in query
    assert "SELECT AVG(wordsInQuestion) AS averageWordCount" in query


def test_cypher2oracle_sqlpgq_translates_vertex_comparisons():
    query = _translate("MATCH (m1:Movie) MATCH (m2:Movie) WHERE m1 <> m2 RETURN m2")

    assert "NOT VERTEX_EQUAL(m1, m2)" in query


def test_cypher2oracle_sqlpgq_translates_final_with_projection_aggregate():
    query = _translate(
        "MATCH (u1:User)-[:INTERACTED]->(u2:User) "
        "WHERE u2.size <> 1.5 "
        "WITH u1.size AS interactingUserSize "
        "RETURN sum(interactingUserSize) AS totalSize"
    )

    assert query.startswith("SELECT COALESCE(SUM(interactingUserSize), 0) AS totalSize")
    assert 'u1."size" AS interactingUserSize' in query
    assert 'WHERE u2."size" <> 1.5' in query


def test_cypher2oracle_sqlpgq_uses_oracle_edge_label_map():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (a)-[:book]->(b) RETURN b",
        graph_name="G",
        edge_label_map={"book": ["book_language_book_publisher", "book_author_book"]},
    )

    assert category == "Graph-IL Translatable"
    assert 'IS "book_language_book_publisher" | "book_author_book"' in query


def test_cypher2oracle_sqlpgq_translates_relationship_label_alternatives():
    query = _translate(
        "MATCH (fp:FINANCIAL_PERIOD {status: 'Open'})"
        "<-[:BelongsTo]-(t:TRANSACTION)<-[:Initiates|Approves]-(u:USER) "
        "RETURN fp.period_id, COUNT(DISTINCT u) AS unique_users, "
        "SUM(t.amount) AS total_transaction_amount"
    )

    assert 'IS "Initiates" | "Approves"' in query
    assert 'fp."period_id" AS period_id' in query
    assert "COUNT(DISTINCT u_VALUE) AS unique_users" in query
    assert "COALESCE(SUM(amount), 0) AS total_transaction_amount" in query


def test_cypher2oracle_sqlpgq_aggregates_outside_graph_table():
    query = _translate(
        "MATCH (book:book) "
        "WHERE (book.publisher_id = 1929 AND book.num_pages > 500) "
        "RETURN count(*)"
    )

    assert query.startswith("SELECT COUNT(*) AS COUNT_VALUE")
    assert 'MATCH (book IS "book")' in query
    assert 'WHERE (book."publisher_id" = 1929 AND book."num_pages" > 500)' in query
    assert "COLUMNS (1 AS dummy_value)" in query
    assert "COUNT(*) AS COUNT_VALUE)" not in query


def test_cypher2oracle_sqlpgq_average_aggregates_projected_property_outside_graph_table():
    query = _translate(
        "MATCH (:Person)-[r:REVIEWED]->(m:Movie) "
        "WHERE r.rating > 80 "
        "RETURN AVG(m.released) AS averageReleaseYear"
    )

    assert query.startswith("SELECT AVG(released) AS averageReleaseYear")
    assert 'COLUMNS (m."released" AS released)' in query


def test_cypher2oracle_sqlpgq_grouped_aggregate_uses_outer_group_by():
    query = _translate(
        "MATCH (director:director) "
        "RETURN director, count(director.name) ORDER BY count(director.name) DESC LIMIT 1"
    )

    assert query.startswith("SELECT director_VALUE, COUNT(name) AS name")
    assert 'COLUMNS (VERTEX_ID(director) AS director_VALUE, director."name" AS name)' in query
    assert "GROUP BY director_VALUE" in query
    assert "ORDER BY name DESC" in query


def test_cypher2oracle_sqlpgq_translates_aggregate_case_expression():
    query = _translate(
        "MATCH (t1:area_code)<-[zip_code:ZIP_CODE]-(t2:zip_data) "
        "WHERE t1.area_code = 787 "
        "RETURN (count(CASE WHEN t2.type = 'P.O. Box Only' THEN 1 ELSE NULL END) "
        "- count(CASE WHEN t2.type = 'Post Office' THEN 1 ELSE NULL END)) AS DIFFERENCE"
    )

    assert query.startswith(
        "SELECT (count(CASE WHEN type = 'P.O. Box Only' THEN 1 ELSE NULL END) "
        "- count(CASE WHEN type = 'Post Office' THEN 1 ELSE NULL END)) AS DIFFERENCE"
    )
    assert 'COLUMNS (t2."type" AS type)' in query
    assert "GROUP BY" not in query


def test_cypher2oracle_sqlpgq_uses_case_insensitive_label_maps():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (t1:state)<-[state:STATE]-(t2:country) RETURN count(t2.county)",
        graph_name="G",
        node_label_map={"state": ["state"], "country": ["country"]},
        edge_label_map={"state": ["country_STATE_state"]},
    )

    assert category == "Graph-IL Translatable"
    assert '[state IS "country_STATE_state"]->' in query
    assert '[state IS "STATE"]' not in query


def test_cypher2oracle_sqlpgq_maps_sanitized_labels_and_properties_strictly():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (t1:characters)-[hero:HERO]->(t2:`voice-actors`) "
        "WHERE t2.movie = t1.movie_title "
        "RETURN t2.`voice-actor`",
        graph_name="G",
        node_label_map={
            "characters": ["characters"],
            "voice_actors": ["voice_actors"],
        },
        edge_label_map={"HERO": ["characters_HERO_voice_actors"]},
        property_type_map={
            "characters": {"movie_title": "VARCHAR2(4000)"},
            "voice_actors": {
                "movie": "VARCHAR2(4000)",
                "voice_actor": "VARCHAR2(4000)",
            },
            "characters_HERO_voice_actors": {},
        },
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 't2 IS "voice_actors"' in query
    assert '[hero IS "characters_HERO_voice_actors"]->' in query
    assert 't2."voice_actor" AS voice_actor' in query


def test_cypher2oracle_sqlpgq_translates_string_predicates():
    starts = _translate("MATCH (a:author) WHERE a.name STARTS WITH 'George' RETURN a.name")
    ends = _translate("MATCH (c:customer) WHERE c.email ENDS WITH '@x.test' RETURN c.email")
    contains = _translate("MATCH (p:publisher) WHERE p.name CONTAINS 'book' RETURN count(*)")

    assert "a.\"name\" LIKE 'George' || '%'" in starts
    assert "c.\"email\" LIKE '%' || '@x.test'" in ends
    assert "INSTR(p.\"name\", 'book') > 0" in contains


def test_cypher2oracle_sqlpgq_translates_label_predicates():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (entity)-[:ClassifiedUnder]->(d:Domain) "
        "WHERE entity:Concept OR entity:Assertion "
        "RETURN d.name, entity:Concept AS is_concept",
        graph_name="G",
        node_label_map={"Concept": ["Concept"], "Assertion": ["Assertion"]},
    )

    assert category == "Graph-IL Translatable"
    assert 'entity IS LABELED "Concept"' in query
    assert 'entity IS LABELED "Assertion"' in query
    assert "entity:Concept" not in query


def test_cypher2oracle_sqlpgq_folds_impossible_label_predicates():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (p:Person)-[:DIRECTED]->(m:Movie) "
        "WHERE NOT (p:Director) "
        "RETURN m.title AS MovieTitle",
        graph_name="G",
        node_label_map={"Person": ["Person"], "Director": ["Director"], "Movie": ["Movie"]},
    )

    assert category == "Graph-IL Translatable"
    assert "WHERE NOT ((1 = 0))" in query
    assert 'p IS LABELED "Director"' not in query


def test_cypher2oracle_sqlpgq_maps_identity_to_primary_key():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (n:PaymentTransaction) RETURN count(n.identity)",
        graph_name="G",
        property_type_map={
            "PaymentTransaction": {
                "transaction_id": "VARCHAR2(4000)",
                "status": "VARCHAR2(4000)",
            }
        },
        node_primary_key_map={"PaymentTransaction": "transaction_id"},
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 'n."transaction_id" AS identity' in query
    assert 'n."identity"' not in query


def test_cypher2oracle_sqlpgq_rejects_unresolved_identity_pseudo_property():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (n1:USER)-[*1..3]->(n2) RETURN n2.identity",
        graph_name="G",
        property_type_map={
            "USER": {"user_id": "VARCHAR2(4000)"},
            "TWEET": {"tweet_id": "VARCHAR2(4000)"},
        },
        node_primary_key_map={"USER": "user_id", "TWEET": "tweet_id"},
        strict_property_validation=True,
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_maps_edge_identity_to_edge_id_function():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (u:USER)-[r:POSTS]->(t:TWEET) RETURN u.user_id, r.identity, t.tweet_id",
        graph_name="G",
        node_label_map={"USER": ["USER"], "TWEET": ["TWEET"]},
        edge_label_map={"POSTS": ["USER_POSTS_TWEET"]},
        property_type_map={
            "USER": {"user_id": "VARCHAR2(4000)"},
            "TWEET": {"tweet_id": "VARCHAR2(4000)"},
            "POSTS": {"EDGE_ID": "NUMBER"},
            "USER_POSTS_TWEET": {"EDGE_ID": "NUMBER"},
        },
        edge_primary_key_map={"POSTS": "EDGE_ID", "USER_POSTS_TWEET": "EDGE_ID"},
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert "EDGE_ID(r) AS identity" in query
    assert 'r."EDGE_ID"' not in query


def test_cypher2oracle_sqlpgq_rejects_missing_properties_when_strict():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (n:PaymentTransaction) RETURN n.missing_property",
        graph_name="G",
        property_type_map={"PaymentTransaction": {"transaction_id": "VARCHAR2(4000)"}},
        strict_property_validation=True,
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_rejects_string_numeric_aggregate_without_cast():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (t:TWEET) RETURN AVG(t.tweet_id) AS avg_tweet_id",
        graph_name="G",
        property_type_map={"TWEET": {"tweet_id": "VARCHAR2(4000)"}},
        strict_property_validation=True,
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_maps_camel_case_property_to_snake_case():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (u:User)-[:ASKED]->(q:Question) "
        "WITH u, count(q) AS questionCount ORDER BY questionCount DESC LIMIT 3 "
        "RETURN u.displayName, questionCount",
        graph_name="G",
        property_type_map={
            "User": {"display_name": "VARCHAR2(4000)"},
            "Question": {},
        },
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 'u."display_name" AS u_displayName' in query
    assert 'u."displayName"' not in query


def test_cypher2oracle_sqlpgq_translates_aggregate_arithmetic_over_elements():
    query = _translate(
        "MATCH (g:Group)<-[:BelongsTo]-(u:User)-[:HasRole]->(r:Role) "
        "RETURN g.Group_id, g.name, COUNT(DISTINCT u) AS user_count, "
        "COUNT(r) / COUNT(DISTINCT u) AS avg_roles_per_user"
    )

    assert "COUNT(r_VALUE) / COUNT(DISTINCT u_VALUE) AS avg_roles_per_user" in query
    assert "VERTEX_ID(r) AS r_VALUE" in query
    assert "VERTEX_ID(u) AS u_VALUE" in query
    assert "r) / COUNT(u AS" not in query


def test_cypher2oracle_sqlpgq_translates_lowercase_distinct_element_aggregate():
    query = _translate("MATCH (p:Person) RETURN count(distinct p) AS person_count")

    assert "COUNT(DISTINCT p_VALUE) AS person_count" in query
    assert "VERTEX_ID(p) AS p_VALUE" in query
    assert "distinct p AS" not in query


def test_cypher2oracle_sqlpgq_translates_aggregate_arithmetic_over_properties():
    query = _translate(
        "MATCH (fp:FINANCIAL_PERIOD)<-[:BelongsTo]-(t:TRANSACTION), "
        "(b:BUDGET)-[:AllocatedTo]->(a:ACCOUNT)-[:BelongsTo]->(fp) "
        "RETURN fp.period_id, SUM(b.amount) - SUM(t.amount) AS budget_variance"
    )

    assert "COALESCE(SUM(b_amount), 0) - COALESCE(SUM(t_amount), 0) AS budget_variance" in query
    assert 'b."amount" AS b_amount' in query
    assert 't."amount" AS t_amount' in query


def test_cypher2oracle_sqlpgq_translates_aggregate_with_to_cte():
    query = _translate_sql(
        "MATCH (u:USER)-[:POSTS]->(t:TWEET) "
        "WITH u.username AS username, COUNT(t) AS tweet_count "
        "WHERE tweet_count > 10 "
        "RETURN username, tweet_count ORDER BY tweet_count DESC LIMIT 5"
    )

    assert query.startswith("WITH stage_1 AS")
    assert "SELECT username, COUNT(t_VALUE) AS tweet_count" in query
    assert "GROUP BY username" in query
    assert "WHERE tweet_count > 10" in query
    assert "ORDER BY tweet_count DESC" in query


def test_cypher2oracle_sqlpgq_resolves_duplicate_final_aliases_after_with_stage():
    query = _translate_sql(
        "MATCH (a:ACTOR)-[:ACTED_IN]->(m1:MOVIE)-[s:SIMILAR_TO]->(m2:MOVIE) "
        "WHERE s.similarity_score > 0.8 "
        "WITH a, m1, m2, COUNT(s) AS sim_count "
        "WHERE sim_count >= 3 "
        "RETURN DISTINCT a.name, m1.title, m2.title"
    )

    assert "SELECT DISTINCT a_name AS name, m1_title AS m1, m2_title AS m2" in query
    assert "m1_title AS title, m2_title AS title" not in query


def test_cypher2oracle_sqlpgq_translates_correlated_optional_match_to_left_join():
    query = _translate_sql(
        "MATCH (a:Person) "
        "OPTIONAL MATCH (a)-[:KNOWS]->(b:Person) "
        "RETURN a.name AS person_name, b.name AS friend_name"
    )

    assert query.startswith("WITH stage_1 AS")
    assert "stage_2 AS" in query
    assert "LEFT JOIN stage_2 ON stage_2.a_VALUE = stage_1.stage_1_a_VALUE" in query
    assert "stage_1.person_name AS person_name" in query
    assert "stage_2.friend_name AS friend_name" in query


def test_cypher2oracle_sqlpgq_translates_optional_match_after_with_to_left_join():
    query = _translate_sql(
        "MATCH (a:Person) WITH a "
        "OPTIONAL MATCH (a)-[:KNOWS]->(b:Person) "
        "RETURN a.name AS person_name, b.name AS friend_name"
    )

    assert "LEFT JOIN stage_2 ON stage_2.a_VALUE = stage_1.stage_1_a_VALUE" in query
    assert "stage_1.person_name AS person_name" in query
    assert "stage_2.friend_name AS friend_name" in query


def test_cypher2oracle_sqlpgq_aggregates_optional_match_rows():
    query = _translate_sql(
        "MATCH (a:Person) "
        "OPTIONAL MATCH (a)-[:KNOWS]->(b:Person) "
        "WITH a, count(b) AS friend_count "
        "RETURN a.name AS person_name, friend_count"
    )

    assert "LEFT JOIN stage_2 ON stage_2.a_VALUE = stage_1.stage_1_a_VALUE" in query
    assert "COUNT(stage_2.b_VALUE) AS friend_count" in query
    assert "GROUP BY stage_1.stage_1_a_VALUE" in query
    assert "stage_1.a_name AS a_name" in query


def test_cypher2oracle_sqlpgq_keeps_optional_where_inside_optional_stage():
    query = _translate_sql(
        "MATCH (a:Person) "
        "OPTIONAL MATCH (a)-[:KNOWS]->(b:Person) "
        "WHERE b.age > 30 "
        "RETURN a.name AS person_name, b.name AS friend_name"
    )

    assert "FROM stage_1\nLEFT JOIN stage_2 ON stage_2.a_VALUE = stage_1.stage_1_a_VALUE" in query
    assert query.index('WHERE b."age" > 30') < query.index('COLUMNS (b."name" AS friend_name')


def test_cypher2oracle_sqlpgq_rejects_unsupported_optional_match_shapes():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (a:Person) OPTIONAL MATCH (a)-[:KNOWS]->(b:Person) "
        "OPTIONAL MATCH (b)-[:KNOWS]->(c:Person) RETURN c.name",
        graph_name="MOVIE_GRAPH",
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"

    query, category = cypher2oracle_sqlpgq(
        "MATCH (a:Person) OPTIONAL MATCH (b:Person) RETURN b.name",
        graph_name="MOVIE_GRAPH",
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_carries_with_variable_properties_to_cte():
    query = _translate_sql(
        "MATCH (u:USER)-[:Initiates]->(t:TRANSACTION) "
        "WITH u, COUNT(t) AS transaction_count, SUM(t.amount) AS total_amount "
        "WHERE transaction_count > 5 "
        "RETURN u.user_id, total_amount"
    )

    assert 'u."user_id" AS u_user_id' in query
    assert "GROUP BY u_VALUE, u_user_id" in query
    assert "SELECT u_user_id AS user_id, total_amount AS total_amount" in query
    assert "SELECT u AS user_id" not in query


def test_cypher2oracle_sqlpgq_carries_with_variable_properties_for_final_aggregate():
    query = _translate_sql(
        "MATCH (a:ACCOUNT)-[:GovernedBy]->(cr:COMPLIANCE_RULE) "
        "WITH a, COUNT(cr) AS rule_count "
        "WHERE rule_count > 1 "
        "RETURN AVG(a.balance) AS average_balance"
    )

    assert 'a."balance" AS a_balance' in query
    assert "GROUP BY a_VALUE, a_balance" in query
    assert "SELECT AVG(a_balance) AS average_balance" in query
    assert "AVG(a)" not in query


def test_cypher2oracle_sqlpgq_groups_final_with_stage_aggregate_projection():
    query = _translate_sql(
        "MATCH (u:USER)-[:USES]->(r:RESOURCE) "
        "WITH u, COUNT(DISTINCT r) AS distinct_resources "
        "RETURN u.name, AVG(distinct_resources) AS avg_resources"
    )

    assert "SELECT u_name AS name, AVG(distinct_resources) AS avg_resources" in query
    assert "GROUP BY u_name" in query
    assert 'u."name" AS u_name' in query


def test_cypher2oracle_sqlpgq_aggregates_carried_with_edge_variable():
    query = _translate_sql(
        "MATCH (p:PERSON)-[r:HAS]->(res:RESOURCE) "
        "WITH p, r, COUNT(res) AS resource_count "
        "RETURN p.name, COUNT(r) AS relationship_count"
    )

    assert "COUNT(r_VALUE) AS relationship_count" in query
    assert "EDGE_ID(r) AS r_VALUE" in query
    assert "GROUP BY p_name" in query
    assert "COUNT(r) AS" not in query


def test_cypher2oracle_sqlpgq_filters_with_stage_on_carried_property_alias():
    query = _translate_sql(
        "MATCH (g:GROUP)<-[:MEMBER_OF]-(u:USER) "
        "WITH g, COUNT(u) AS member_count "
        "WHERE g.member_count > 10 "
        "RETURN g.name, member_count"
    )

    assert 'g."member_count" AS g_member_count' in query
    assert "WHERE g_member_count > 10" in query
    assert "WHERE g.member_count" not in query


def test_cypher2oracle_sqlpgq_translates_ordered_with_to_cte():
    query = _translate_sql(
        "MATCH (c:Character) "
        "WITH c.name AS name, c.rank AS rank ORDER BY rank DESC LIMIT 5 "
        "RETURN name, rank"
    )

    assert query.startswith("WITH stage_1 AS")
    assert 'c."name" AS name' in query
    assert 'c."rank" AS rank' in query
    assert "ORDER BY rank DESC" in query
    assert "FETCH FIRST 5 ROWS ONLY" in query
    assert query.strip().endswith("FROM stage_1")


def test_cypher2oracle_sqlpgq_normalizes_descending_order_keyword():
    query = _translate_sql(
        "MATCH (p:Product) "
        "WITH p, p.reorderLevel AS reorderLevel ORDER BY reorderLevel DESCENDING "
        "RETURN p.productName LIMIT 1"
    )

    assert "ORDER BY reorderLevel DESC" in query
    assert "DESCENDING" not in query


def test_cypher2oracle_sqlpgq_orders_with_stage_by_hidden_property_alias():
    query = _translate_sql(
        "MATCH (m:Movie)<-[:RATED]-(u:User) "
        "WITH m, count(u) AS userCount "
        "WHERE userCount > 1000 "
        "RETURN m ORDER BY m.imdbRating DESC LIMIT 3"
    )

    assert 'm."imdbRating" AS m_imdbRating' in query
    assert "ORDER BY m_imdbRating DESC" in query
    assert "ORDER BY imdbRating DESC" not in query


def test_cypher2oracle_sqlpgq_translates_chained_numeric_comparison():
    query = _translate(
        "MATCH (q:Question) "
        "WHERE 100 <= q.view_count <= 500 "
        "RETURN q.uuid, q.title, q.view_count ORDER BY q.view_count ASC"
    )

    assert '(100 <= q."view_count" AND q."view_count" <= 500)' in query
    assert '100 <= q."view_count" <= 500' not in query


def test_cypher2oracle_sqlpgq_omits_unknown_strict_edge_label():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (z:ZIP)-[state:STATE]->(s:STATE) RETURN s.name",
        graph_name="G",
        node_label_map={"ZIP": ["zip"], "STATE": ["state"]},
        edge_label_map={"zip_to_state": ["zip_data_country_state"]},
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 'MATCH (z IS "zip")-[state]->(s IS "state")' in query
    assert 'state IS "STATE"' not in query


def test_cypher2oracle_sqlpgq_rejects_property_on_unknown_strict_edge_label():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (a:A)-[bad:UnknownEdge]->(b:B) RETURN bad.some_property",
        graph_name="G",
        node_label_map={"A": ["A"], "B": ["B"]},
        edge_label_map={"KnownEdge": ["A_KnownEdge_B"]},
        property_type_map={"UnknownEdge": {"some_property": "VARCHAR2(4000)"}},
        strict_property_validation=True,
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_maps_source_label_alias_to_graph_label():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (s:Source)<-[:SourcedFrom]-(a:Assertion) RETURN COUNT(DISTINCT s)",
        graph_name="G",
        node_label_map={"Source": ["InfoSource"], "Assertion": ["Assertion"]},
        edge_label_map={"SourcedFrom": ["Assertion_SourcedFrom_InfoSource"]},
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 's IS "InfoSource"' in query
    assert 's IS "Source"' not in query


def test_cypher2oracle_sqlpgq_translates_id_function_vertex_comparison():
    query = _translate(
        "MATCH (a:Assertion)<-[:Supports]-(s1:Assertion), "
        "(a)<-[:Supports]-(s2:Assertion) "
        "WHERE id(s1) <> id(s2) "
        "RETURN avg(a.confidence_score) AS average_confidence"
    )

    assert "WHERE NOT VERTEX_EQUAL(s1, s2)" in query
    assert "id(s1)" not in query


def test_cypher2oracle_sqlpgq_uses_resolved_aliases_for_duplicate_aggregate_properties():
    query = _translate(
        "MATCH (p:Policy)-[:Enforces]->(r:Role)-[:GrantsAccessTo]->(res:Resource) "
        "RETURN r.name, p.name, COUNT(res) AS api_endpoint_count"
    )

    assert "SELECT r, p, COUNT(res_VALUE) AS api_endpoint_count" in query
    assert 'COLUMNS (r."name" AS r, p."name" AS p, VERTEX_ID(res) AS res_VALUE)' in query
    assert "GROUP BY r, p" in query
    assert "SELECT name, name" not in query


def test_cypher2oracle_sqlpgq_translates_with_stage_tofloat_aggregate_argument():
    query = _translate_sql(
        "MATCH (role:Role {is_compliant: true})-[:GrantsAccessTo]->(res:Resource) "
        "WITH role, COUNT(res) AS resource_count "
        "WHERE resource_count >= 1 "
        "RETURN role.name AS role_name, AVG(toFloat(resource_count)) AS avg_resources "
        "ORDER BY avg_resources DESC"
    )

    assert "AVG(TO_NUMBER(resource_count)) AS avg_resources" in query
    assert "toFloat" not in query


def test_cypher2oracle_sqlpgq_translates_final_with_arithmetic_expression():
    query = _translate_sql(
        "MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent)-[:Targets]->(r:Resource) "
        "WITH u, COUNT(ae) AS attempt_count, MIN(ae.timestamp) AS first_attempt, "
        "MAX(ae.timestamp) AS last_attempt "
        "WHERE attempt_count > 1 "
        "RETURN u.name, attempt_count, "
        "(last_attempt - first_attempt) / attempt_count AS avg_time_between_attempts"
    )

    assert "(last_attempt - first_attempt) / attempt_count AS avg_time_between_attempts" in query
    assert "_last_attempt_first_attempt_attempt_count AS avg_time_between_attempts" not in query


def test_cypher2oracle_sqlpgq_casts_date_function_over_properties():
    query = _translate(
        "MATCH (p:Project)<-[:AppliedIn]-(c:Concept)-[:TaggedWith]->(t:Tag) "
        "RETURN COUNT(p) AS project_count, "
        "AVG(DATE(p.end_date) - DATE(p.start_date)) AS avg_duration_days"
    )

    assert 'CAST(p."end_date" AS DATE) - CAST(p."start_date" AS DATE)' in query
    assert 'DATE(p."end_date")' not in query


def test_cypher2oracle_sqlpgq_rejects_numeric_aggregate_over_temporal_property():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (p:Policy) RETURN AVG(p.effective_date) AS avg_effective_date",
        graph_name="G",
        property_type_map={"Policy": {"effective_date": "DATE"}},
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_suffixes_resource_reserved_identifier():
    query = _translate_sql(
        "MATCH (role:Role)-[:GrantsAccessTo]->(resource:Resource) "
        "RETURN role, resource "
        "UNION "
        "MATCH (role:Role)-[:GrantsAccessTo]->(:TemporaryAccess)"
        "-[:AssignedTempAccess]->(resource:Resource) "
        "RETURN role, resource"
    )

    assert '(resource_VALUE IS "Resource")' in query
    assert "VERTEX_ID(resource_VALUE) AS resource_VALUE" in query
    assert '(resource IS "Resource")' not in query


def test_cypher2oracle_sqlpgq_uses_safe_variable_for_user_identifier():
    query = _translate_sql(
        "MATCH (user:User)-[:COMMENTED]->(comment:Comment)"
        "-[:COMMENTED_ON]->(question:Question) "
        "WITH question, count(DISTINCT user) AS distinct_commenters "
        "WHERE distinct_commenters > 1 RETURN question.title"
    )

    assert 'MATCH (user_var IS "User")' in query
    assert '(comment_VALUE IS "Comment")' in query
    assert "VERTEX_ID(user_var) AS user_VALUE" in query
    assert "COUNT(DISTINCT user_VALUE) AS distinct_commenters" in query


def test_cypher2oracle_sqlpgq_translates_with_match_join_on_carried_variable():
    query = _translate_sql(
        "MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent)-[:Targets]->(r:Resource) "
        "WHERE r.sensitivity_level = 'Confidential' "
        "WITH u "
        "MATCH (u)-[:AssignedTempAccess]->(ta:TemporaryAccess) "
        "RETURN DISTINCT u.name, u.department"
    )

    assert query.startswith("WITH stage_1 AS")
    assert "stage_2 AS" in query
    assert "VERTEX_ID(u) AS stage_1_u_VALUE" in query
    assert "VERTEX_ID(u) AS u_VALUE" in query
    assert "JOIN stage_1 ON stage_2.u_VALUE = stage_1.stage_1_u_VALUE" in query
    assert "SELECT DISTINCT stage_1.name AS name, stage_1.department AS department" in query


def test_cypher2oracle_sqlpgq_translates_with_match_join_on_multiple_variables():
    query = _translate_sql(
        "MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent)-[:Targets]->(r:Resource) "
        "WHERE r.sensitivity_level = 'Confidential' "
        "WITH u, r "
        "MATCH (u)-[:AssignedTempAccess]->(ta:TemporaryAccess)-[:AssignedTempAccess]->(r) "
        "RETURN DISTINCT u.name, r.name"
    )

    assert "VERTEX_ID(r) AS stage_1_r_VALUE" in query
    assert "VERTEX_ID(u) AS stage_1_u_VALUE" in query
    assert "VERTEX_ID(r) AS r_VALUE" in query
    assert "VERTEX_ID(u) AS u_VALUE" in query
    assert "stage_2.r_VALUE = stage_1.stage_1_r_VALUE" in query
    assert "stage_2.u_VALUE = stage_1.stage_1_u_VALUE" in query
    assert "SELECT DISTINCT stage_1.u AS u, stage_1.r AS r" in query


def test_cypher2oracle_sqlpgq_uses_second_stage_duplicate_property_aliases_after_with_match():
    query = _translate_sql(
        "MATCH (creator:User {department:'IT'})-[:BelongsTo]->(g:Group) "
        "WITH DISTINCT g "
        "MATCH (g)<-[:BelongsTo]-(u:User)-[:AttemptsAccess]->"
        "(ae:AccessEvent {outcome:'FAILURE'})-[:Targets]->(r:Resource) "
        "RETURN u.name, g.name, r.name"
    )

    assert "SELECT stage_2.u AS u, stage_1.g AS g, stage_2.r AS r" in query
    assert "stage_2.name AS u" not in query
    assert "stage_2.name AS r" not in query


def test_cypher2oracle_sqlpgq_qualifies_second_stage_whole_element_after_with_match():
    query = _translate_sql(
        "MATCH (v:VENDOR)-[:PROVIDES]->(c:CONTRACT) "
        "WITH v, SUM(c.value) AS total_value "
        "WHERE total_value > 100000 "
        "MATCH (v)-[:PROVIDES]->(c:CONTRACT) "
        "RETURN v, c ORDER BY c.value DESC LIMIT 10"
    )

    assert "SELECT stage_1.v_VALUE AS v_VALUE, stage_2.c_VALUE AS c_VALUE" in query
    assert "SELECT stage_1.v_VALUE AS v_VALUE, c_VALUE" not in query
    assert 'c."value" AS c_value_PROP' in query
    assert "ORDER BY stage_2.c_value_PROP DESC" in query


def test_cypher2oracle_sqlpgq_projects_carried_return_properties_from_first_with_stage():
    query = _translate_sql(
        "MATCH (p:Policy)-[:Enforces]->(r:Role)-[:GrantsAccessTo]->(res1:Resource) "
        "WHERE res1.type = 'Database' "
        "WITH p, r "
        "MATCH (r)-[:GrantsAccessTo]->(res2:Resource) "
        "WHERE res2.type = 'File Server' "
        "RETURN DISTINCT p.name AS PolicyName, p.description AS PolicyDescription"
    )

    assert 'p."name" AS PolicyName' in query
    assert 'p."description" AS PolicyDescription' in query
    assert "COLUMNS (VERTEX_ID(r) AS r_VALUE)" in query
    assert "p.name AS PolicyName" not in query


def test_cypher2oracle_sqlpgq_maps_label_derived_id_for_carried_with_match_property():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (s:Source)<-[:SourcedFrom]-(a1:Assertion) "
        "WHERE a1.confidence_score < 0.5 "
        "WITH s "
        "MATCH (s)<-[:SourcedFrom]-(a2:Assertion) "
        "WHERE a2.confidence_score > 0.9 "
        "RETURN DISTINCT s.source_id, s.title",
        graph_name="G",
        node_label_map={"Source": ["InfoSource"], "Assertion": ["Assertion"]},
        edge_label_map={"SourcedFrom": ["Assertion_SourcedFrom_InfoSource"]},
        property_type_map={
            "InfoSource": {
                "infosource_id": "VARCHAR2(4000)",
                "title": "VARCHAR2(4000)",
            },
            "Assertion": {"confidence_score": "NUMBER"},
        },
        node_primary_key_map={"InfoSource": "infosource_id"},
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 's."infosource_id" AS source_id' in query
    assert 's."source_id"' not in query
    assert "SELECT DISTINCT stage_1.source_id AS source_id, stage_1.title AS title" in query


def test_cypher2oracle_sqlpgq_does_not_duplicate_redeclared_carried_vertex_return():
    query = _translate_sql(
        "MATCH (nodes_1:Policy) WHERE nodes_1.name = 'Compliance Policy 9' "
        "WITH nodes_1 "
        "MATCH (nodes_1)-[edges_1:GrantsAccessTo]->(nodes_2:Resource) "
        "RETURN nodes_2, nodes_1, edges_1 LIMIT 10"
    )

    stage_1 = query.split("stage_2 AS", 1)[0]
    assert "VERTEX_ID(nodes_1) AS stage_1_nodes_1_VALUE" in stage_1
    assert "VERTEX_ID(nodes_1) AS nodes_1_VALUE" not in stage_1
    assert (
        "SELECT stage_2.nodes_2_VALUE AS nodes_2_VALUE, "
        "stage_1.stage_1_nodes_1_VALUE AS nodes_1_VALUE, "
        "stage_2.edges_1_VALUE AS edges_1_VALUE"
    ) in query


def test_cypher2oracle_sqlpgq_translates_aggregate_with_match_stage_alias_aggregate():
    query = _translate_sql(
        "MATCH (u:User)-[:AttemptsAccess]->(:AccessEvent)-[:Targets]->(res:Resource) "
        "WITH u, COUNT(res) AS resource_count "
        "WHERE resource_count > 3 "
        "MATCH (u)-[:HasRole]->(r:Role) "
        "RETURN r.role_type, AVG(resource_count) AS avg_resources_accessed"
    )

    assert "COUNT(res_VALUE) AS resource_count" in query
    assert "WHERE resource_count > 3" in query
    assert "AVG(stage_1.resource_count) AS avg_resources_accessed" in query
    assert "JOIN stage_1 ON stage_2.u_VALUE = stage_1.u_VALUE" in query


def test_cypher2oracle_sqlpgq_translates_aggregate_with_match_carried_property_projection():
    query = _translate_sql(
        "MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent)-[:Targets]->(r:Resource) "
        "WHERE r.sensitivity_level = 'Confidential' "
        "WITH u, r, COUNT(ae) AS access_count "
        "WHERE access_count > 1 "
        "MATCH (u)-[:HasRole]->(ro:Role)-[:GrantsAccessTo]->(r) "
        "RETURN DISTINCT u.name, r.name, access_count"
    )

    assert 'u."name" AS u_name' in query
    assert 'r."name" AS r_name' in query
    assert "SELECT DISTINCT stage_1.u_name AS u, stage_1.r_name AS r" in query
    assert "stage_1.access_count AS access_count" in query


def test_cypher2oracle_sqlpgq_translates_aggregate_with_match_distinct_second_stage_count():
    query = _translate_sql(
        "MATCH (u:User)-[:BelongsTo]->(g:Group) "
        "WITH u, COUNT(g) AS group_count "
        "WHERE group_count > 1 "
        "MATCH (u)-[:AttemptsAccess]->(ae:AccessEvent)-[:Targets]->(r:Resource) "
        "WHERE r.type = 'API Endpoint' "
        "RETURN u.name, COUNT(DISTINCT r) AS api_endpoints_accessed"
    )

    assert "VERTEX_ID(r) AS r_VALUE" in query
    assert "COUNT(DISTINCT stage_2.r_VALUE) AS api_endpoints_accessed" in query


def test_cypher2oracle_sqlpgq_translates_aggregate_with_match_order_by_stage_alias():
    query = _translate_sql(
        "MATCH (u:User)-[:HasRole]->(r:Role)-[:GrantsAccessTo]->(res:Resource) "
        "WITH u, r, COUNT(res) AS resource_count "
        "WHERE resource_count > 5 "
        "MATCH (u)-[:BelongsTo]->(g:Group) "
        "WHERE g.member_count > 10 "
        "RETURN u.name AS UserName, r.name AS RoleName, resource_count "
        "ORDER BY resource_count DESC"
    )

    assert "stage_1.resource_count AS resource_count" in query
    assert "ORDER BY resource_count DESC" in query
    stage_2 = query.split("stage_2 AS", 1)[1].split(")\nSELECT", 1)[0]
    assert "resource_count AS resource_count" not in stage_2


def test_cypher2oracle_sqlpgq_translates_ordered_limited_aggregate_with_match():
    query = _translate_sql(
        "MATCH (q:Question)<-[:COMMENTED_ON]-(c:Comment) "
        "WITH q, COUNT(c) AS commentCount ORDER BY commentCount DESC LIMIT 5 "
        "MATCH (q)<-[:ANSWERED]-(a:Answer)<-[:PROVIDED]-(u:User) "
        "RETURN u.display_name AS user, COUNT(a) AS answerCount "
        "ORDER BY answerCount DESC LIMIT 5"
    )

    assert "COUNT(c_VALUE) AS commentCount" in query
    assert "ORDER BY commentCount DESC" in query
    assert "FETCH FIRST 5 ROWS ONLY" in query
    assert "JOIN stage_1 ON stage_2.q_VALUE = stage_1.q_VALUE" in query
    assert "COUNT(stage_2.a_VALUE) AS answerCount" in query
    assert "ORDER BY answerCount DESC" in query


def test_cypher2oracle_sqlpgq_keeps_final_aggregate_when_alias_matches_stage():
    query = _translate_sql(
        "MATCH (q:Question)<-[:COMMENTED_ON]-(c:Comment) "
        "WITH q, COUNT(c) AS comment_count ORDER BY comment_count DESC LIMIT 3 "
        "MATCH (q)<-[:COMMENTED_ON]-(c)<-[:COMMENTED]-(u:User) "
        "RETURN q.title AS question_title, u.display_name AS commenter_name, "
        "COUNT(c) AS comment_count ORDER BY comment_count DESC"
    )

    assert "VERTEX_ID(c) AS c_VALUE" in query
    assert "COUNT(stage_2.c_VALUE) AS comment_count" in query
    assert "stage_1.comment_count AS comment_count" not in query


def test_cypher2oracle_sqlpgq_translates_ordered_limited_with_match():
    query = _translate_sql(
        "MATCH (g:Group) "
        "WITH g ORDER BY g.member_count DESC LIMIT 3 "
        "MATCH (u:User)-[:BelongsTo]->(g) "
        "RETURN g.name AS group_name, u.name AS user_name, "
        "u.last_login AS last_login_date"
    )

    assert 'g."member_count" AS member_count' in query
    assert "ORDER BY member_count DESC" in query
    assert "FETCH FIRST 3 ROWS ONLY" in query
    assert "JOIN stage_1 ON stage_2.g_VALUE = stage_1.stage_1_g_VALUE" in query
    assert (
        "SELECT stage_1.group_name AS group_name, "
        "stage_2.user_name AS user_name, "
        "stage_2.last_login_date AS last_login_date" in query
    )


def test_cypher2oracle_sqlpgq_projects_scalar_alias_in_ordered_with_match_stage():
    query = _translate_sql(
        "MATCH (q:Question) "
        "WITH q, q.view_count AS viewCount ORDER BY viewCount DESC LIMIT 3 "
        "MATCH (u:User)-[:ASKED]->(q) "
        "RETURN u.display_name AS userDisplayName"
    )

    stage_1 = query.split("stage_2 AS", 1)[0]
    assert 'q."view_count" AS viewCount' in stage_1
    assert "viewCount AS viewCount" not in stage_1
    assert "ORDER BY viewCount DESC" in stage_1


def test_cypher2oracle_sqlpgq_translates_with_match_property_correlation():
    query = _translate_sql(
        "MATCH (u:User)-[:HasRole]->(r:Role)-[:GrantsAccessTo]->(res:Resource) "
        "WITH u, COUNT(res) AS resource_count "
        "WHERE resource_count > 5 "
        "MATCH (g:Group) "
        "WHERE g.created_by = u.User_id "
        "RETURN AVG(g.member_count) AS AverageMembersInGroups"
    )

    assert 'u."User_id" AS u_User_id' in query
    assert 'g."created_by" AS g_created_by' in query
    assert "JOIN stage_1 ON stage_2.g_created_by = stage_1.u_User_id" in query
    assert 'WHERE g."created_by" = u."User_id"' not in query


def test_cypher2oracle_sqlpgq_translates_with_match_correlation_and_stage_alias_return():
    query = _translate_sql(
        "MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent)-[:Targets]->(r:Resource) "
        "WITH u, COUNT(DISTINCT r) AS resource_count "
        "WHERE resource_count > 3 "
        "MATCH (al:AuditLog) "
        "WHERE al.performed_by = u.User_id "
        "RETURN al.timestamp, resource_count"
    )

    assert 'al."performed_by" AS al_performed_by' in query
    assert "stage_1.resource_count AS resource_count" in query
    assert "JOIN stage_1 ON stage_2.al_performed_by = stage_1.u_User_id" in query


def test_cypher2oracle_sqlpgq_translates_with_match_element_correlation():
    query = _translate_sql(
        "MATCH (p1:Product {productName: 'Aniseed Syrup'})"
        "<-[:ORDERS]-(:Order)<-[:PURCHASED]-(c1:Customer) "
        "WITH c1 "
        "MATCH (p2:Product {productName: 'Ipoh Coffee'})"
        "<-[:ORDERS]-(:Order)<-[:PURCHASED]-(c2:Customer) "
        "WHERE c1 = c2 "
        "RETURN c1.companyName"
    )

    assert "VERTEX_ID(c1) AS stage_1_c1_VALUE" in query
    assert 'c1."companyName" AS companyName' in query
    assert "VERTEX_ID(c2) AS c2_VALUE" in query
    assert "JOIN stage_1 ON stage_2.c2_VALUE = stage_1.stage_1_c1_VALUE" in query


def test_cypher2oracle_sqlpgq_translates_scalar_with_match_comparison():
    query = _translate_sql(
        "MATCH (p:Policy {name: 'Compliance Policy 9'}) "
        "WITH p.effective_date AS target_date "
        "MATCH (other:Policy) "
        "WHERE other.effective_date > target_date "
        "RETURN other"
    )

    assert 'p."effective_date" AS target_date' in query
    assert 'other."effective_date" AS other_effective_date' in query
    assert "JOIN stage_1 ON stage_2.other_effective_date > stage_1.target_date" in query
    assert "SELECT stage_2.other_VALUE AS other_VALUE" in query


def test_cypher2oracle_sqlpgq_translates_scalar_with_match_comparison_with_path():
    query = _translate_sql(
        "MATCH (r:Resource {name: 'meeting Document'}) "
        "WITH r.created_date AS target_date "
        "MATCH (role:Role)-[:GrantsAccessTo]->(res:Resource) "
        "WHERE res.created_date > target_date "
        "RETURN DISTINCT role.name"
    )

    assert 'r."created_date" AS target_date' in query
    assert 'res."created_date" AS res_created_date' in query
    assert "JOIN stage_1 ON stage_2.res_created_date > stage_1.target_date" in query
    assert "SELECT DISTINCT stage_2.name AS name" in query


def test_cypher2oracle_sqlpgq_translates_cast_scalar_with_match_comparison():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (o:Order)-[oi:ORDERS]->(p:Product) "
        "WITH MAX(toFloat(oi.unitPrice)) AS maxUnitPrice "
        "MATCH (o:Order)-[oi:ORDERS]->(p:Product) "
        "WHERE toFloat(oi.unitPrice) = maxUnitPrice "
        "MATCH (c:Customer)-[:PURCHASED]->(o) "
        "RETURN c.companyName",
        edge_label_map={
            "ORDERS": ["Order_ORDERS_Product"],
            "PURCHASED": ["Customer_PURCHASED_Order"],
        },
        property_type_map={
            "Order": {},
            "Product": {},
            "Customer": {"companyName": "VARCHAR2(4000)"},
            "ORDERS": {"unitPrice": "VARCHAR2(4000)"},
            "Order_ORDERS_Product": {"unitPrice": "VARCHAR2(4000)"},
            "PURCHASED": {},
            "Customer_PURCHASED_Order": {},
        },
        strict_property_validation=True,
    )

    assert category == "Graph-IL Translatable"
    assert 'TO_NUMBER(oi."unitPrice") AS unitPrice' in query
    assert 'oi."unitPrice" AS oi_unitPrice' in query
    assert "JOIN stage_1 ON stage_2.oi_unitPrice = stage_1.maxUnitPrice" in query


def test_cypher2oracle_sqlpgq_translates_size_scalar_with_match_comparison():
    query = _translate_sql(
        "MATCH (a:Answer) "
        "WITH avg(size(a.body_markdown)) AS average_length "
        "MATCH (a:Answer) "
        "WHERE size(a.body_markdown) > average_length "
        "RETURN count(a) AS answer_count"
    )

    assert 'LENGTH(a."body_markdown") AS body_markdown' in query
    assert 'LENGTH(a."body_markdown") AS a_body_markdown_size' in query
    assert "JOIN stage_1 ON stage_2.a_body_markdown_size > stage_1.average_length" in query
    assert "SELECT COUNT(stage_2.a_VALUE) AS answer_count" in query


def test_cypher2oracle_sqlpgq_translates_scalar_with_match_property_map_correlation():
    query = _translate_sql(
        'MATCH (m:Movie {title: "Open Season"}) '
        "WITH m.year AS releaseYear "
        "MATCH (movies:Movie {year: releaseYear}) "
        "RETURN avg(movies.imdbRating) AS averageRating"
    )

    assert 'm."year" AS releaseYear' in query
    assert 'movies."year" AS movies_year' in query
    assert "JOIN stage_1 ON stage_2.movies_year = stage_1.releaseYear" in query
    assert "year = releaseYear" not in query


def test_cypher2oracle_sqlpgq_filters_with_match_on_stage_scalar_alias():
    query = _translate_sql(
        "MATCH (a:ASSET)-[:LOCATED_AT]->(l:LOCATION) "
        "WITH l, SUM(l.capacity) AS total_capacity "
        "MATCH (a:ASSET)-[:LOCATED_AT]->(l:LOCATION) "
        "WHERE total_capacity > 1000 "
        "RETURN a.asset_id, a.model, l.name"
    )

    assert "WHERE stage_1.total_capacity > 1000" in query
    assert "WHERE total_capacity > 1000" not in query


def test_cypher2oracle_sqlpgq_correlates_anonymous_property_map_scalar_alias():
    query = _translate_sql(
        "MATCH (u:User)-[:WROTE]->(r:Review)-[:REVIEWS]->(b:Business) "
        "WITH u.name AS userName, b.city AS businessCity "
        "MATCH (user:User {name: userName})-[:WROTE]->(:Review)"
        "-[:REVIEWS]->(:Business {city: businessCity}) "
        "RETURN DISTINCT userName"
    )

    assert 'with_corr_n1."city" AS with_corr_n1_city' in query
    assert "stage_2.with_corr_n1_city = stage_1.businessCity" in query
    assert 'city" = businessCity' not in query


def test_cypher2oracle_sqlpgq_orders_with_aggregate_alias_expression():
    query = _translate_sql(
        "MATCH (m:Movie)-[:IN_COLLECTION]->(c:Collection) "
        "WITH c, max(m.release_date) AS maxDate, min(m.release_date) AS minDate "
        "ORDER BY maxDate - minDate DESC LIMIT 5 "
        "RETURN c.name AS CollectionName, minDate, maxDate, maxDate - minDate AS DateRange"
    )

    assert "ORDER BY maxDate - minDate DESC" in query
    assert "maxDate - minDate AS maxDate_minDate" not in query
    assert "GROUP BY c_VALUE, c_name, maxDate_minDate" not in query


def test_cypher2oracle_sqlpgq_groups_by_hidden_aggregate_sort_property():
    query = _translate_sql(
        "MATCH (fp:FINANCIAL_PERIOD)<-[:BelongsTo]-(t:TRANSACTION {status: 'Completed'}) "
        "WHERE fp.start_date > date('2020-01-01') "
        "RETURN fp.period_id, sum(t.amount) AS total_amount "
        "ORDER BY fp.start_date"
    )

    assert 'fp."start_date" AS start_date' in query
    assert "GROUP BY period_id, start_date" in query
    assert "ORDER BY start_date" in query


def test_cypher2oracle_sqlpgq_counts_carried_with_vertex_after_match():
    query = _translate_sql(
        "MATCH (u:USER)-[:Initiates]->(t:TRANSACTION) "
        "WITH u, t "
        "MATCH (u)-[:Approves]->(:REPORT) "
        "RETURN COUNT(t) AS total_transactions"
    )

    assert "VERTEX_ID(t) AS stage_1_t_VALUE" in query
    assert "COUNT(stage_1.stage_1_t_VALUE) AS total_transactions" in query
    assert "COUNT(t)" not in query


def test_cypher2oracle_sqlpgq_aggregates_carried_with_vertex_property_after_match():
    query = _translate_sql(
        "MATCH (c:CUSTOMER)-[:BELONGS_TO]->(a:ACCOUNT)-[:INITIATED_BY]->(t:TRANSACTION) "
        "WITH c, a, t "
        "MATCH (a)-[:USED_DEVICE]->(d:DEVICE) "
        "WHERE d.risk_score > 0.8 "
        "RETURN AVG(t.amount) AS average_transaction_amount"
    )

    assert 't."amount" AS t_amount' in query
    assert "AVG(stage_1.t_amount) AS average_transaction_amount" in query
    assert "AVG(amount)" not in query


def test_cypher2oracle_sqlpgq_aggregates_carried_optional_vertex_property():
    query = _translate_sql(
        "MATCH (a:ACCOUNT)-[:USED_DEVICE]->(d:DEVICE) "
        "WITH a, d "
        "OPTIONAL MATCH (t:TRANSACTION)-[:INITIATED_BY]->(a) "
        "RETURN SUM(t.amount) AS total_transaction_amount, "
        "AVG(d.risk_score) AS average_device_risk_score"
    )

    assert 'd."risk_score" AS d_risk_score' in query
    assert "AVG(stage_1.d_risk_score) AS average_device_risk_score" in query
    assert "AVG(risk_score)" not in query


def test_cypher2oracle_sqlpgq_cross_joins_uncorrelated_second_match_after_with():
    query = _translate_sql(
        "MATCH (ou:ORGANIZATION_UNIT)<-[:AssignedTo]-(u:USER)-[:Approves]->(b:BUDGET) "
        "WHERE b.variance_threshold > 0.1 "
        "WITH ou, AVG(b.amount) AS avg_budget_amount "
        "MATCH (u)-[:Initiates]->(t:TRANSACTION)-[:GovernedBy]->(cr:COMPLIANCE_RULE) "
        "WHERE cr.regulation_standard = 'SOX' "
        "RETURN ou.name, avg_budget_amount"
    )

    assert "CROSS JOIN stage_1" in query
    assert "1 AS dummy_value" in query
    assert "stage_1.ou_name AS name" in query
    assert "stage_1.avg_budget_amount AS avg_budget_amount" in query


def test_cypher2oracle_sqlpgq_groups_by_resolved_alias_for_duplicate_property_names():
    query = _translate_sql(
        "MATCH (follower:USER)-[:FOLLOWS]->(followee:USER)"
        "-[:POSTS]->(t:TWEET {is_sensitive: true}) "
        "WITH follower, followee, t "
        "MATCH (follower)-[e:ENGAGES_WITH]->(t) "
        "RETURN follower.display_name, followee.display_name, COUNT(e) AS engagement_count"
    )

    assert 'follower."display_name" AS follower' in query
    assert 'followee."display_name" AS followee' in query
    assert "SELECT stage_1.follower AS follower, stage_1.followee AS followee" in query
    assert "GROUP BY stage_1.follower, stage_1.followee" in query
    assert "GROUP BY display_name" not in query
    assert 'follower."stage_1.display_name"' not in query
    assert "stage_1.followee.display_name" not in query


def test_cypher2oracle_sqlpgq_selects_second_stage_properties_after_with_match():
    query = _translate_sql(
        "MATCH (u:USER)-[:FOLLOWS]->(followed:USER) "
        "WITH u, COUNT(followed) AS follows_count "
        "WHERE follows_count >= 5 "
        "MATCH (u)-[:POSTS]->(t:TWEET)-[:ATTACHES_MEDIA]->(:MEDIA_ATTACHMENT) "
        "RETURN t.content, t.view_count ORDER BY t.view_count DESC LIMIT 20"
    )

    assert "SELECT stage_2.content AS content, stage_2.view_count AS view_count" in query
    assert "ORDER BY stage_2.t_view_count DESC" in query
    assert 't."content"' not in query.split("SELECT stage_2.content AS content", 1)[1]
    assert 't."view_count"' not in query.split("SELECT stage_2.content AS content", 1)[1]


def test_cypher2oracle_sqlpgq_groups_second_stage_property_after_distinct_with():
    query = _translate_sql(
        "MATCH (u:USER {verified_status: true})-[:MEMBER_OF_LIST]->(l:LIST {is_private: true}) "
        "WITH DISTINCT u "
        "MATCH (u)-[:POSTS]->(t:TWEET) "
        "RETURN t.language, AVG(t.view_count) AS avg_view_count"
    )

    assert "SELECT stage_2.language AS language, AVG(view_count) AS avg_view_count" in query
    assert "GROUP BY stage_2.language" in query
    assert 't."language"' not in query.split("SELECT stage_2.language AS language", 1)[1]


def test_cypher2oracle_sqlpgq_computes_with_scalar_expression_in_outer_select():
    query = _translate_sql(
        "MATCH (u:USER)-[:POSTS]->(t:TWEET) "
        "WITH u, SUM(t.like_count + t.retweet_count + t.reply_count) AS engagement_sum "
        "MATCH (u) "
        "RETURN u.display_name, u.followers_count + engagement_sum AS influence_score "
        "ORDER BY influence_score DESC LIMIT 10"
    )

    assert 'u."followers_count" + engagement_sum' not in query
    assert "stage_1.u_followers_count + stage_1.engagement_sum AS influence_score" in query
    assert "ORDER BY influence_score DESC" in query


def test_cypher2oracle_sqlpgq_rejects_unprojected_aggregate_in_with_where():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (u:USER)-[:POSTS]->(t:TWEET) "
        "WITH u WHERE u.followers_count > 1000 AND AVG(t.view_count) > 100 "
        "MATCH (u)-[:POSTS]->(t:TWEET) "
        "RETURN AVG(t.view_count) AS avg_view_count"
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_rejects_aggregate_in_match_where():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (t:TRANSACTION)-[:INITIATED_BY]->(a:ACCOUNT) "
        "WHERE a.account_id = 'ACC000000' AND t.amount > avg(t.amount) "
        "RETURN t"
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_rejects_duration_between_aggregate():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (a:ACCOUNT)-[ud:USED_DEVICE]->(d:DEVICE) "
        "RETURN AVG(duration.between(ud.session_start, ud.session_end)) "
        "AS avg_session_duration"
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_rejects_temporal_arithmetic_aggregate_without_cast():
    query, category = cypher2oracle_sqlpgq(
        "MATCH (a:ACCOUNT)-[u:USED_DEVICE]->(d:DEVICE) "
        "RETURN AVG(u.session_end - u.session_start) AS avg_session_duration",
        property_type_map={
            "USED_DEVICE": {
                "session_start": "TIMESTAMP",
                "session_end": "TIMESTAMP",
            }
        },
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_orders_with_match_by_staged_property_alias():
    query = _translate_sql(
        "MATCH (p:Product) WITH avg(p.unitPrice) AS avgPrice "
        "MATCH (p2:Product) WHERE p2.unitPrice < avgPrice "
        "RETURN p2 ORDER BY p2.unitPrice LIMIT 5"
    )

    assert 'p2."unitPrice" AS p2_unitPrice' in query
    assert "ORDER BY stage_2.p2_unitPrice" in query
    assert "ORDER BY unitPrice" not in query


def test_cypher2oracle_sqlpgq_translates_with_match_cross_stage_vertex_inequality():
    query = _translate_sql(
        'MATCH (toyStory:Movie {title: "Toy Story"})-[:IN_GENRE]->(genre:Genre) '
        "WITH toyStory, genre "
        "MATCH (genre)<-[:IN_GENRE]-(otherMovie:Movie) "
        "WHERE toyStory <> otherMovie "
        "RETURN DISTINCT otherMovie.title"
    )

    assert "VERTEX_ID(otherMovie) AS otherMovie_VALUE" in query
    assert "stage_2.otherMovie_VALUE <> stage_1.stage_1_toyStory_VALUE" in query
    assert "WHERE toyStory <> otherMovie" not in query


def test_cypher2oracle_sqlpgq_translates_scalar_with_split_count_projection():
    query = _translate_sql(
        "MATCH (p:Policy {review_status: 'Approved'})"
        "-[:Enforces]->(r:Role {is_compliant: true}) "
        "WITH r, SIZE(SPLIT(r.permissions_list, ',')) AS permission_count "
        "RETURN r.name AS role_name, r.description AS role_description, permission_count"
    )

    assert 'CASE WHEN r."permissions_list" IS NULL' in query
    assert "REGEXP_COUNT(r.\"permissions_list\", ',') + 1 END AS permission_count" in query
    assert "SELECT r_name AS role_name, r_description AS role_description" in query


def test_cypher2oracle_sqlpgq_translates_scalar_function_with_final_aggregate():
    query = _translate_sql(
        "MATCH (m:Movie)-[:IN_GENRE]->(g:Genre) "
        "WITH g.name AS genre, size(m.languages) AS languageCount "
        "RETURN genre, sum(languageCount) AS totalLanguages "
        "ORDER BY totalLanguages DESC LIMIT 5"
    )

    assert 'LENGTH(m."languages") AS languageCount' in query
    assert "SELECT genre AS genre, COALESCE(SUM(languageCount), 0) AS totalLanguages" in query
    assert "GROUP BY genre" in query


def test_cypher2oracle_sqlpgq_translates_string_size_to_length():
    query = _translate_sql("MATCH (q:Question) RETURN size(q.text) AS textLength")

    assert 'LENGTH(q."text") AS textLength' in query


def test_cypher2oracle_sqlpgq_translates_id_order_comparison():
    query = _translate_sql(
        "MATCH (m1:Movie)<-[:ACTED_IN]-(a:Actor)-[:ACTED_IN]->(m2:Movie) "
        "WHERE id(m1) < id(m2) "
        "RETURN m1.title, m2.title"
    )

    assert "WHERE VERTEX_ID(m1) < VERTEX_ID(m2)" in query
    assert "WHERE id(" not in query.lower()


def test_cypher2oracle_sqlpgq_rewrites_with_filter_element_equality_to_projected_ids():
    query = _translate_sql(
        "MATCH (neo4j:User {screen_name: 'neo4j'}) "
        "MATCH (neo4j)-[:FOLLOWS]->(followed:User) "
        "MATCH (mentioned:User)-[:POSTS]->(:Tweet)-[:MENTIONS]->(neo4j) "
        "WITH DISTINCT followed, mentioned "
        "WHERE followed = mentioned "
        "RETURN followed.screen_name AS users"
    )

    assert "WHERE followed_VALUE = mentioned_VALUE" in query
    assert "VERTEX_EQUAL(followed, mentioned)" not in query


def test_cypher2oracle_sqlpgq_uses_second_stage_property_alias_when_final_alias_differs():
    query = _translate_sql(
        "MATCH (aa1:AdministrativeArea)-[:Borders]->(aa2:AdministrativeArea) "
        "WITH aa1, COUNT(aa2) AS border_count "
        "WHERE border_count >= 3 "
        "MATCH (aa1)-[:ContainsPoi]->(poi:PointOfInterest) "
        "RETURN poi.name, poi.category, aa1.name"
    )

    assert 'poi."name" AS name' in query
    assert "SELECT stage_2.name AS poi" in query
    assert "stage_2.poi" not in query


def test_cypher2oracle_sqlpgq_uses_second_stage_aliases_for_renamed_properties():
    query = _translate_sql(
        "MATCH (u:USER)-[:Approves]->(r1:REPORT)-[:ConsolidatesInto]->(r2:REPORT) "
        "WITH u, r1, r2 "
        "MATCH (u2:USER)-[:Approves]->(r2) "
        "WHERE u.department <> u2.department "
        "RETURN u.user_id, u.department, u2.user_id AS consolidated_approver_id, "
        "u2.department AS consolidated_department"
    )

    assert 'u2."user_id" AS u2_user_id' in query
    assert 'u2."department" AS u2_department' in query
    assert "stage_2.u2_user_id AS consolidated_approver_id" in query
    assert "stage_2.u2_department AS consolidated_department" in query
    assert "stage_2.consolidated_approver_id" not in query
    assert "stage_2.consolidated_department" not in query


def test_cypher2oracle_sqlpgq_translates_left_tostring_and_safe_numeric_division():
    left_query = _translate_sql(
        "MATCH (p1:Person)-[:FOLLOWS]->(p2:Person) "
        "WHERE left(p1.name, 1) = left(p2.name, 1) "
        "RETURN p1.name LIMIT 3"
    )
    assert 'SUBSTR(p1."name", 1, 1) = SUBSTR(p2."name", 1, 1)' in left_query
    assert "left(" not in left_query.lower()

    tostring_query = _translate_sql(
        "MATCH (dd:DataDomain)<-[:BelongsTo]-(da:DataAsset) "
        "WITH dd, AVG(TOFLOAT(REPLACE(da.schema_version, 'v', ''))) AS avg_schema_version "
        "WHERE avg_schema_version > 2.0 "
        "RETURN dd.name AS DomainName, 'v' + TOSTRING(avg_schema_version) AS AverageSchemaVersion"
    )
    assert "'v' || TO_CHAR(avg_schema_version) AS AverageSchemaVersion" in tostring_query
    assert "TOSTRING" not in tostring_query

    division_query = _translate_sql(
        "MATCH (u:User) "
        "WITH u, u.following / toFloat(u.followers) AS ratio "
        "WHERE ratio > 2 "
        "RETURN u.screen_name, ratio"
    )
    assert 'u."following" / NULLIF(TO_NUMBER(u."followers"), 0) AS ratio' in division_query


def test_cypher2oracle_sqlpgq_translates_map_comparison_property_literals():
    query = _translate_sql("MATCH ()-[:INTERACTS45 {weight: {lt: 10}}]->() RETURN count(*)")

    assert 'e1."weight" < 10' in query
    assert "{lt:" not in query


def test_cypher2oracle_sqlpgq_translates_apoc_toset_collect_size_as_count_distinct():
    query = _translate_sql(
        "MATCH (p:Person)-[r:ACTED_IN]->(m:Movie) "
        "WITH p, size(apoc.coll.toSet(collect(r.roles))) AS roleDiversity "
        "RETURN p.name AS actor, roleDiversity ORDER BY roleDiversity DESC LIMIT 3"
    )

    assert "COUNT(DISTINCT roles) AS roleDiversity" in query
    assert "apoc.coll.toSet" not in query


def test_cypher2oracle_sqlpgq_auto_edge_names_avoid_future_node_names():
    query = _translate_sql(
        "MATCH (e1:Employee)-[:REQUESTS]->(a:Asset)<-[:REQUESTS]-(e2:Employee) "
        "WHERE e1.name = 'Donald Schultz' AND e2.name <> 'Donald Schultz' "
        "RETURN DISTINCT e2.name"
    )

    assert (
        '(e1 IS "Employee")-[e3 IS "REQUESTS"]->'
        '(a IS "Asset")<-[e4 IS "REQUESTS"]-(e2 IS "Employee")' in query
    )


def test_cypher2oracle_sqlpgq_qualifies_carried_with_match_return_variables():
    query = _translate_sql(
        "MATCH (c:Customer)-[:Initiates]->(pt:PaymentTransaction)-[:ProcessedFor]->(m:Merchant) "
        "WHERE m.category_code = 'Retail' "
        "WITH c, pt "
        "MATCH (pt)-[:HasRiskAssessment]->(ra:RiskAssessment) "
        "WHERE ra.score > 70 "
        "RETURN DISTINCT c LIMIT 10"
    )

    assert "SELECT DISTINCT stage_1.c_VALUE AS c" in query
    assert "\nSELECT DISTINCT c\n" not in query


def test_cypher2oracle_sqlpgq_orders_with_stage_by_expression_aliases():
    query = _translate_sql(
        "MATCH (p:Person)-[:CAST_FOR]->(m:Movie) "
        "MATCH (p)-[:CAST_FOR]->(v:Video) "
        "WITH p, COUNT(DISTINCT m) AS movie_count, COUNT(DISTINCT v) AS video_count "
        "WHERE movie_count > 0 AND video_count > 0 "
        "RETURN p.name AS actor, movie_count, video_count "
        "ORDER BY movie_count + video_count DESC LIMIT 3"
    )

    assert "ORDER BY movie_count + video_count DESC" in query
    assert "movie_count_video_count" not in query


def test_cypher2oracle_sqlpgq_groups_direct_with_projection_final_aggregate():
    query = _translate_sql(
        "MATCH (u:User)-[:WROTE]->(r:Review)-[:REVIEWS]->(b:Business) "
        "WITH b.city AS city, r.stars AS stars "
        "RETURN city, avg(stars) AS averageRating"
    )

    assert "SELECT city AS city, AVG(stars) AS averageRating" in query
    assert "GROUP BY city" in query


def test_cypher2oracle_sqlpgq_translates_complex_optional_aggregate_expression():
    query = _translate_sql(
        "MATCH (t:Tweet) "
        "OPTIONAL MATCH (t)-[:RETWEETS]->(r:Tweet) "
        "RETURN t, t.favorites + count(r) AS score ORDER BY score DESC LIMIT 3"
    )

    assert "stage_1.t_favorites + count(stage_2.r_VALUE) AS score" in query
    assert 't."favorites" + count(r)' not in query
    assert "GROUP BY stage_1.stage_1_t_VALUE, stage_1.t_favorites" in query


def test_cypher2oracle_sqlpgq_translates_complex_with_match_count_expression():
    query = _translate_sql(
        "MATCH (pc:ProductionCompany)<-[:PRODUCED_BY]-(m1:Movie)"
        "-[:DIRECTED_BY]->(d:Director {name: 'Director 15'}) "
        "WITH pc, m1 "
        "MATCH (pc)<-[:PRODUCED_BY]-(m2:Movie)-[:BELONGS_TO]->(g:Genre {name: 'Horror'}) "
        "RETURN pc.name AS ProductionCompany, COUNT(DISTINCT m1) + "
        "COUNT(DISTINCT m2) AS TotalDistinctMovies"
    )

    assert "VERTEX_ID(m2) AS m2_VALUE" in query
    assert (
        "COUNT(DISTINCT stage_1.stage_1_m1_VALUE) + "
        "COUNT(DISTINCT stage_2.m2_VALUE) AS TotalDistinctMovies" in query
    )


def test_cypher2oracle_sqlpgq_projects_properties_from_aliased_with_vertex():
    query = _translate_sql(
        "MATCH (c1:Character) WHERE c1.community = 735 "
        "MATCH (c1)--(c2:Character) "
        "WITH DISTINCT c2 AS character, c2.book1PageRank AS pageRank "
        "ORDER BY pageRank DESC LIMIT 10 "
        "RETURN character.name AS characterName, pageRank"
    )

    assert 'c2."name" AS character_name' in query
    assert "SELECT character_name AS characterName, pageRank AS pageRank" in query
    assert "character.name" not in query


def test_cypher2oracle_sqlpgq_translates_passthrough_with_final_aggregate():
    query = _translate_sql(
        "MATCH (g:Group)<-[:BelongsTo]-(u:User {department: 'Finance'})"
        "-[:AttemptsAccess]->(:AccessEvent)-[:Targets]->(:Resource {type: 'Database'}) "
        "WITH g, u "
        "RETURN g.name AS GroupName, COUNT(DISTINCT u) AS DistinctUsersCount"
    )

    assert "VERTEX_ID(g) AS g_VALUE" in query
    assert "VERTEX_ID(u) AS u_VALUE" in query
    assert "SELECT g_name AS GroupName, COUNT(DISTINCT u_VALUE) AS DistinctUsersCount" in query
    assert "GROUP BY g_name" in query


def test_cypher2oracle_sqlpgq_translates_two_stage_aggregate_with():
    query = _translate_sql(
        "MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent)-[:Targets]->(r:Resource) "
        "WITH u.department AS dept, u.User_id AS userId, "
        "COUNT(DISTINCT r.Resource_id) AS resourceCount "
        "WITH dept, AVG(resourceCount) AS avgResourcesPerUser "
        "ORDER BY avgResourcesPerUser DESC "
        "RETURN dept, avgResourcesPerUser"
    )

    assert "WITH stage_1 AS" in query
    assert 'u."department" AS dept' in query
    assert 'r."Resource_id" AS r_Resource_id' in query
    assert "COUNT(DISTINCT r_Resource_id) AS resourceCount" in query
    assert "GROUP BY dept, userId" in query
    assert "stage_2 AS" in query
    assert "AVG(resourceCount) AS avgResourcesPerUser" in query
    assert "GROUP BY dept" in query
    assert "ORDER BY avgResourcesPerUser DESC" in query


def test_cypher2oracle_sqlpgq_translates_two_stage_with_filter_before_second_aggregate():
    query = _translate_sql(
        "MATCH (u:User)-[:AssignedTempAccess]->(ta:TemporaryAccess) "
        "WITH u.department AS Department, u.User_id AS UserID, "
        "COUNT(ta) AS TempAccessCount "
        "WHERE Department IS NOT NULL "
        "WITH Department, AVG(TempAccessCount) AS AvgTempAccesses "
        "RETURN Department, AvgTempAccesses"
    )

    assert "WHERE Department IS NOT NULL" in query
    assert "COUNT(ta_VALUE) AS TempAccessCount" in query
    assert "GROUP BY Department, UserID" in query
    assert "AVG(TempAccessCount) AS AvgTempAccesses" in query
    assert "GROUP BY Department" in query
    assert "SELECT Department AS Department, AvgTempAccesses AS AvgTempAccesses" in query


def test_cypher2oracle_sqlpgq_groups_two_stage_final_aggregate_return():
    query = _translate_sql(
        "MATCH (m:Movie)-[:IN_GENRE]->(g:Genre) "
        "WITH g, m.languages AS languages "
        "WITH g, size(languages) AS languageCount "
        "RETURN g.name AS genre, avg(languageCount) AS avgLanguages "
        "ORDER BY avgLanguages DESC LIMIT 5"
    )

    assert "SELECT g_name AS genre, AVG(languageCount) AS avgLanguages" in query
    assert "GROUP BY g_name" in query
    assert "ORDER BY avgLanguages DESC" in query


def test_cypher2oracle_sqlpgq_keeps_two_stage_aggregate_function_argument_expression():
    query = _translate_sql(
        "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)<-[:ORDERS]-(o:Order) "
        "WITH s, o.freight AS freight WHERE freight IS NOT NULL "
        "WITH s, avg(toFloat(freight)) AS avgFreight "
        "ORDER BY avgFreight DESC LIMIT 3 "
        "RETURN s.companyName AS supplierName, avgFreight"
    )

    assert "AVG(TO_NUMBER(freight)) AS avgFreight" in query
    assert "TO_NUMBER_freight_" not in query


def test_cypher2oracle_sqlpgq_translates_size_collect_distinct_to_count():
    query = _translate_sql(
        "MATCH (d:Director)-[:DIRECTED]->(m:Movie) "
        "WITH d, size(collect(distinct m.countries)) AS numCountries "
        "WHERE numCountries > 3 "
        "RETURN d.name AS director, numCountries "
        "ORDER BY numCountries DESC LIMIT 5"
    )

    assert "COUNT(DISTINCT countries) AS numCountries" in query
    assert 'm."countries" AS countries' in query
    assert "LENGTH(collect" not in query


def test_cypher2oracle_sqlpgq_translates_size_collect_element_to_count():
    query = _translate_sql(
        "MATCH (d:Director)-[:DIRECTED]->(m:Movie) "
        "WHERE m.imdbRating > 8.0 "
        "WITH d, size(collect(m)) AS moviesDirected "
        "ORDER BY moviesDirected DESC "
        "RETURN d.name, moviesDirected LIMIT 1"
    )

    assert "COUNT(m_VALUE) AS moviesDirected" in query
    assert "VERTEX_ID(m) AS m_VALUE" in query
    assert "LENGTH(collect" not in query


def test_cypher2oracle_sqlpgq_carries_two_stage_with_vertex_properties_to_final_return():
    query = _translate_sql(
        "MATCH (p:Policy)-[:Enforces]->(r:Role)-[:GrantsAccessTo]->(res:Resource) "
        "WITH p, r, COUNT(res) AS resource_count "
        "WHERE resource_count > 3 "
        "WITH p, COUNT(r) AS role_count "
        "WHERE role_count >= 2 "
        "RETURN DISTINCT p.name"
    )

    assert 'p."name" AS p_name' in query
    assert "COUNT(r_VALUE) AS role_count" in query
    assert "GROUP BY p_VALUE, p_name" in query
    assert "SELECT DISTINCT p_name AS name" in query
    assert 'p."name" AS name' not in query


def test_cypher2oracle_sqlpgq_carries_two_stage_with_aliased_final_properties():
    query = _translate_sql(
        "MATCH (g:Group)<-[:BelongsTo]-(u:User)-[:AttemptsAccess]->(ae:AccessEvent) "
        "WITH g, u, COUNT(ae) AS user_access_count "
        "WITH g, AVG(user_access_count) AS avg_access_per_user "
        "RETURN g.name AS GroupName, avg_access_per_user AS AverageAccessPerUser"
    )

    assert 'g."name" AS g_name' in query
    assert "AVG(user_access_count) AS avg_access_per_user" in query
    assert "GROUP BY g_VALUE, g_name" in query
    assert "SELECT g_name AS GroupName" in query
    assert 'g."name" AS GroupName' not in query


def test_cypher2oracle_sqlpgq_translates_not_exists_pattern_predicate():
    query = _translate_sql(
        "MATCH (u:User) "
        "WHERE NOT EXISTS((u)-[:AttemptsAccess]->(:AccessEvent)) "
        "RETURN u.name, u.email"
    )

    assert "WITH base AS" in query
    assert 'MATCH (u IS "User")' in query
    assert "SELECT name, email" in query
    assert "WHERE NOT EXISTS" in query
    assert 'MATCH (u)-[e1 IS "AttemptsAccess"]->(n1 IS "AccessEvent")' in query
    assert "pp.u_VALUE = base.u_VALUE" in query


def test_cypher2oracle_sqlpgq_translates_pattern_predicate_inline_map_as_filter():
    query = _translate_sql(
        "MATCH (d:DIRECTOR) "
        "WHERE NOT EXISTS((d)<-[:DIRECTED_BY]-(m:MOVIE)"
        "-[:BELONGS_TO]->(:GENRE {name: 'Horror'})) "
        "RETURN d.name"
    )

    assert 'IS "GENRE"' in query
    assert "n1.\"name\" = 'Horror'" in query
    assert "GENRE_name_Horror" not in query


def test_cypher2oracle_sqlpgq_translates_exists_pattern_predicate_before_aggregate():
    query = _translate_sql(
        "MATCH (a1:Assertion)-[:Contradicts]->(a2:Assertion) "
        "WHERE EXISTS((a1)-[:ClassifiedUnder]->(:Domain)<-[:ClassifiedUnder]-(a2)) "
        "RETURN COUNT(*) AS contradiction_count"
    )

    assert "SELECT COUNT(*) AS contradiction_count" in query
    assert "WHERE EXISTS" in query
    assert 'MATCH (a1)-[e1 IS "ClassifiedUnder"]->(n1 IS "Domain")' in query
    assert '<-[e2 IS "ClassifiedUnder"]-(a2)' in query
    assert "pp.a1_VALUE = base.a1_VALUE" in query
    assert "pp.a2_VALUE = base.a2_VALUE" in query


def test_cypher2oracle_sqlpgq_translates_incoming_exists_pattern_predicate_in_and():
    query = _translate_sql(
        "MATCH (q:Question)-[:TAGGED]->(t:Tag {name: 'neo4j'}) "
        "WHERE EXISTS((q)<-[:ANSWERED]-(:Answer)) "
        "AND EXISTS((q)<-[:COMMENTED_ON]-(:Comment)) "
        "RETURN q.title"
    )

    assert "WITH base AS" in query
    assert "WHERE EXISTS" in query
    assert 'MATCH (q IS "Question")-[e1 IS "TAGGED"]->(t IS "Tag")' in query
    assert 'MATCH (n1 IS "Answer")-[e1 IS "ANSWERED"]->(q)' in query
    assert 'MATCH (n1 IS "Comment")-[e1 IS "COMMENTED_ON"]->(q)' in query
    assert "pp.q_VALUE = base.q_VALUE" in query
    assert "EXISTS((" not in query


def test_cypher2oracle_sqlpgq_translates_lowercase_exists_pattern_predicate_in_and():
    query = _translate_sql(
        "MATCH (m:Movie) "
        "WHERE m.released < '2000-01-01' AND exists((m)-[:IN_GENRE]->(:Genre)) "
        "RETURN m.title, m.imdbRating ORDER BY m.imdbRating DESC LIMIT 3"
    )

    assert "WITH base AS" in query
    assert "m.\"released\" < '2000-01-01'" in query
    assert "WHERE EXISTS" in query
    assert 'MATCH (m)-[e1 IS "IN_GENRE"]->(n1 IS "Genre")' in query
    assert "exists((" not in query


def test_cypher2oracle_sqlpgq_translates_raw_path_predicates_before_with_aggregate():
    query = _translate_sql(
        "MATCH (p)--(m:Movie) "
        "WHERE (p)-[:DIRECTED]->(m) AND (p)-[:ACTED_IN]->(m) "
        "WITH avg(m.budget) AS average_budget "
        "RETURN average_budget"
    )

    assert "WITH base AS" in query
    assert "stage_1 AS" in query
    assert "predicate_1 AS" in query
    assert "predicate_2 AS" in query
    assert "JOIN predicate_1 ON predicate_1.m_VALUE = base.m_VALUE" in query
    assert "JOIN predicate_2 ON predicate_2.m_VALUE = base.m_VALUE" in query
    assert 'MATCH (p)-[e1 IS "DIRECTED"]->(m)' in query
    assert 'MATCH (p)-[e1 IS "ACTED_IN"]->(m)' in query
    assert "WHERE EXISTS" not in query
    assert "[:DIRECTED]" not in query


def test_cypher2oracle_sqlpgq_translates_return_exists_pattern_predicate():
    query = _translate_sql(
        "MATCH (p:Policy)-[:Enforces]->(r:Role)-[:GrantsAccessTo]->(res:Resource) "
        "WHERE res.sensitivity_level = 'Confidential' "
        "RETURN EXISTS((p)-[:Enforces]->(r)-[:GrantsAccessTo]->(res)) AS policyExists"
    )

    assert "SELECT CASE WHEN EXISTS" in query
    assert "THEN 1 ELSE 0 END AS policyExists" in query
    assert "pp.p_VALUE = base.p_VALUE" in query
    assert "pp.r_VALUE = base.r_VALUE" in query
    assert "pp.res_VALUE = base.res_VALUE" in query


def test_cypher2oracle_sqlpgq_avoids_auto_edge_variable_collision():
    query = _translate_sql(
        "MATCH p = (n1:USER)-[e1:POSTS]-(x)-[]-(n2:USER) "
        "WHERE n1.username = 'robert00' "
        "RETURN p LIMIT 1"
    )

    assert "EDGE_ID(e1) AS p_e1_ID" in query
    assert "EDGE_ID(e2) AS p_e2_ID" in query
    assert query.count("AS p_e1_ID") == 1


def test_cypher2oracle_sqlpgq_translates_with_match_then_aggregate_with():
    query = _translate_sql(
        "MATCH (u:User)-[:BelongsTo]->(g:Group) "
        "WHERE g.member_count > 10 "
        "WITH u, g "
        "MATCH (u)-[:HasRole]->(r:Role)-[:GrantsAccessTo]->(res:Resource) "
        "WHERE res.sensitivity_level = 'Confidential' "
        "WITH u, g, COUNT(DISTINCT res) AS confidential_resource_count "
        "WHERE confidential_resource_count >= 1 "
        "RETURN u.name, g.name, confidential_resource_count"
    )

    assert "stage_3 AS" in query
    assert "JOIN stage_1 ON stage_2.u_VALUE = stage_1.stage_1_u_VALUE" in query
    assert "COUNT(DISTINCT stage_2.res_VALUE) AS confidential_resource_count" in query
    assert "WHERE confidential_resource_count >= 1" in query
    assert "SELECT u_name AS name, g_name AS name" in query


def test_cypher2oracle_sqlpgq_translates_uncorrelated_with_match_aggregate_cross_join():
    query = _translate_sql(
        "MATCH (u:User)-[:BelongsTo]->(g:Group) "
        "WITH g, COUNT(u) AS member_count "
        "MATCH (u:User)-[:AttemptsAccess]->(:AccessEvent)-[:Targets]->(r:Resource) "
        "WHERE r.sensitivity_level = 'high' "
        "RETURN AVG(member_count) AS average_member_count"
    )

    assert "CROSS JOIN stage_1" in query
    assert "COLUMNS (1 AS dummy_value)" in query
    assert "AVG(stage_1.member_count) AS average_member_count" in query


def test_cypher2oracle_sqlpgq_translates_standalone_optional_match_null_fallback():
    query = _translate_sql(
        "OPTIONAL MATCH (p:Policy)-[:Enforces]->(r:Role) "
        "RETURN p.name AS policy_name, r.name AS role_name"
    )

    assert query.startswith("WITH optional_rows AS")
    assert 'MATCH (p IS "Policy")-[e1 IS "Enforces"]->(r IS "Role")' in query
    assert "UNION ALL" in query
    assert "SELECT NULL AS policy_name, NULL AS role_name" in query
    assert "WHERE NOT EXISTS (SELECT 1 FROM optional_rows)" in query


def test_cypher2oracle_sqlpgq_translates_standalone_optional_match_count_fallback():
    query = _translate_sql(
        "OPTIONAL MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent) "
        "RETURN u.name AS UserName, COUNT(ae) AS AccessEventCount "
        "ORDER BY AccessEventCount DESC"
    )

    assert query.startswith("WITH optional_rows AS")
    assert "COUNT(ae_VALUE) AS AccessEventCount" in query
    assert "GROUP BY UserName" in query
    assert "SELECT NULL AS UserName, 0 AS AccessEventCount" in query
    assert query.strip().endswith("ORDER BY AccessEventCount DESC")


def test_cypher2oracle_sqlpgq_rejects_standalone_optional_match_count_star():
    query, category = cypher2oracle_sqlpgq(
        "OPTIONAL MATCH (u:User)-[:AttemptsAccess]->(ae:AccessEvent) RETURN count(*)",
        graph_name="G",
    )

    assert query == "Unable to Translate to Oracle SQL/PGQ"
    assert category == "Graph-IL Not Support"


def test_cypher2oracle_sqlpgq_translates_with_optional_match_as_left_join():
    query = _translate_sql(
        "MATCH (g:Group) "
        "WITH g ORDER BY g.created_date DESC LIMIT 1 "
        "OPTIONAL MATCH (g)<-[:BelongsTo]-(u:User) "
        "RETURN g.name AS GroupName, g.created_by AS CreatorName, "
        "COUNT(u) AS MemberCount"
    )

    assert "WITH stage_1 AS" in query
    assert "stage_2 AS" in query
    assert "FROM stage_1\nLEFT JOIN stage_2 ON stage_2.g_VALUE = stage_1.stage_1_g_VALUE" in query
    assert "COUNT(stage_2.u_VALUE) AS MemberCount" in query
    assert "JOIN stage_1" not in query


def test_cypher2oracle_sqlpgq_translates_match_optional_with_count_left_join():
    query = _translate_sql(
        "MATCH (q:Question)-[:TAGGED]->(t:Tag {name: 'neo4j'}) "
        "OPTIONAL MATCH (q)<-[:COMMENTED_ON]-(c:Comment) "
        "WITH q, count(c) AS commentCount "
        "RETURN q.title, commentCount"
    )

    assert "LEFT JOIN stage_2 ON stage_2.q_VALUE = stage_1.stage_1_q_VALUE" in query
    assert "stage_1.stage_1_q_VALUE AS q_VALUE" in query
    assert "COUNT(stage_2.c_VALUE) AS commentCount" in query
    assert "GROUP BY stage_1.stage_1_q_VALUE, stage_1.q_title" in query


def test_cypher2oracle_sqlpgq_carries_base_only_variable_in_match_optional_with():
    query = _translate_sql(
        "MATCH (p:Product)-[:PART_OF]->(category:Category) "
        "OPTIONAL MATCH (p)<-[o:ORDERS]-(:Order) "
        "WITH category.categoryName AS categoryName, "
        "SUM(toInteger(o.quantity)) AS totalQuantityOrdered "
        "RETURN categoryName, totalQuantityOrdered"
    )

    assert 'category."categoryName" AS categoryName' in query
    assert "LEFT JOIN stage_2 ON stage_2.p_VALUE = stage_1.stage_1_p_VALUE" in query
    assert "stage_1.categoryName AS categoryName" in query
    assert "GROUP BY stage_1.categoryName" in query


def test_cypher2oracle_sqlpgq_keeps_optional_null_where_in_optional_stage():
    query = _translate_sql(
        "MATCH (q:Question) "
        "OPTIONAL MATCH (q)<-[:COMMENTED_ON]-(c:Comment) "
        "WHERE c IS NULL "
        "RETURN q.title"
    )

    assert "LEFT JOIN stage_2 ON stage_2.q_VALUE = stage_1.stage_1_q_VALUE" in query
    assert 'MATCH (c IS "Comment")-[e1 IS "COMMENTED_ON"]->(q)' in query
    assert "WHERE c IS NULL" in query
    assert "OPTIONAL MATCH" not in query
