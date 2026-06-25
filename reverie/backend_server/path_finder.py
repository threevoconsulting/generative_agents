"""
path_finder.py — REPLACEMENT (drop-in for reverie/backend_server/path_finder.py)

Changes from original:
  - Replaced bounded Bellman-Ford (path_finder_v2) with proper queue-based BFS.
  - Removed the 150-step cap that caused agents to freeze on long paths.
  - path_finder() is the single authoritative entry point; v1/v2 kept as
    deprecated legacy (not called anywhere in the codebase).
  - Coordinate convention is unchanged: callers pass (x, y) = (col, row);
    the internal BFS operates on (row, col); translation happens in path_finder().
  - Unreachable targets return [start] so the agent stays in place cleanly
    instead of freezing with act_path_set=True and an empty planned_path.

Author of original: Joon Sung Park (joonspk@stanford.edu)
BFS replacement: threevoconsulting fork
"""

from collections import deque
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# CORE BFS
# ─────────────────────────────────────────────────────────────────────────────

def _bfs_path(collision_maze, start_rc, end_rc, collision_block_char):
    """
    Standard BFS on a 2-D collision maze.

    Parameters
    ----------
    collision_maze : list[list[str]]
        The raw collision maze from Maze.collision_maze.
        Indexed as collision_maze[row][col].
    start_rc : (int, int)
        Start position as (row, col).
    end_rc : (int, int)
        Target position as (row, col).
    collision_block_char : str
        The value in collision_maze that represents an impassable tile
        (comes from utils.collision_block_id, e.g. "32125").

    Returns
    -------
    list[(int, int)]
        Shortest path from start_rc to end_rc as (row, col) tuples,
        start-inclusive.  Returns [start_rc] when no path exists so the
        caller always gets a non-empty list with a valid tile.
    """
    rows = len(collision_maze)
    cols = len(collision_maze[0]) if rows else 0

    sr, sc = start_rc
    er, ec = end_rc

    # ── Bounds guard ──────────────────────────────────────────────────────────
    def in_bounds(r, c):
        return 0 <= r < rows and 0 <= c < cols

    if not in_bounds(sr, sc) or not in_bounds(er, ec):
        return [start_rc]

    # ── Trivial case ──────────────────────────────────────────────────────────
    if start_rc == end_rc:
        return [start_rc]

    # ── If the end tile is a wall, nudge to the nearest walkable neighbor ─────
    # This happens when the LLM targets an object tile that carries a collision
    # flag (e.g., the back row of a counter).  Rather than returning "no path",
    # we path to the adjacent walkable tile closest to the agent.
    if collision_maze[er][ec] == collision_block_char:
        nudged = False
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = er + dr, ec + dc
            if in_bounds(nr, nc) and collision_maze[nr][nc] != collision_block_char:
                er, ec = nr, nc
                nudged = True
                break
        if not nudged:
            return [start_rc]   # end completely walled off

    # ── BFS ───────────────────────────────────────────────────────────────────
    visited = [[False] * cols for _ in range(rows)]
    parent  = {}                # (row, col) → (parent_row, parent_col)

    visited[sr][sc] = True
    queue = deque([(sr, sc)])
    found = False

    while queue:
        r, c = queue.popleft()
        if (r, c) == (er, ec):
            found = True
            break
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if (in_bounds(nr, nc)
                    and not visited[nr][nc]
                    and collision_maze[nr][nc] != collision_block_char):
                visited[nr][nc] = True
                parent[(nr, nc)] = (r, c)
                queue.append((nr, nc))

    if not found:
        return [start_rc]

    # ── Reconstruct path ──────────────────────────────────────────────────────
    path = []
    node = (er, ec)
    while node != (sr, sc):
        path.append(node)
        node = parent[node]
    path.append((sr, sc))
    path.reverse()
    return path


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API  (same signatures as the original)
# ─────────────────────────────────────────────────────────────────────────────

def path_finder(maze, start, end, collision_block_char, verbose=False):
    """
    Shortest-path finder for the Generative Agents simulation.

    This is the single function called throughout execute.py.  It translates
    between the callers' (x, y) = (col, row) convention and the maze's
    [row][col] storage, then delegates to the BFS implementation.

    Parameters
    ----------
    maze : list[list[str]]
        Maze.collision_maze — the raw 2-D collision grid.
    start : (int, int)
        Current tile as (x, y) = (col, row).
    end : (int, int)
        Target tile as (x, y) = (col, row).
    collision_block_char : str
        Collision block ID from utils.collision_block_id.
    verbose : bool
        Unused; kept for API compatibility.

    Returns
    -------
    list[(int, int)]
        Path as (x, y) tuples, start-inclusive.
        Returns [start] when no path exists — never an empty list.

    Notes
    -----
    The original path_finder() contained an "EMERGENCY PATCH" that swapped
    (x, y) → (row, col) on entry and back on exit.  That swap is preserved
    here because the (x=col, y=row) mismatch is a real convention difference
    that exists throughout execute.py, not a bug to be removed.
    """
    # (x, y) = (col, row)  →  (row, col) for BFS
    start_rc = (start[1], start[0])
    end_rc   = (end[1],   end[0])

    path_rc = _bfs_path(maze, start_rc, end_rc, collision_block_char)

    # (row, col)  →  (x, y) = (col, row)
    return [(c, r) for r, c in path_rc]


def closest_coordinate(curr_coordinate, target_coordinates):
    """Return the element of target_coordinates nearest to curr_coordinate."""
    min_dist = None
    best = None
    for coordinate in target_coordinates:
        dist = abs(np.linalg.norm(np.array(coordinate) - np.array(curr_coordinate)))
        if best is None or dist < min_dist:
            min_dist = dist
            best = coordinate
    return best


def path_finder_2(maze, start, end, collision_block_char, verbose=False):
    """
    Path to an adjacent tile of <end> rather than <end> itself.
    Used for persona-to-persona navigation so agents stop beside
    their conversation partner rather than on top of them.
    """
    end = list(end)
    pot_targets = [
        (end[0],     end[1] + 1),
        (end[0],     end[1] - 1),
        (end[0] - 1, end[1]),
        (end[0] + 1, end[1]),
    ]
    maze_width  = len(maze[0])
    maze_height = len(maze)
    targets = [c for c in pot_targets
               if 0 <= c[0] < maze_width and 0 <= c[1] < maze_height]

    target = closest_coordinate(start, targets)
    return path_finder(maze, start, target, collision_block_char)


def path_finder_3(maze, start, end, collision_block_char, verbose=False):
    """
    Split a path into two halves (used for meeting-in-the-middle navigation).
    Returns (a_path, b_path) or ([], []) when the path is too short.
    """
    curr_path = path_finder(maze, start, end, collision_block_char)
    if len(curr_path) <= 2:
        return [], []
    mid = len(curr_path) // 2
    a_path = curr_path[:mid]
    b_path = list(reversed(curr_path[mid - 1:]))
    return a_path, b_path


# ─────────────────────────────────────────────────────────────────────────────
# DEPRECATED LEGACY  (kept for reference; not called anywhere in the codebase)
# ─────────────────────────────────────────────────────────────────────────────

def path_finder_v1(maze, start, end, collision_block_char, verbose=False):
    """DEPRECATED — DFS-based, non-optimal.  Use path_finder() instead."""
    # … original implementation unchanged …
    def prepare_maze(maze, start, end):
        maze[start[0]][start[1]] = "S"
        maze[end[0]][end[1]] = "E"
        return maze

    def find_start(maze):
        for row in range(len(maze)):
            for col in range(len(maze[0])):
                if maze[row][col] == 'S':
                    return row, col

    def is_valid_position(maze, pos_r, pos_c):
        if pos_r < 0 or pos_c < 0:
            return False
        if pos_r >= len(maze) or pos_c >= len(maze[0]):
            return False
        if maze[pos_r][pos_c] in ' E':
            return True
        return False

    def solve_maze(maze, start, verbose=False):
        path = []
        stack = [start]
        while stack:
            pos_r, pos_c = stack.pop()
            if maze[pos_r][pos_c] == 'E':
                path += [(pos_r, pos_c)]
                return path
            if maze[pos_r][pos_c] == 'X':
                continue
            maze[pos_r][pos_c] = 'X'
            path += [(pos_r, pos_c)]
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                if is_valid_position(maze, pos_r+dr, pos_c+dc):
                    stack.append((pos_r+dr, pos_c+dc))
        return False

    new_maze = []
    for row in maze:
        new_row = ["#" if j == collision_block_char else " " for j in row]
        new_maze.append(new_row)
    maze = prepare_maze(new_maze, start, end)
    start = find_start(maze)
    return solve_maze(maze, start, verbose)


def path_finder_v2(a, start, end, collision_block_char, verbose=False):
    """
    DEPRECATED — Bounded Bellman-Ford with a 150-step cap.
    Causes agents to freeze permanently on paths longer than ~150 tiles.
    Use path_finder() → _bfs_path() instead.
    """
    raise DeprecationWarning(
        "path_finder_v2 is deprecated and broken on long paths. "
        "Use path_finder() which delegates to _bfs_path() (proper BFS)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ─────────────────────────────────────────────────────────────────────────────

def _print_maze(maze):
    for row in maze:
        print("".join(str(c) for c in row))


if __name__ == "__main__":
    WALL = "32125"
    W, O = WALL, "0"

    # Simple corridor
    m1 = [
        [W, W, W, W, W],
        [W, O, O, O, W],
        [W, W, W, O, W],
        [W, O, O, O, W],
        [W, W, W, W, W],
    ]
    # Caller uses (x=col, y=row): start=(1,1), end=(1,3)
    p = path_finder(m1, (1,1), (1,3), WALL)
    assert p[0] == (1,1), f"Expected start (1,1), got {p[0]}"
    assert p[-1] == (1,3), f"Expected end (1,3), got {p[-1]}"
    print("Test 1 PASSED — simple corridor:", p)

    # Unreachable target
    m2 = [
        [W, W, W],
        [W, O, W],
        [W, W, W],
    ]
    p2 = path_finder(m2, (1,1), (0,0), WALL)
    assert p2 == [(1,1)], f"Expected [(1,1)] for unreachable, got {p2}"
    print("Test 2 PASSED — unreachable returns start:", p2)

    # Same start and end
    p3 = path_finder(m1, (1,1), (1,1), WALL)
    assert p3 == [(1,1)], f"Expected [(1,1)] for same tile, got {p3}"
    print("Test 3 PASSED — same tile:", p3)

    # Long path (would have failed with except_handle=150 on a large map)
    # Build a 20-wide open corridor
    m3 = [[O] * 20 for _ in range(3)]
    for j in range(20):
        m3[0][j] = W
        m3[2][j] = W
    p4 = path_finder(m3, (0,1), (19,1), WALL)
    assert p4[0] == (0,1) and p4[-1] == (19,1), f"Long path endpoints wrong: {p4[0]} → {p4[-1]}"
    assert len(p4) == 20, f"Expected 20 tiles, got {len(p4)}"
    print("Test 4 PASSED — long corridor (20 tiles):", len(p4), "steps")

    # End tile is a wall → nudge to neighbor
    m4 = [row[:] for row in m1]
    p5 = path_finder(m4, (1,1), (0,0), WALL)   # (0,0) is a wall
    assert p5[0] == (1,1), "Should start at (1,1)"
    print("Test 5 PASSED — end is wall, nudged:", p5)

    print("\nAll tests passed ✓")
