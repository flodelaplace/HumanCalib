#!/usr/bin/env python3
"""Co-visibility diagnostic for partial-overlap calibration sequences.

For each (camera, frame) decides whether the person is *well seen* — enough
confident joints AND a large enough 2D spread — while ignoring dark/aberrant
frames (their scores are already zeroed by ``detect_outlier_frames.py``; if a
``--video_dir`` is given, sidecar ``<video>.dropped.json`` drops are excluded
too). It then builds the C×C matrix of co-visible well-seen frames per camera
pair, the co-visibility graph (edge if shared frames >= ``--min_covis``), and
reports:

  * total well-seen frames per camera,
  * connected components (cameras with no reliable link are NOT calibrable
    from this sequence and are flagged explicitly — never invented),
  * the weakest links / bridges (edges whose removal disconnects the graph),
  * a heatmap PNG of the co-visibility matrix.

This is a *diagnostic only* — it never modifies poses or calibration files.

Usage:
    python -m humancalib.tools.covisibility_report \\
        --prefix ./output/my_session \\
        --subset noise_1_0 --aid 1 --pid 1 --gid 1 \\
        --video_dir ./input/my_session \\
        --min_covis 50
"""
import argparse
import os
import sys

import numpy as np


from humancalib.core import load_poses, load_eldersim_camera
from humancalib.core.sidecars import read_dropped
from humancalib.core.videos import list_videos


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prefix", required=True)
    p.add_argument("--subset", default="noise_1_0")
    p.add_argument("--aid", type=int, default=1)
    p.add_argument("--pid", type=int, default=1)
    p.add_argument("--gid", type=int, default=1)
    p.add_argument("--video_dir", default=None,
                   help="Optional: exclude sidecar-dropped frames and label cameras by serial.")
    p.add_argument("--conf_threshold", type=float, default=0.5)
    p.add_argument("--min_joints", type=int, default=15,
                   help="Min #joints above conf_threshold for a frame to count as well-seen.")
    p.add_argument("--min_spread", type=float, default=80.0,
                   help="Min 2D bbox diagonal (px) of confident joints for a well-seen frame.")
    p.add_argument("--min_covis", type=int, default=50,
                   help="Min #co-visible well-seen frames for a graph edge between two cameras.")
    p.add_argument("--out", default=None,
                   help="Heatmap PNG path (default: <prefix>/results/covisibility.png).")
    return p.parse_args()


def load_all_2d(prefix, subset, aid, pid, gid, camid):
    """Load per-camera 2D poses. Frame indices are assumed identical across cams."""
    p2d_all, s2d_all = [], []
    frame_indices = None
    for cid in camid:
        fname = f"A{aid:03d}_P{pid:03d}_G{gid:03d}_C{int(cid):03d}.json"
        f2d, p2d, s2d = load_poses(os.path.join(prefix, subset, "2d_joint", fname))
        if frame_indices is None:
            frame_indices = np.array([int(f) for f in f2d])
        n_joints = s2d.shape[1]
        p2d_all.append(p2d.reshape(-1, n_joints, 2))
        s2d_all.append(s2d)
    return frame_indices, np.array(p2d_all), np.array(s2d_all)


def load_dropped(prefix, subset, video_dir, camid):
    """Return {cam_idx: set(absolute frame indices)} from the dropped-frame sidecars.

    Maps cameras to videos the same way the rest of the pipeline does: sorted
    video filenames aligned to the CAMID order.
    """
    if not video_dir:
        return {}, {}
    videos = list_videos(video_dir)
    if len(videos) != len(camid):
        print(f"  WARN: {len(videos)} videos vs {len(camid)} cams — skipping sidecar drops.")
        return {}, {}
    dropped, serials = {}, {}
    for c, v in enumerate(videos):
        serials[c] = os.path.splitext(os.path.basename(v))[0]
        idx = read_dropped(prefix, subset, v)
        if idx:
            dropped[c] = idx
        else:
            dropped[c] = set()
    return dropped, serials


def compute_well_seen(p2d, s2d, frame_indices, dropped, conf, min_joints, min_spread):
    """Return (C, N) bool: person well seen by camera c at frame index f."""
    C, N, J, _ = p2d.shape
    conf_mask = s2d > conf                       # C, N, J
    n_conf = conf_mask.sum(axis=2)               # C, N

    spread = np.zeros((C, N))
    for c in range(C):
        for f in range(N):
            m = conf_mask[c, f]
            if m.sum() >= 2:
                pts = p2d[c, f, m, :]
                d = pts.max(axis=0) - pts.min(axis=0)
                spread[c, f] = float(np.hypot(d[0], d[1]))

    well = (n_conf >= min_joints) & (spread >= min_spread)

    # Exclude sidecar-dropped frames (matched by absolute frame index)
    for c, frames in dropped.items():
        if not frames:
            continue
        drop_pos = np.isin(frame_indices, list(frames))
        well[c, drop_pos] = False
    return well


def connected_components(adj):
    """adj: C×C bool (symmetric, no self). Returns list of sorted node lists."""
    C = adj.shape[0]
    seen = [False] * C
    comps = []
    for start in range(C):
        if seen[start]:
            continue
        stack, comp = [start], []
        seen[start] = True
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in range(C):
                if adj[u, v] and not seen[v]:
                    seen[v] = True
                    stack.append(v)
        comps.append(sorted(comp))
    return comps


def find_bridges(adj):
    """Tarjan bridge finding. adj: C×C bool symmetric. Returns list of (u, v) edges."""
    C = adj.shape[0]
    disc = [-1] * C
    low = [0] * C
    timer = [0]
    bridges = []

    def dfs(u, parent):
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in range(C):
            if not adj[u, v]:
                continue
            if disc[v] == -1:
                dfs(v, u)
                low[u] = min(low[u], low[v])
                if low[v] > disc[u]:
                    bridges.append((min(u, v), max(u, v)))
            elif v != parent:
                low[u] = min(low[u], disc[v])

    sys.setrecursionlimit(10000)
    for u in range(C):
        if disc[u] == -1:
            dfs(u, -1)
    return bridges


def save_heatmap(M, labels, out_path, min_covis):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # pragma: no cover
        print(f"  WARN: matplotlib unavailable, skipping heatmap ({e})")
        return
    C = M.shape[0]
    fig, ax = plt.subplots(figsize=(1.1 * C + 2, 1.1 * C + 1))
    Mshow = M.astype(float).copy()
    np.fill_diagonal(Mshow, np.nan)
    im = ax.imshow(Mshow, cmap="viridis")
    ax.set_xticks(range(C)); ax.set_yticks(range(C))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(labels, fontsize=8)
    for i in range(C):
        for j in range(C):
            if i == j:
                continue
            v = int(M[i, j])
            color = "white" if v < np.nanmax(Mshow) * 0.6 else "black"
            weak = "" if v >= min_covis else "✗"
            ax.text(j, i, f"{v}{weak}", ha="center", va="center", color=color, fontsize=7)
    ax.set_title(f"Co-visible well-seen frames per camera pair (edge if ≥ {min_covis})")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  Heatmap saved -> {out_path}")


def main():
    args = parse_args()

    cam_file = os.path.join(args.prefix, args.subset, f"cameras_G{args.gid:03d}.json")
    CAMID, _, _, _, _ = load_eldersim_camera(cam_file)
    n_cams = len(CAMID)

    frame_indices, p2d, s2d = load_all_2d(
        args.prefix, args.subset, args.aid, args.pid, args.gid, CAMID)
    dropped, serials = load_dropped(args.prefix, args.subset, args.video_dir, CAMID)
    labels = [serials.get(c, f"CAM{int(CAMID[c])}") for c in range(n_cams)]

    print("=" * 70)
    print("CO-VISIBILITY REPORT")
    print("=" * 70)
    print(f"  Cameras       : {n_cams}  ({', '.join(str(int(c)) for c in CAMID)})")
    print(f"  Frames        : {len(frame_indices)}  "
          f"({int(frame_indices[0])}-{int(frame_indices[-1])})")
    print(f"  well-seen rule: >= {args.min_joints} joints @ conf>{args.conf_threshold} "
          f"AND 2D spread >= {args.min_spread}px")
    print(f"  edge rule     : >= {args.min_covis} co-visible well-seen frames")
    print("-" * 70)

    well = compute_well_seen(p2d, s2d, frame_indices, dropped,
                             args.conf_threshold, args.min_joints, args.min_spread)

    # C×C co-visibility counts; diagonal = total well-seen frames per camera
    W = well.astype(np.int64)
    M = W @ W.T

    print("Well-seen frames per camera:")
    for c in range(n_cams):
        print(f"  [{c}] {labels[c]:<28} {int(M[c, c]):5d} frames")
    print("-" * 70)

    adj = (M >= args.min_covis)
    np.fill_diagonal(adj, False)

    # Isolated cameras = no edge at all
    degrees = adj.sum(axis=1)
    isolated = [c for c in range(n_cams) if degrees[c] == 0]

    comps = connected_components(adj)
    bridges = find_bridges(adj)

    print(f"Graph: {int(adj.sum() // 2)} edges, {len(comps)} connected component(s)")
    for i, comp in enumerate(comps):
        names = ", ".join(labels[c] for c in comp)
        tag = "  <-- SINGLE CAMERA, NOT CALIBRABLE" if len(comp) == 1 else ""
        print(f"  Component {i}: [{', '.join(str(c) for c in comp)}]  {names}{tag}")

    if isolated:
        print("\n⚠ ISOLATED cameras (share < min_covis frames with EVERY other camera):")
        for c in range(n_cams):
            if c in isolated:
                best = sorted(((int(M[c, d]), labels[d]) for d in range(n_cams) if d != c),
                              reverse=True)[:3]
                best_str = ", ".join(f"{name}:{cnt}" for cnt, name in best)
                print(f"    {labels[c]} — best partners: {best_str}")
        print("    -> NOT calibrable from this sequence; flagged, not invented.")

    print("\nWeakest links (bridges — removal disconnects the graph):")
    if bridges:
        for u, v in sorted(bridges, key=lambda e: M[e[0], e[1]]):
            print(f"    {labels[u]} <-> {labels[v]}: {int(M[u, v])} frames")
    else:
        print("    none (graph has no bridges — robust to single-edge loss)")

    # Per-camera weakest accepted edge (translation is poorly constrained on thin links)
    print("\nPer-camera connectivity (degree / weakest accepted edge):")
    for c in range(n_cams):
        if degrees[c] == 0:
            print(f"  {labels[c]:<28} degree 0  (isolated)")
            continue
        edge_counts = [(int(M[c, d]), labels[d]) for d in range(n_cams) if adj[c, d]]
        weakest = min(edge_counts)
        print(f"  {labels[c]:<28} degree {int(degrees[c])}  "
              f"weakest: {weakest[1]}:{weakest[0]}")

    out_path = args.out or os.path.join(args.prefix, "results", "covisibility.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    save_heatmap(M, labels, out_path, args.min_covis)

    print("=" * 70)


if __name__ == "__main__":
    main()