# Implement `slugify(s)`

`slug.py` contains a `slugify(s)` stub that raises `NotImplementedError`.
Implement URL-slug generation: lowercase the text, turn every run of
non-`[a-z0-9]` characters (spaces, underscores, punctuation, accents) into a
single `-`, and strip leading/trailing `-`.

Examples: `"Hello World"` → `"hello-world"`, `"  A   B  "` → `"a-b"`,
`"Café!"` → `"caf"`, `""` → `""`.
