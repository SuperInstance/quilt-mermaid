"""
quilt_mermaid.py — Render a Quilt canon citation graph (or cell fleet) as
a Mermaid `flowchart` block. Embeddable in any GitHub README.

Usage:
    python3 quilt_mermaid.py --canon > canon.mmd
    python3 quilt_mermaid.py --fleet > fleet.mmd
    python3 quilt_mermaid.py --canon --top 20 > canon-top-20.mmd
    python3 quilt_mermaid.py --canon --cite hub-tag --top 5

Output is a Mermaid block you can paste into any Markdown file.
GitHub renders it as an interactive graph.
"""
from __future__ import annotations
import os, sys, json, time, urllib.request, urllib.error, argparse
from typing import Iterable

DEFAULT_CANON = "https://a2a-v3.superinstance.dev"
DEFAULT_FLEET = "https://a2a-v3.superinstance.dev"


def fetch(url: str, headers: dict | None = None) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "quilt-mermaid/1.0", **(headers or {})})
    for attempt in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code}: {url}", file=sys.stderr)
            return None
        except Exception as e:
            time.sleep(2)
    return None


def fetch_canon_graph(base: str) -> dict:
    """Fetch the live citation graph from the canon worker."""
    data = fetch(f"{base}/canon-graph")
    if not data:
        return {"nodes": [], "edges": []}
    return data


def fetch_fleet_graph(base: str) -> dict:
    """Fetch the live cell fleet from the worker."""
    data = fetch(f"{base}/visual/graph.json")
    if not data:
        return {"cells": [], "workspaces": {}}
    return data


def _sanitize_id(s: str) -> str:
    """Make a string safe for use as a Mermaid node id."""
    out = []
    for ch in s:
        if ch.isalnum() or ch in "_-":
            out.append(ch)
        else:
            out.append("_")
    return "n" + "".join(out)[:60]


def _label(s: str, max_len: int = 32) -> str:
    """Sanitize for Mermaid label (escape brackets/quotes)."""
    s = s.replace('"', "'").replace('[', '(').replace(']', ')')
    if len(s) > max_len:
        s = s[:max_len - 3] + "..."
    return s


def _node_shape(role: str) -> str:
    """Map a cell role to a Mermaid node shape."""
    return {
        "advisor": "([{}])",       # stadium
        "ensemble": "{{}}",       # rhombus
        "polyformal": "[/{}/]",     # parallelogram
        "shaper": "((( {} )))",     # double circle
        "test": "({})",             # rounded
        "test-runner": "[{}]",      # rect
        "cell-router": "{{{}}}",      # diamond
    }.get(role, "[{}]")  # default rect


def _color_for_role(role: str) -> str:
    return {
        "advisor": "#5c99d4",
        "ensemble": "#9a60d9",
        "polyformal": "#7ee787",
        "shaper": "#f7a026",
        "test": "#888888",
        "test-runner": "#a5a5ff",
        "cell-router": "#ffa657",
    }.get(role, "#c9d1d9")


def render_canon(graph: dict, top: int | None = None, hub: str | None = None, depth: int = 1) -> str:
    """Render the canon citation graph as Mermaid."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return "```mermaid\nflowchart LR\n  empty[No canon pieces]\n```\n"

    # Optionally filter to top-N most-connected nodes
    if top and len(nodes) > top:
        # Compute degree
        deg = {n["id"]: 0 for n in nodes}
        for e in edges:
            deg[e["source"]] = deg.get(e["source"], 0) + 1
            deg[e["target"]] = deg.get(e["target"], 0) + 1
        keep = set(sorted(deg.keys(), key=lambda x: -deg[x])[:top])
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]

    if hub:
        # Keep only nodes within `depth` hops of hub
        adj = {n["id"]: set() for n in nodes}
        for e in edges:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])
        keep = {hub}
        frontier = {hub}
        for _ in range(depth):
            new_frontier = set()
            for n in frontier:
                for m in adj.get(n, set()):
                    if m not in keep:
                        keep.add(m)
                        new_frontier.add(m)
            frontier = new_frontier
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]

    out = ["```mermaid", "flowchart LR"]

    # Group by inferred workspace for subgraphs
    def ws(tag: str) -> str:
        if tag.startswith("auto-"): return "auto"
        if tag.startswith("bridge-"): return "bridges"
        if tag.startswith("paper_") or tag.startswith("essay"): return "papers"
        if tag.startswith("grow-"): return "grown"
        if tag.startswith("ai-") or tag.startswith("fable"): return "ai-writings"
        if tag.startswith("taps-"): return "taps"
        return "topical"

    by_ws: dict[str, list] = {}
    for n in nodes:
        w = ws(n["id"])
        by_ws.setdefault(w, []).append(n)

    for w, ns in sorted(by_ws.items()):
        if len(by_ws) > 1:
            out.append(f"  subgraph {w}")
        for n in ns:
            nid = _sanitize_id(n["id"])
            title = n.get("title") or n["id"]
            cites = n.get("cites", [])
            label = _label(title)
            count = len(cites)
            if count > 0:
                out.append(f'    {nid}["{label}"]:::cite{count}')
            else:
                out.append(f'    {nid}["{label}"]')
        if len(by_ws) > 1:
            out.append("  end")

    # Edges
    out.append("")
    for e in edges:
        s = _sanitize_id(e["source"])
        t = _sanitize_id(e["target"])
        out.append(f"  {s} --> {t}")

    # Class defs
    out.append("")
    for c in [1, 2, 3, 4, 5, 10]:
        out.append(f"  classDef cite{c} fill:#0d1117,stroke:#4fb3a9,color:#c9d1d9,stroke-width:{1 + c // 3}px;")

    out.append("```")
    return "\n".join(out)


def render_fleet(graph: dict, top: int | None = None) -> str:
    """Render the cell fleet as Mermaid."""
    cells = graph.get("cells", [])
    workspaces = graph.get("workspaces", {})

    if top and len(cells) > top:
        cells = cells[:top]

    out = ["```mermaid", "flowchart TB"]

    # Group by workspace
    by_ws: dict[str, list] = {}
    for c in cells:
        ws_name = c.get("workspace") or "(default)"
        by_ws.setdefault(ws_name, []).append(c)

    for ws_name, cs in sorted(by_ws.items(), key=lambda x: -len(x[1])):
        out.append(f'  subgraph {ws_name}["{ws_name}"]')
        for c in cs:
            nid = _sanitize_id(c["id"])
            role = c.get("role") or "?"
            label = _label(f'{c["id"]}\\n({role})')
            shape = _node_shape(role)
            try:
                out.append(f"    {nid}{shape.format(label)}")
            except KeyError:
                # rhombus uses double braces — escape
                out.append(f"    {nid}{shape.replace('{{}}', '{label}')}")
        out.append("  end")

    # Parent-of edges (heritage)
    out.append("")
    for c in cells:
        if c.get("parent"):
            s = _sanitize_id(c["parent"])
            t = _sanitize_id(c["id"])
            out.append(f"  {s} -.-> {t}")

    out.append("```")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canon", action="store_true", help="Render the canon citation graph")
    ap.add_argument("--fleet", action="store_true", help="Render the cell fleet graph")
    ap.add_argument("--base", default=os.environ.get("QUILT_A2A", DEFAULT_CANON),
                    help="a2a-v3 worker URL")
    ap.add_argument("--top", type=int, default=None, help="Limit to top-N most-cited")
    ap.add_argument("--cite", dest="hub", default=None,
                    help="Hub tag — keep only nodes within `--depth` of this tag")
    ap.add_argument("--depth", type=int, default=1)
    args = ap.parse_args()

    if not (args.canon or args.fleet):
        ap.error("Specify --canon or --fleet")

    if args.canon:
        g = fetch_canon_graph(args.base)
        print(render_canon(g, top=args.top, hub=args.hub, depth=args.depth))
    else:
        g = fetch_fleet_graph(args.base)
        print(render_fleet(g, top=args.top))


if __name__ == "__main__":
    main()
