"""RelationshipGraph unit tests (spine/graph.py). Pure, no DB.

Tests run entirely on in-memory entity/edge dicts — the ``RelationshipGraph`` class
has no Postgres dependency by design.

Covers: direct 1-hop resolution via dst_id, name-slug fallback (the core bug fix),
2-hop paths, target-type filtering, RELATIONAL_KINDS exclusion, unresolvable edges,
and max_hops bounds.
"""
from apps.matchmaker.graph import (
    RELATIONAL_KINDS,
    GraphPath,
    Hop,
    RelationshipGraph,
    build_graph,
    path_to_dict,
)


def _entity(eid, name, type_="startup"):
    return {"id": eid, "name": name, "type": type_}


def _edge(src, dst_id, dst_name, kind, src_url=None):
    return {"src_id": src, "dst_id": dst_id, "dst_name": dst_name,
            "kind": kind, "source_url": src_url}


def test_1hop_via_dst_id():
    """A direct 1-hop match resolves correctly when dst_id already matches."""
    entities = [_entity("startup:a", "Startup A"),
                _entity("investor:x", "Investor X", "investor")]
    edges = [_edge("startup:a", "investor:x", "Investor X", "raised_from",
                   "https://example.com")]
    graph = build_graph(entities, edges)
    paths = graph.find_paths("startup:a")
    assert len(paths) == 1
    p = paths[0]
    assert p.target_id == "investor:x"
    assert p.target_name == "Investor X"
    assert p.target_type == "investor"
    assert p.distance == 1
    assert len(p.hops) == 1
    assert p.hops[0].kind == "raised_from"
    assert p.hops[0].hop == 1


def test_1hop_via_name_slug_fallback():
    """A 1-hop match resolves via name-slug fallback when dst_id is an unresolved
    'name:{slug}' placeholder but dst_name matches a real entity — this is the core
    dst_resolved bug workaround, test it explicitly."""
    entities = [_entity("startup:a", "Startup A"),
                _entity("investor:x", "Investor X", "investor")]
    edges = [_edge("startup:a", "name:investor-x", "Investor X", "raised_from",
                   "https://example.com")]
    graph = build_graph(entities, edges)
    paths = graph.find_paths("startup:a")
    assert len(paths) == 1
    p = paths[0]
    assert p.target_id == "investor:x"
    assert p.distance == 1


def test_2hop_path():
    """A 2-hop path is found and hops are in the correct order/direction.

    startup:a --invested_in--> investor:x --raised_from--> corporation:y
    """
    entities = [_entity("startup:a", "Startup A"),
                _entity("investor:x", "Investor X", "investor"),
                _entity("corporation:y", "Corp Y", "corporation")]
    edges = [
        _edge("investor:x", "startup:a", "Startup A", "invested_in"),
        _edge("investor:x", "corporation:y", "Corp Y", "raised_from"),
    ]
    graph = build_graph(entities, edges)
    paths = graph.find_paths("startup:a", max_hops=2)
    # Should find both 1-hop and 2-hop targets
    targets = {p.target_id: p for p in paths}
    assert "investor:x" in targets
    assert targets["investor:x"].distance == 1
    assert "corporation:y" in targets
    assert targets["corporation:y"].distance == 2
    assert targets["corporation:y"].hops[0].kind == "invested_in"
    assert targets["corporation:y"].hops[1].kind == "raised_from"
    assert targets["corporation:y"].hops[0].hop == 1
    assert targets["corporation:y"].hops[1].hop == 2


def test_target_types_filter():
    """target_types filtering excludes non-matching types."""
    entities = [_entity("startup:a", "Startup A"),
                _entity("investor:x", "Investor X", "investor"),
                _entity("university:u", "Uni U", "university")]
    edges = [
        _edge("startup:a", "investor:x", "Investor X", "raised_from"),
        _edge("startup:a", "university:u", "Uni U", "partner_with"),
    ]
    graph = build_graph(entities, edges)
    paths = graph.find_paths("startup:a", max_hops=2,
                             target_types={"investor"})
    assert len(paths) == 1
    assert paths[0].target_type == "investor"
    assert paths[0].target_id == "investor:x"


def test_non_relational_kind_excluded():
    """An edge whose kind is not in RELATIONAL_KINDS (e.g. founded_by_alumni_of)
    is NOT traversed."""
    entities = [_entity("startup:a", "Startup A"),
                _entity("investor:x", "Investor X", "investor")]
    edges = [_edge("startup:a", "investor:x", "Investor X", "founded_by_alumni_of")]
    graph = build_graph(entities, edges)
    assert "founded_by_alumni_of" not in RELATIONAL_KINDS
    paths = graph.find_paths("startup:a")
    assert len(paths) == 0


def test_unresolvable_edge_skipped():
    """An edge pointing to a name with no matching entity produces no path (doesn't
    crash, doesn't fabricate a node)."""
    entities = [_entity("startup:a", "Startup A")]
    edges = [_edge("startup:a", "name:nobody", "Nobody Real Corp", "raised_from")]
    graph = build_graph(entities, edges)
    paths = graph.find_paths("startup:a")
    assert len(paths) == 0


def test_max_hops_respected():
    """max_hops is respected — a target 3 hops away is not returned when max_hops=2."""
    entities = [
        _entity("startup:a", "Startup A"),
        _entity("investor:x", "Investor X", "investor"),
        _entity("corporation:y", "Corp Y", "corporation"),
    ]
    # startup:a <-> investor:x <-> corporation:y  (2 hops from a to y)
    # Add a 3-hop path: startup:a <-> investor:x <-> corporation:y via extra node
    # Actually with 3 entities the max path is already 2 hops.
    # Let's add a 4th entity to make a 3-hop path:
    entities.append(_entity("investor:z", "Investor Z", "investor"))
    edges = [
        _edge("investor:x", "startup:a", "Startup A", "invested_in"),
        _edge("investor:x", "corporation:y", "Corp Y", "partner_with"),
        _edge("corporation:y", "investor:z", "Investor Z", "raised_from"),
    ]
    graph = build_graph(entities, edges)

    # With max_hops=1: only direct neighbors of a
    paths1 = graph.find_paths("startup:a", max_hops=1)
    assert len(paths1) == 1
    assert paths1[0].target_id == "investor:x"

    # With max_hops=2: should find investor:x (1-hop) and corporation:y (2-hop)
    paths2 = graph.find_paths("startup:a", max_hops=2)
    targets2 = {p.target_id for p in paths2}
    assert "investor:x" in targets2
    assert "corporation:y" in targets2
    # investor:z is 3 hops away, should NOT be found
    assert "investor:z" not in targets2


def test_path_to_dict_roundtrip():
    """path_to_dict produces the expected JSON-serializable shape."""
    p = GraphPath(
        target_id="investor:x",
        target_name="Investor X",
        target_type="investor",
        hops=[
            Hop(from_id="startup:a", to_id="investor:x", kind="raised_from",
                source_url="https://example.com", hop=1),
        ],
    )
    d = path_to_dict(p)
    assert d == {
        "target_id": "investor:x",
        "target_name": "Investor X",
        "target_type": "investor",
        "distance": 1,
        "path": [
            {"from_id": "startup:a", "to_id": "investor:x", "kind": "raised_from",
             "source_url": "https://example.com", "hop": 1},
        ],
    }


def test_build_graph_factory():
    """build_graph returns a RelationshipGraph."""
    entities = [_entity("startup:a", "Startup A")]
    graph = build_graph(entities, [])
    assert isinstance(graph, RelationshipGraph)
