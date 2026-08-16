# Alignment contract

- Child `from` contributes to parent `to` via frozen C1 `perf_alignment_links`
- Tree: Company → Department → Team → Individual where configured
- Orphans allowed
- History: `perf_okr_alignment_events` (`linked` / `withdrawn`)
- `inherits_score = false` always
- Parent progress changes only through C1 measure / rollup of the parent's own KRs
- Hidden nodes omitted — following a tree is not a permission bypass
- Server enforcement: `can_view_objective` + filtered tree
